from datetime import datetime
from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from models.context import get_context_id, get_or_create_context
from services.llm import extract_structured_analysis, generate_session_title
from services.pdf import process_upload


upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("files")  # multiple files
    if not files:
        files = [request.files.get("file")]  # fallback to single file
    
    uploaded_docs = []
    context_id = get_context_id(session)
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403

    for file in files:
        if file:
            try:
                doc_payload = process_upload(file, current_app.config["UPLOAD_FOLDER"])
                doc_payload["uploaded_by"] = current_user.name or current_user.email or "Unknown User"
                doc_payload["uploaded_at"] = datetime.now().strftime("%b %d, %Y")
                uploaded_docs.append(doc_payload)
            except ValueError:
                continue
    
    if uploaded_docs:
        existing_docs = context.get("uploaded_documents", [])
        existing_docs.extend(uploaded_docs)
        context["uploaded_documents"] = existing_docs
    
    return jsonify({
        "status": "success",
        "documents": uploaded_docs,
        "total_documents": len(context.get("uploaded_documents", []))
    })

@upload_bp.route("/documents/toggle", methods=["POST"])
@login_required
def toggle_document():
    data = request.get_json()
    context_id = data.get("context_id")
    doc_index = data.get("doc_index")
    included = data.get("included")

    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403

    docs = context.get("uploaded_documents", [])
    if 0 <= doc_index < len(docs):
        doc = docs[doc_index]
        doc["included"] = included
        
        # update description
        text_block = f"\n\n[Document: {doc['filename']}]\n{doc['text']}"
        desc = context.get("description", "")
        
        if included:
            if text_block not in desc:
                context["description"] = desc + text_block
        else:
            context["description"] = desc.replace(text_block, "")

    return jsonify({"status": "ok", "included": included})

@upload_bp.route("/documents/delete", methods=["POST"])
@login_required
def delete_document():
    data = request.get_json()
    context_id = data.get("context_id")
    doc_index = data.get("doc_index")

    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403

    docs = context.get("uploaded_documents", [])
    if 0 <= doc_index < len(docs):
        doc = docs[doc_index]
        
        # safely slice description if logically toggled
        if doc.get("included"):
            text_block = f"\n\n[Document: {doc['filename']}]\n{doc['text']}"
            desc = context.get("description", "")
            context["description"] = desc.replace(text_block, "")
            
        docs.pop(doc_index)
        context["uploaded_documents"] = docs

    return jsonify({"status": "ok"})
