"""
Global search endpoint — searches across all user sessions, cases, notes, and messages.
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.search import search_user_contexts

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["POST"])
@login_required
def search():
    """Search across all user content. Accepts {query, filters}."""
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"results": [], "total": 0, "query": ""})

    filters = data.get("filters") or {}
    user_id = str(current_user.get_id())

    results = search_user_contexts(user_id, query, filters)

    return jsonify({
        "results": results,
        "total": len(results),
        "query": query,
    })
