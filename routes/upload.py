from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from models.context import get_context_id, get_or_create_context
from services.llm import extract_structured_analysis
from services.pdf import allowed_file, save_uploaded_pdf, extract_pdf_text, cleanup_temp_file


upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF file provided"}), 400
    f = request.files["pdf"]
    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if f and allowed_file(f.filename):
        name, path = save_uploaded_pdf(f, current_app.config["UPLOAD_FOLDER"])
        try:
            pdf_text = extract_pdf_text(path, name)

            # Store in context
            context_id = get_context_id(session)
            context = get_or_create_context(context_id, str(current_user.get_id()))
            if context is None:
                return jsonify({"error": "forbidden"}), 403
            context["description"] += f"\n\n[PDF: {name}]\n{pdf_text}"

            # Extract structured analysis from PDF
            analysis = extract_structured_analysis(pdf_text)
            context["analysis"] = analysis

            return jsonify(
                {
                    "filename": name,
                    "text": pdf_text[:500] + "..." if len(pdf_text) > 500 else pdf_text,
                    "analysis": analysis,
                    "context_id": context_id,
                }
            )
        finally:
            cleanup_temp_file(path)
    return jsonify({"error": "Invalid file type"}), 400
