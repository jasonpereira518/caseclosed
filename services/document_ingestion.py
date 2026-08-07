"""Transient-original document ingestion."""
from __future__ import annotations

import hashlib
import os
import tempfile

from services.matters import upsert_document
from services.jobs import cancellation_requested
from services.chat_orchestrator import JobCancelled
from services.pdf import extract_document_text
from services.retrieval import index_matter_document
from services.storage import delete_path, download_to_file
from services.tenancy import now


def ingest_document_job(matter_id: str, job_id: str, data: dict) -> dict:
    payload = data.get("payload") or {}
    uid = str(data.get("requested_by") or "")
    document_id = str(payload.get("document_id") or "")
    filename = str(payload.get("filename") or "document")
    storage_path = str(payload.get("storage_path") or payload.get("staging_path") or "")
    staging_path = str(payload.get("staging_path") or "")
    local_path = str(payload.get("local_path") or "")
    temporary_download = ""
    if not document_id or not (storage_path or local_path):
        raise ValueError("document ingestion payload is incomplete")
    try:
        path = local_path
        if storage_path:
            suffix = os.path.splitext(filename)[1]
            handle = tempfile.NamedTemporaryFile(prefix="caseclosed-ingest-", suffix=suffix, delete=False)
            temporary_download = handle.name
            try:
                download_to_file(storage_path, handle)
            finally:
                handle.close()
            path = temporary_download
        with open(path, "rb") as source:
            hasher = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(block)
            digest = hasher.hexdigest()
        text = extract_document_text(path, filename).strip()
        if not text:
            raise ValueError("document yielded no extractable text")
        if cancellation_requested(matter_id, job_id):
            raise JobCancelled()
        metadata = {
            "filename": filename, "included": False, "status": "ready",
            "error": None,
            "uploaded_by": payload.get("uploaded_by") or "Unknown User",
            "uploaded_at": now(), "sha256": digest,
            "content_type": payload.get("content_type") or "application/octet-stream",
            "size_bytes": os.path.getsize(path),
            "storage_path": storage_path if storage_path and not staging_path else None,
        }
        upsert_document(matter_id, uid, document_id, metadata, text)
        chunks = index_matter_document(matter_id, uid, document_id, filename, text)
        return {"status": "document_ready", "document": {
            "record_id": document_id, **metadata, "uploaded_at": metadata["uploaded_at"].isoformat(),
            "chunk_count": chunks,
        }}
    finally:
        if temporary_download and os.path.exists(temporary_download):
            try:
                os.remove(temporary_download)
            except OSError:
                pass


def cleanup_document_source(data: dict):
    """Remove retry-only source files while retaining durable matter originals."""
    payload = data.get("payload") or {}
    staging_path = str(payload.get("staging_path") or "")
    local_path = str(payload.get("local_path") or "")
    if staging_path:
        try:
            delete_path(staging_path)
        except Exception:
            pass
    if local_path and os.path.exists(local_path):
        try:
            os.remove(local_path)
        except OSError:
            pass
