import uuid

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from models.context import (
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


context_bp = Blueprint("context", __name__)


@context_bp.route("/context", methods=["GET"])
@login_required
def get_context():
    """Get current context for a session."""
    user_id = str(current_user.get_id())
    if "context_id" not in session:
        workspace_id = active_workspace(user_id)
        stored_id = active_matter(user_id)
        stored_context = get_stored_context(stored_id, user_id) if stored_id else {}
        if stored_context and stored_context.get("workspace_id") == workspace_id:
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
    sessions = list_user_contexts(user_id, workspace_id)
    sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    if not sessions:
        context_id, ctx = create_new_context(user_id, workspace_id=workspace_id)
        session["context_id"] = context_id
        set_active_matter(user_id, context_id)
        sessions = [
            {
                "context_id": context_id, "matter_id": context_id,
                "workspace_id": workspace_id,
                "title": ctx.get("title", "New Session"),
                "total_seconds": ctx.get("total_seconds", 0),
                "created_at": ctx.get("created_at"),
                "updated_at": ctx.get("updated_at"),
            }
        ]
    return jsonify({"contexts": sessions, "matters": sessions,
                    "workspace_id": workspace_id,
                    "active_context_id": get_context_id(session),
                    "active_matter_id": get_context_id(session)})


@context_bp.route("/contexts/new", methods=["POST"])
@login_required
def create_context():
    user_id = str(current_user.get_id())
    context_id = str(uuid.uuid4())
    payload = request.get_json(silent=True) or {}
    workspace_id = payload.get("workspace_id") or session.get("workspace_id") or active_workspace(user_id)
    create_new_context(user_id, context_id=context_id, workspace_id=workspace_id)
    session["context_id"] = context_id
    set_active_matter(user_id, context_id)
    session["workspace_id"] = workspace_id
    return jsonify({"context_id": context_id, "matter_id": context_id,
                    "workspace_id": workspace_id, "title": "New Session"})


@context_bp.route("/contexts/switch", methods=["POST"])
@login_required
def switch_context():
    payload = request.json or {}
    context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403
    session["context_id"] = context_id
    set_active_matter(user_id, context_id)
    loaded = get_stored_context(context_id, user_id) or {}
    session["workspace_id"] = loaded.get("workspace_id")
    current_app.logger.info(
        "Switch context loaded id=%s keys=%s messages=%s cases=%s",
        context_id,
        list(loaded.keys()),
        len(loaded.get("messages", []) or []),
        len(loaded.get("cases", []) or []),
    )
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
    # Include any additional stored keys without dropping known required shape.
    for key, value in loaded.items():
        if key not in context:
            context[key] = value
    return jsonify({
        "status": "ok",
        "switched_to": context_id,
        "context_id": context_id,
        "total_seconds": loaded.get("total_seconds", 0),
        "context": context
    })


@context_bp.route("/contexts/rename", methods=["POST"])
@login_required
def rename_context_route():
    payload = request.json or {}
    context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403
    rename_context(context_id, user_id, title)
    return jsonify({"status": "ok"})


@context_bp.route("/contexts/delete", methods=["POST"])
@login_required
def delete_context_route():
    payload = request.json or {}
    context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403
    deleted = delete_user_context(context_id, user_id)
    if not deleted:
        return jsonify({"error": "delete failed"}), 500

    active_context_id = session.get("context_id")
    if active_context_id == context_id:
        sessions = list_user_contexts(user_id, session.get("workspace_id"))
        remaining = [s for s in sessions if s.get("context_id") != context_id]
        remaining.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        if remaining:
            existing_context_id = str(remaining[0].get("context_id") or "").strip()
            if not existing_context_id:
                return jsonify({"error": "no remaining contexts"}), 500
            session["context_id"] = existing_context_id
            set_active_matter(user_id, existing_context_id)
            loaded = get_stored_context(existing_context_id, user_id) or {}
            full_context_data = {
                "context_id": existing_context_id,
                "title": loaded.get("title", "New Session"),
                "description": loaded.get("description", ""),
                "messages": loaded.get("messages", []),
                "analysis": loaded.get("analysis", {}),
                "cases": loaded.get("cases", []),
                "summary": loaded.get("summary", ""),
                "search_query": loaded.get("search_query", ""),
                "draft": loaded.get("draft", ""),
            }
            for key, value in loaded.items():
                if key not in full_context_data:
                    full_context_data[key] = value
            return jsonify(
                {
                    "status": "ok",
                    "switched_to": existing_context_id,
                    "context": full_context_data,
                }
            )

        new_context_id = str(uuid.uuid4())
        create_new_context(user_id, context_id=new_context_id, workspace_id=session.get("workspace_id"))
        session["context_id"] = new_context_id
        set_active_matter(user_id, new_context_id)
        default_context_data = get_context_or_default(new_context_id, user_id) or {}
        return jsonify(
            {
                "status": "ok",
                "switched_to": new_context_id,
                "context": default_context_data,
            }
        )
    return jsonify({"status": "ok", "switched_to": session.get("context_id")})


@context_bp.route("/session/track-time", methods=["POST"])
@login_required
def track_time():
    data = request.get_json(silent=True) or {}
    context_id = data.get("matter_id") or data.get("context_id")
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    try:
        seconds = int(data.get("seconds", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "seconds must be an integer"}), 400
    if seconds <= 0 or seconds > 86_400:
        return jsonify({"error": "seconds must be between 1 and 86400"}), 400
    user_id = str(current_user.get_id())

    context = get_stored_context(context_id, user_id)
    if not context:
        return jsonify({"total_seconds": 0}), 404
    total = append_time_entry(context_id, user_id, seconds)
    return jsonify({"total_seconds": total})
