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


context_bp = Blueprint("context", __name__)


@context_bp.route("/context", methods=["GET"])
@login_required
def get_context():
    print("[ROUTE] /context called")
    """Get current context for a session."""
    context_id = get_context_id(session)
    context = get_context_or_default(context_id, str(current_user.get_id()))
    print(f"[GET-CONTEXT] Returning total_seconds: {context.get('total_seconds', 0)}")
    return jsonify({
        "context_id": context_id,
        "total_seconds": context.get("total_seconds", 0),
        "context": context
    })


@context_bp.route("/contexts", methods=["GET"])
@login_required
def get_contexts():
    print("[ROUTE] /contexts called")
    user_id = str(current_user.get_id())
    sessions = list_user_contexts(user_id)
    for ctx in sessions:
        print(f"[CONTEXTS-LIST] {ctx.get('context_id', 'Unknown')}: total_seconds = {ctx.get('total_seconds', 'MISSING')}")
    sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    if not sessions:
        context_id, ctx = create_new_context(user_id)
        session["context_id"] = context_id
        sessions = [
            {
                "context_id": context_id,
                "title": ctx.get("title", "New Session"),
                "total_seconds": ctx.get("total_seconds", 0),
                "created_at": ctx.get("created_at"),
                "updated_at": ctx.get("updated_at"),
            }
        ]
    return jsonify({"contexts": sessions, "active_context_id": get_context_id(session)})


@context_bp.route("/contexts/new", methods=["POST"])
@login_required
def create_context():
    user_id = str(current_user.get_id())
    context_id = str(uuid.uuid4())
    create_new_context(user_id, context_id=context_id)
    session["context_id"] = context_id
    return jsonify({"context_id": context_id, "title": "New Session"})


@context_bp.route("/contexts/switch", methods=["POST"])
@login_required
def switch_context():
    print(f"[ROUTE] /contexts/switch called with body: {request.get_json(silent=True)}")
    payload = request.json or {}
    context_id = str(payload.get("context_id", "")).strip()
    user_id = str(current_user.get_id())
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403
    session["context_id"] = context_id
    loaded = get_stored_context(context_id, user_id) or {}
    current_app.logger.info(
        "Switch context loaded id=%s keys=%s messages=%s cases=%s",
        context_id,
        list(loaded.keys()),
        len(loaded.get("messages", []) or []),
        len(loaded.get("cases", []) or []),
    )
    context = {
        "context_id": context_id,
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
    context_id = str(payload.get("context_id", "")).strip()
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
    context_id = str(payload.get("context_id", "")).strip()
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
        sessions = list_user_contexts(user_id)
        remaining = [s for s in sessions if s.get("context_id") != context_id]
        remaining.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        if remaining:
            existing_context_id = str(remaining[0].get("context_id") or "").strip()
            if not existing_context_id:
                return jsonify({"error": "no remaining contexts"}), 500
            session["context_id"] = existing_context_id
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
        create_new_context(user_id, context_id=new_context_id)
        session["context_id"] = new_context_id
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
    print(f"[ROUTE] /session/track-time called with body: {request.get_json(silent=True)}")
    data = request.get_json(silent=True) or {}
    context_id = data.get("context_id")
    seconds = data.get("seconds", 0)
    user_id = str(current_user.get_id())
    
    print(f"[TRACK-TIME] Received seconds: {seconds}")
    
    context = get_stored_context(context_id, user_id)
    if not context:
        return jsonify({"total_seconds": 0}), 404

    print(f"[TRACK-TIME] Context BEFORE: total_seconds = {context.get('total_seconds', 'KEY MISSING')}")
    if hasattr(context, "set"):
        context.set("total_seconds", int(context.get("total_seconds", 0)) + int(seconds), touch=False)
    else:
        context["total_seconds"] = int(context.get("total_seconds", 0)) + int(seconds)
    print(f"[TRACK-TIME] Context AFTER: total_seconds = {context.get('total_seconds')}")
    
    return jsonify({"total_seconds": context["total_seconds"]})
