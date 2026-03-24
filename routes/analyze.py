from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.context import get_context as get_stored_context, get_or_create_context
from services.llm import extract_structured_analysis


analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("/analyze", methods=["POST"])
@login_required
def analyze():
    """Extract structured analysis from text or use existing context."""
    payload = request.json or {}
    text = payload.get("text", "").strip()
    context_id = payload.get("context_id")

    uid = str(current_user.get_id())
    if not text and context_id:
        context = get_stored_context(context_id, uid)
        text = context.get("description", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    analysis = extract_structured_analysis(text)

    # Update context if provided
    if context_id:
        ctx = get_or_create_context(context_id, uid)
        if ctx is None:
            return jsonify({"error": "forbidden"}), 403
        ctx["analysis"] = analysis
        if not ctx["description"]:
            ctx["description"] = text

    return jsonify({"status": "success", "analysis": analysis, "context_id": context_id})
