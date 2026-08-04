"""Private Firebase Storage operations with Firestore-owned paths."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from firebase_admin import storage

import config
from services.firestore import get_firestore_client


def _bucket():
    get_firestore_client()  # initializes the shared Firebase app
    if not config.FIREBASE_STORAGE_BUCKET:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET is required for durable uploads")
    return storage.bucket(config.FIREBASE_STORAGE_BUCKET)


def upload_matter_file(path: str, workspace_id: str, matter_id: str,
                       document_id: str, filename: str, content_type: str | None = None) -> dict:
    storage_path = f"workspaces/{workspace_id}/matters/{matter_id}/documents/{document_id}/{filename}"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    blob = _bucket().blob(storage_path)
    blob.upload_from_filename(path, content_type=content_type or "application/octet-stream")
    blob.reload()
    return {
        "storage_path": storage_path,
        "sha256": digest.hexdigest(),
        "size_bytes": blob.size,
        "content_type": blob.content_type or content_type,
    }


def upload_avatar(path: str, uid: str, filename: str, content_type: str | None = None) -> str:
    storage_path = f"users/{uid}/avatar/{filename}"
    blob = _bucket().blob(storage_path)
    blob.upload_from_filename(path, content_type=content_type or "application/octet-stream")
    return storage_path


def upload_bytes(data: bytes, storage_path: str, content_type: str) -> str:
    blob = _bucket().blob(storage_path)
    blob.upload_from_string(data, content_type=content_type)
    return storage_path


def signed_download_url(storage_path: str, minutes: int = 10) -> str:
    return _bucket().blob(storage_path).generate_signed_url(
        expiration=timedelta(minutes=minutes), method="GET", version="v4")


def delete_path(storage_path: str):
    if storage_path:
        blob = _bucket().blob(storage_path)
        if blob.exists():
            blob.delete()


def delete_prefix(prefix: str):
    for blob in _bucket().list_blobs(prefix=prefix):
        blob.delete()


def download_bytes(storage_path: str) -> bytes:
    return _bucket().blob(storage_path).download_as_bytes()
