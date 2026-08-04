from datetime import datetime
import uuid
from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from models.context import get_context_id, get_or_create_context
from services.pdf import process_upload
from services.storage import delete_path, signed_download_url


upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("files")  # multiple files
    if not files:
        files = [request.files.get("file")]  # fallback to single file
    
    uploaded_docs = []
    context_id = request.form.get("matter_id") or request.form.get("context_id") or get_context_id(session)
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403

    for file in files:
        if file:
            try:
                document_id = str(uuid.uuid4())
                doc_payload = process_upload(
                    file, current_app.config["UPLOAD_FOLDER"],
                    workspace_id=context.get("workspace_id"), matter_id=context_id,
                    document_id=document_id,
                )
                doc_payload["record_id"] = document_id
                doc_payload["uploaded_by"] = current_user.name or current_user.email or "Unknown User"
                doc_payload["uploaded_at"] = datetime.now().strftime("%b %d, %Y")
                uploaded_docs.append(doc_payload)
            except ValueError:
                continue
    
    if uploaded_docs:
        existing_docs = context.get("uploaded_documents", [])
        existing_docs.extend(uploaded_docs)
        try:
            context["uploaded_documents"] = existing_docs
        except Exception:
            for document in uploaded_docs:
                delete_path(document.get("storage_path"))
            raise
    
    return jsonify({
        "status": "success",
        "documents": uploaded_docs,
        "total_documents": len(context.get("uploaded_documents", []))
    })

@upload_bp.route("/documents/toggle", methods=["POST"])
@login_required
def toggle_document():
    data = request.get_json()
    context_id = data.get("matter_id") or data.get("context_id")
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
    context_id = data.get("matter_id") or data.get("context_id")
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
        delete_path(doc.get("storage_path"))

    return jsonify({"status": "ok"})


@upload_bp.route("/documents/download", methods=["POST"])
@login_required
def download_document():
    data = request.get_json(silent=True) or {}
    context_id = str(data.get("matter_id") or data.get("context_id") or "").strip()
    record_id = str(data.get("document_id") or "").strip()
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403
    for document in context.get("uploaded_documents") or []:
        if str(document.get("record_id")) == record_id and document.get("storage_path"):
            return jsonify({"url": signed_download_url(document["storage_path"])})
    return jsonify({"error": "document not found"}), 404
