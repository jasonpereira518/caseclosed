"""Account data export -- builds a downloadable zip archive of a user's data.

Runs inside the account_export job body (services/worker.py:process_account_job),
so it returns a result payload rather than owning any job-status bookkeeping.
"""
from __future__ import annotations

import html
import json
import tempfile
import zipfile

from werkzeug.utils import secure_filename

import config
from services.firestore import get_firestore_client
from services.matters import list_matters, load_matter
from services.storage import download_to_file, upload_file_object
from services.tenancy import get_profile, list_workspaces


def _json_safe(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"unsupported value: {type(value)!r}")


def run_account_export(uid: str, job_id: str, data: dict) -> dict:
    archive = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            account_data = {"profile": get_profile(uid), "workspaces": list_workspaces(uid)}
            user_snapshot = get_firestore_client().collection(
                config.FIRESTORE_USERS_COLLECTION).document(uid).get()
            user_record = user_snapshot.to_dict() or {}
            if user_record.get("avatar_storage_path"):
                account_data["profile"]["avatar_url"] = None
            bundle.writestr("account.json", json.dumps(account_data, default=_json_safe, indent=2))
            if user_record.get("avatar_storage_path"):
                with bundle.open("profile/avatar", "w") as destination:
                    download_to_file(user_record["avatar_storage_path"], destination)
            for workspace in account_data["workspaces"]:
                wid = workspace["workspace_id"]
                for summary in list_matters(wid, uid):
                    matter = load_matter(summary["matter_id"], uid) or {}
                    prefix = f"workspaces/{wid}/matters/{summary['matter_id']}"
                    bundle.writestr(f"{prefix}/matter.json",
                                    json.dumps(matter, default=_json_safe, indent=2))
                    html_document = (
                        f"<html><body><h1>{html.escape(str(matter.get('title', 'Matter')))}</h1>"
                        f"<pre>{html.escape(json.dumps(matter, default=_json_safe, indent=2))}</pre>"
                        f"</body></html>")
                    bundle.writestr(f"{prefix}/matter.html", html_document)
                    if matter.get("draft"):
                        bundle.writestr(f"{prefix}/draft.txt", str(matter["draft"]))
                    for document in matter.get("uploaded_documents") or []:
                        if document.get("storage_path"):
                            filename = secure_filename(
                                document.get("filename") or document.get("record_id") or "document")
                            with bundle.open(f"{prefix}/files/{filename}", "w") as destination:
                                download_to_file(document["storage_path"], destination)
        storage_path = f"users/{uid}/exports/{job_id}.zip"
        upload_file_object(archive, storage_path, "application/zip")
        return {"storage_path": storage_path}
    finally:
        archive.close()
