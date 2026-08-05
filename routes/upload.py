import uuid
from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from models.context import get_context_id, get_or_create_context
import config
from services.jobs import create_job, update_job
from services.matters import upsert_document
from services.pdf import allowed_file, secure_save_document
from services.retrieval import delete_matter_document_index, set_matter_document_included
from services.storage import delete_path, upload_staging_file
from services.task_queue import enqueue_job


upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("files")  # multiple files
    if not files:
        files = [request.files.get("file")]  # fallback to single file
    
    jobs = []
    context_id = request.form.get("matter_id") or request.form.get("context_id") or get_context_id(session)
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden"}), 403

    for file in files:
        if not file or not allowed_file(file.filename or ""):
            continue
        job = None
        document_id = uuid.uuid4().hex
        staging_path = local_path = ""
        try:
            if config.TASKS_MODE == "cloud":
                staging_path = upload_staging_file(
                    file, context.get("workspace_id"), context_id, document_id, file.mimetype)
                filename = file.filename
            else:
                filename, local_path = secure_save_document(file, current_app.config["UPLOAD_FOLDER"])
            payload = {
                "document_id": document_id, "filename": filename,
                "content_type": file.mimetype, "staging_path": staging_path,
                "local_path": local_path,
                "uploaded_by": current_user.name or current_user.email or "Unknown User",
            }
            upsert_document(context_id, str(current_user.get_id()), document_id, {
                "filename": filename, "included": False, "status": "processing",
                "uploaded_by": payload["uploaded_by"],
            }, "")
            job, created = create_job(context_id, str(current_user.get_id()),
                                      "document_ingest", payload, document_id)
            if created:
                enqueue_job(context_id, job["job_id"])
            job["status_url"] = f"/api/matters/{context_id}/jobs/{job['job_id']}"
            jobs.append(job)
        except Exception as exc:
            if job:
                update_job(context_id, job["job_id"], status="failed", stage="enqueue_failed",
                           error={"code": "upload_failed", "message": str(exc)[:300]})
            delete_path(staging_path)
            if local_path:
                from services.pdf import cleanup_temp_file
                cleanup_temp_file(local_path)
    if not jobs:
        return jsonify({"error": "no supported documents could be queued"}), 400
    return jsonify({"status": "queued", "context_id": context_id, "jobs": jobs}), 202

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
        set_matter_document_included(context_id, str(current_user.get_id()),
                                     str(doc.get("record_id") or ""), bool(included))

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
        delete_matter_document_index(context_id, str(current_user.get_id()), doc.get("record_id", ""))
        delete_path(doc.get("storage_path"))

    return jsonify({"status": "ok"})
