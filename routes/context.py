from flask import Blueprint, jsonify, session

from models.context import get_context_id, get_context_or_default


context_bp = Blueprint("context", __name__)


@context_bp.route("/context", methods=["GET"])
def get_context():
    """Get current context for a session."""
    context_id = get_context_id(session)
    context = get_context_or_default(context_id)
    return jsonify({"context_id": context_id, "context": context})
