"""
Per-case notes — save and delete user notes on individual cases.

Notes are stored as a ``notes`` string and ``notes_updated_at`` timestamp
inside each case object in the Firestore-backed session context, following
the same pattern used by bookmarks and follow-ups.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.context import context_belongs_to_user, get_context
from services.request_context import resolve_matter_id

notes_bp = Blueprint("notes", __name__)


def _now_iso():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@notes_bp.route("/case/notes", methods=["POST"])
@login_required
def save_note():
    """Create or update a note on a specific case (upsert)."""
    data = request.get_json(silent=True) or {}
    context_id = resolve_matter_id(data) or ""
    case_index = data.get("case_index")
    content = data.get("content", "")

    if not context_id or case_index is None:
        return jsonify({"error": "context_id and case_index are required"}), 400

    try:
        idx = int(case_index)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid case_index"}), 400

    user_id = str(current_user.get_id())
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403

    ctx = get_context(context_id, user_id)
    if not ctx:
        return jsonify({"error": "context not found"}), 404

    cases = list(ctx.get("cases") or [])
    if idx < 0 or idx >= len(cases):
        return jsonify({"error": "invalid case_index"}), 400

    now = _now_iso()
    cases[idx] = dict(cases[idx])
    cases[idx]["notes"] = str(content)
    cases[idx]["notes_updated_at"] = now
    ctx["cases"] = cases  # triggers FirestoreBackedDict save

    return jsonify({"status": "ok", "updated_at": now})


@notes_bp.route("/case/notes", methods=["DELETE"])
@login_required
def delete_note():
    """Delete (clear) a note from a specific case."""
    data = request.get_json(silent=True) or {}
    context_id = resolve_matter_id(data) or ""
    case_index = data.get("case_index")

    if not context_id or case_index is None:
        return jsonify({"error": "context_id and case_index are required"}), 400

    try:
        idx = int(case_index)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid case_index"}), 400

    user_id = str(current_user.get_id())
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "forbidden"}), 403

    ctx = get_context(context_id, user_id)
    if not ctx:
        return jsonify({"error": "context not found"}), 404

    cases = list(ctx.get("cases") or [])
    if idx < 0 or idx >= len(cases):
        return jsonify({"error": "invalid case_index"}), 400

    cases[idx] = dict(cases[idx])
    cases[idx]["notes"] = ""
    cases[idx].pop("notes_updated_at", None)
    ctx["cases"] = cases

    return jsonify({"status": "ok"})
