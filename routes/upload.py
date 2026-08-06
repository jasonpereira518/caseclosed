import uuid
from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models.context import get_context, get_context_id, get_or_create_context
import config
from services.jobs import create_job, update_job
from services.matters import delete_document as delete_document_record
from services.matters import patch_document, patch_matter, require_matter, upsert_document
from services.pdf import allowed_file, secure_save_document
from services.retrieval import delete_matter_document_index, set_matter_document_included
from services.storage import delete_path, signed_download_url, upload_matter_file
from services.task_queue import enqueue_job
from services.tenancy import AuthorizationError


upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    if config.TASKS_MODE == "cloud" and not config.FIREBASE_STORAGE_BUCKET:
        return jsonify({"error": "durable document storage is not configured"}), 503
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
        document_created = False
        document_id = uuid.uuid4().hex
        storage_path = local_path = ""
        try:
            filename = secure_filename(file.filename) or f"document-{document_id}"
            if config.FIREBASE_STORAGE_BUCKET:
                storage_path = upload_matter_file(
                    file, context.get("workspace_id"), context_id, document_id,
                    filename, file.mimetype)
            else:
                filename, local_path = secure_save_document(file, current_app.config["UPLOAD_FOLDER"])
            payload = {
                "document_id": document_id, "filename": filename,
                "content_type": file.mimetype, "storage_path": storage_path,
                "local_path": local_path,
                "uploaded_by": current_user.name or current_user.email or "Unknown User",
            }
            upsert_document(context_id, str(current_user.get_id()), document_id, {
                "filename": filename, "included": False, "status": "processing",
                "uploaded_by": payload["uploaded_by"], "storage_path": storage_path or None,
            }, "")
            document_created = True
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
            if document_created:
                try:
                    patch_document(context_id, str(current_user.get_id()), document_id,
                                   {"status": "failed", "error": str(exc)[:300]})
                except Exception:
                    pass
            if local_path:
                from services.pdf import cleanup_temp_file
                cleanup_temp_file(local_path)
    if not jobs:
        return jsonify({"error": "no supported documents could be queued"}), 400
    return jsonify({"status": "queued", "context_id": context_id, "jobs": jobs}), 202

@upload_bp.route("/documents/toggle", methods=["POST"])
@login_required
def toggle_document():
    data = request.get_json(silent=True) or {}
    context_id = data.get("matter_id") or data.get("context_id")
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    try:
        doc_index = int(data.get("doc_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid doc_index"}), 400
    included = data.get("included")
    if not isinstance(included, bool):
        return jsonify({"error": "included must be a boolean"}), 400

    context = get_context(context_id, str(current_user.get_id()))
    if not context:
        return jsonify({"error": "forbidden or not found"}), 403

    docs = context.get("uploaded_documents", [])
    if doc_index < 0 or doc_index >= len(docs):
        return jsonify({"error": "invalid doc_index"}), 400
    doc = docs[doc_index]
    document_id = str(doc.get("record_id") or "")
    if not document_id:
        return jsonify({"error": "document record is invalid"}), 409
    text_block = f"\n\n[Document: {doc['filename']}]\n{doc.get('text', '')}"
    description = context.get("description", "")
    if included and text_block not in description:
        description += text_block
    elif not included:
        description = description.replace(text_block, "")
    patch_document(context_id, str(current_user.get_id()), document_id,
                   {"included": included})
    patch_matter(context_id, str(current_user.get_id()), root={"description": description})
    set_matter_document_included(context_id, str(current_user.get_id()), document_id, included)

    return jsonify({"status": "ok", "included": included})

@upload_bp.route("/documents/delete", methods=["POST"])
@login_required
def delete_document():
    data = request.get_json(silent=True) or {}
    context_id = data.get("matter_id") or data.get("context_id")
    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    try:
        doc_index = int(data.get("doc_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid doc_index"}), 400

    context = get_context(context_id, str(current_user.get_id()))
    if not context:
        return jsonify({"error": "forbidden or not found"}), 403

    docs = context.get("uploaded_documents", [])
    if doc_index < 0 or doc_index >= len(docs):
        return jsonify({"error": "invalid doc_index"}), 400
    doc = docs[doc_index]
    document_id = str(doc.get("record_id") or "")
    if not document_id:
        return jsonify({"error": "document record is invalid"}), 409
    description = context.get("description", "")
    if doc.get("included"):
        text_block = f"\n\n[Document: {doc['filename']}]\n{doc.get('text', '')}"
        description = description.replace(text_block, "")
    delete_matter_document_index(context_id, str(current_user.get_id()), document_id)
    delete_path(doc.get("storage_path"))
    delete_document_record(context_id, str(current_user.get_id()), document_id)
    patch_matter(context_id, str(current_user.get_id()), root={"description": description})

    return jsonify({"status": "ok"})


@upload_bp.route("/api/matters/<matter_id>/documents/<document_id>/download")
@login_required
def download_document(matter_id, document_id):
    try:
        _, matter_ref, _ = require_matter(matter_id, str(current_user.get_id()))
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    snap = matter_ref.collection("documents").document(str(document_id)).get()
    document = snap.to_dict() if snap.exists else None
    storage_path = (document or {}).get("storage_path")
    if not storage_path:
        return jsonify({"error": "original document is unavailable"}), 404
    return jsonify({"download_url": signed_download_url(storage_path),
                    "filename": document.get("filename") or "document"})
