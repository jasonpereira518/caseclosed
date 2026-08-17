from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required

from models.context import (
    archive_context,
    context_belongs_to_user,
    create_new_context,
    delete_user_context,
    get_context as get_stored_context,
    get_context_id,
    get_context_or_default,
    list_user_contexts,
    rename_context,
)
from services.tenancy import active_matter, active_workspace, set_active_matter
from services.matters import append_time_entry
from services.request_context import resolve_matter_id


context_bp = Blueprint("context", __name__)

def _not_found():
    """Inaccessible and nonexistent matters are deliberately
    indistinguishable: the matter index is a locator, never an authorization
    source, so a caller probing IDs learns nothing from the status code."""
    return jsonify({"error": "matter not found"}), 404


def _full_context(context_id, loaded):
    """The rehydration payload shape shared by switch, delete, and archive."""
    context = {
        "context_id": context_id, "matter_id": context_id,
        "workspace_id": loaded.get("workspace_id"),
        "title": loaded.get("title", "New Session"),
        "description": loaded.get("description", ""),
        "messages": loaded.get("messages", []),
        "analysis": loaded.get("analysis", {}),
        "cases": loaded.get("cases", []),
        "summary": loaded.get("summary", ""),
        "search_query": loaded.get("search_query", ""),
        "draft": loaded.get("draft", ""),
        "total_seconds": loaded.get("total_seconds", 0),
    }
    for key, value in loaded.items():
        if key not in context:
            context[key] = value
    return context


def _activate_next_matter(user_id):
    """After the active matter is deleted or archived, move to the most
    recently updated remaining matter — or auto-create a fresh one (a
    workspace is never empty by design)."""
    previous_id = session.get("context_id")
    workspace_id = session.get("workspace_id")
    remaining = [s for s in list_user_contexts(user_id, workspace_id)
                 if s.get("context_id") != previous_id]
    remaining.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    if remaining:
        next_id = str(remaining[0].get("context_id") or "").strip()
        session["context_id"] = next_id
        set_active_matter(user_id, next_id)
        loaded = get_stored_context(next_id, user_id) or {}
        return {"status": "ok", "switched_to": next_id,
                "context": _full_context(next_id, loaded)}
    new_id, ctx = create_new_context(user_id, workspace_id=workspace_id)
    session["context_id"] = new_id
    set_active_matter(user_id, new_id)
    context = get_context_or_default(new_id, user_id) or dict(ctx or {})
    return {"status": "ok", "switched_to": new_id, "context": context}


@context_bp.route("/context", methods=["GET"])
@login_required
def get_context():
    """Get current context for a session."""
    user_id = str(current_user.get_id())
    if "context_id" not in session:
        workspace_id = active_workspace(user_id)
        stored_id = active_matter(user_id)
        stored_context = get_stored_context(stored_id, user_id) if stored_id else {}
        if (stored_context
                and stored_context.get("workspace_id") == workspace_id
                and stored_context.get("status") != "archived"):
            session["context_id"] = stored_id
        else:
            matters = list_user_contexts(user_id, workspace_id)
            if matters:
                session["context_id"] = matters[0]["context_id"]
            else:
                session["context_id"] = create_new_context(user_id, workspace_id=workspace_id)[0]
    context_id = get_context_id(session)
    set_active_matter(user_id, context_id)
    context = get_context_or_default(context_id, user_id)
    session["workspace_id"] = context.get("workspace_id") or active_workspace(user_id)
    return jsonify({
        "context_id": context_id, "matter_id": context_id,
        "workspace_id": session.get("workspace_id"),
        "total_seconds": context.get("total_seconds", 0),
        "context": context
    })


@context_bp.route("/contexts", methods=["GET"])
@login_required
def get_contexts():
    user_id = str(current_user.get_id())
    workspace_id = request.args.get("workspace_id") or session.get("workspace_id") or active_workspace(user_id)
    session["workspace_id"] = workspace_id
    matters = list_user_contexts(user_id, workspace_id, include_archived=True)
    active = [m for m in matters if m.get("status") != "archived"]
    archived = [m for m in matters if m.get("status") == "archived"]
    active.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    archived.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    if not active:
        context_id, ctx = create_new_context(user_id, workspace_id=workspace_id)
        session["context_id"] = context_id
        set_active_matter(user_id, context_id)
        active = [
            {
                "context_id": context_id, "matter_id": context_id,
                "workspace_id": workspace_id,
                "title": ctx.get("title", "New Session"),
                "total_seconds": ctx.get("total_seconds", 0),
                "created_at": ctx.get("created_at"),
                "updated_at": ctx.get("updated_at"),
            }
        ]
    body = {"contexts": active, "matters": active,
            "workspace_id": workspace_id,
            "archived_count": len(archived),
            "active_context_id": get_context_id(session),
            "active_matter_id": get_context_id(session)}
    if request.args.get("include_archived"):
        body["archived"] = archived
    return jsonify(body)


@context_bp.route("/contexts/new", methods=["POST"])
@login_required
def create_context():
    user_id = str(current_user.get_id())
    payload = request.get_json(silent=True) or {}
    workspace_id = payload.get("workspace_id") or session.get("workspace_id") or active_workspace(user_id)
    context_id, _ = create_new_context(user_id, workspace_id=workspace_id)
    session["context_id"] = context_id
    set_active_matter(user_id, context_id)
    session["workspace_id"] = workspace_id
    return jsonify({"context_id": context_id, "matter_id": context_id,
                    "workspace_id": workspace_id, "title": "New Session"})


@context_bp.route("/contexts/switch", methods=["POST"])
@login_required
def switch_context():
    payload = request.json or {}
    context_id = resolve_matter_id(payload) or ""
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return _not_found()
    session["context_id"] = context_id
    set_active_matter(user_id, context_id)
    loaded = get_stored_context(context_id, user_id) or {}
    session["workspace_id"] = loaded.get("workspace_id")
    return jsonify({
        "status": "ok",
        "switched_to": context_id,
        "context_id": context_id,
        "total_seconds": loaded.get("total_seconds", 0),
        "context": _full_context(context_id, loaded)
    })


@context_bp.route("/contexts/rename", methods=["POST"])
@login_required
def rename_context_route():
    payload = request.json or {}
    context_id = resolve_matter_id(payload) or ""
    title = str(payload.get("title", "")).strip()
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return _not_found()
    rename_context(context_id, user_id, title)
    return jsonify({"status": "ok"})


def _set_archived(archived: bool):
    payload = request.get_json(silent=True) or {}
    context_id = resolve_matter_id(payload) or ""
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return _not_found()
    if not archive_context(context_id, user_id, archived):
        return jsonify({"error": "update failed"}), 500
    if archived and session.get("context_id") == context_id:
        return jsonify(_activate_next_matter(user_id))
    return jsonify({"status": "ok", "context_id": context_id})


@context_bp.route("/contexts/archive", methods=["POST"])
@login_required
def archive_context_route():
    """Hide a closed matter from the sidebar without touching its data."""
    return _set_archived(True)


@context_bp.route("/contexts/unarchive", methods=["POST"])
@login_required
def unarchive_context_route():
    return _set_archived(False)


@context_bp.route("/contexts/delete", methods=["POST"])
@login_required
def delete_context_route():
    payload = request.json or {}
    context_id = resolve_matter_id(payload) or ""
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return _not_found()
    if not delete_user_context(context_id, user_id):
        return jsonify({"error": "delete failed"}), 500
    if session.get("context_id") == context_id:
        return jsonify(_activate_next_matter(user_id))
    return jsonify({"status": "ok", "switched_to": session.get("context_id")})


@context_bp.route("/session/track-time", methods=["POST"])
@login_required
def track_time():
    data = request.get_json(silent=True) or {}
    context_id = resolve_matter_id(data)
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    try:
        seconds = int(data.get("seconds", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "seconds must be an integer"}), 400
    if seconds <= 0 or seconds > 86_400:
        return jsonify({"error": "seconds must be between 1 and 86400"}), 400
    user_id = str(current_user.get_id())

    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"total_seconds": 0}), 404
    total = append_time_entry(context_id, user_id, seconds)
    return jsonify({"total_seconds": total})
