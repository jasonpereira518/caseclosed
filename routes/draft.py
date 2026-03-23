from flask import Blueprint, jsonify, request

from models.context import get_context as get_stored_context
from services.llm import draft_legal_document, extract_structured_analysis


draft_bp = Blueprint("draft", __name__)


@draft_bp.route("/draft", methods=["POST"])
def draft():
    """Generate legal memo or brief from context."""
    payload = request.json or {}
    context_id = payload.get("context_id")
    doc_type = payload.get("doc_type", "memo")  # "memo" or "brief"

    if not context_id:
        return jsonify({"error": "No context_id provided"}), 400

    context = get_stored_context(context_id)
    if not context:
        return jsonify({"error": "Context not found"}), 404

    # Ensure we have analysis
    if not context.get("analysis"):
        if context.get("description"):
            context["analysis"] = extract_structured_analysis(context["description"])
        else:
            return jsonify({"error": "No case information available"}), 400

    # Generate document
    document = draft_legal_document(context, doc_type)

    return jsonify(
        {"status": "success", "document": document, "doc_type": doc_type, "context_id": context_id}
    )
