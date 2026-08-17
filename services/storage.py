"""Private Firebase Storage operations with Firestore-owned paths."""
from __future__ import annotations

from datetime import timedelta

from firebase_admin import storage

import config
from services.firestore import get_firestore_client


def _bucket():
    get_firestore_client()  # initializes the shared Firebase app
    if not config.FIREBASE_STORAGE_BUCKET:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET is required for durable uploads")
    return storage.bucket(config.FIREBASE_STORAGE_BUCKET)


def upload_matter_file(file_object, workspace_id: str, matter_id: str,
                       document_id: str, filename: str,
                       content_type: str | None = None) -> str:
    """Persist an original upload at a server-owned, tenant-scoped path."""
    storage_path = (
        f"workspaces/{workspace_id}/matters/{matter_id}/documents/"
        f"{document_id}/{filename}"
    )
    file_object.stream.seek(0)
    _bucket().blob(storage_path).upload_from_file(
        file_object.stream, content_type=content_type or "application/octet-stream")
    return storage_path


def upload_avatar(path: str, uid: str, filename: str, content_type: str | None = None) -> str:
    storage_path = f"users/{uid}/avatar/{filename}"
    blob = _bucket().blob(storage_path)
    blob.upload_from_filename(path, content_type=content_type or "application/octet-stream")
    return storage_path


def upload_file_object(file_object, storage_path: str, content_type: str) -> str:
    file_object.seek(0)
    _bucket().blob(storage_path).upload_from_file(file_object, content_type=content_type)
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


def download_to_file(storage_path: str, destination):
    _bucket().blob(storage_path).download_to_file(destination)
