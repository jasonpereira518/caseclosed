"""Durable scheduling for workspace-scoped matter jobs and account jobs.

Both job kinds share one Firestore-transaction status machine and status
vocabulary (queued/running/succeeded/failed/cancelled). Matter jobs live at
<workspace>/matters/<matter_id>/jobs/<job_id>; account jobs live at
users/<uid>/jobs/<job_id> -- each scoped under the entity that owns them,
so ownership is encoded in the document path rather than a filtered query.
"""

from __future__ import annotations

import hashlib
import uuid

import config
from google.cloud import firestore as gc_firestore
from google.api_core.exceptions import AlreadyExists
from services.firestore import get_firestore_client
from services.matters import require_matter
from services.tenancy import now


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset({"queued"})
_PUBLIC_FIELDS = ("kind", "status", "progress", "stage", "result", "error", "attempts",
                  "created_at", "updated_at", "finished_at")


def deterministic_job_id(scope_id: str, kind: str, idempotency_key: str) -> str:
    raw = f"{scope_id}:{kind}:{idempotency_key}".encode("utf-8")
    return "job-" + hashlib.sha256(raw).hexdigest()[:32]


def _serialize_timestamps(result: dict) -> dict:
    for key in ("created_at", "updated_at", "finished_at"):
        if hasattr(result.get(key), "isoformat"):
            result[key] = result[key].isoformat()
    return result


def _public(data: dict, job_id: str, matter_id: str) -> dict:
    result = {key: data.get(key) for key in _PUBLIC_FIELDS if key in data}
    result = _serialize_timestamps(result)
    result.update({"job_id": str(job_id), "matter_id": str(matter_id)})
    return result


def _public_account(data: dict, job_id: str, uid: str) -> dict:
    result = {key: data.get(key) for key in _PUBLIC_FIELDS if key in data}
    result = _serialize_timestamps(result)
    result.update({"job_id": str(job_id), "uid": str(uid)})
    return result


def _new_job_data(kind: str, payload: dict, key: str, owner_field: str, owner_value: str,
                  extra: dict | None = None) -> dict:
    timestamp = now()
    data = {"kind": kind, "status": "queued", "progress": 0, "stage": "queued",
            "payload": dict(payload or {}), "result": None, "error": None, "attempts": 0,
            owner_field: str(owner_value), "idempotency_key": key or None,
            "cancel_requested": False, "created_at": timestamp, "updated_at": timestamp}
    if extra:
        data.update(extra)
    return data


def _claim(ref, build_public):
    """Shared transactional queued->running status flip for any job ref."""
    transaction = get_firestore_client().transaction()

    @gc_firestore.transactional
    def claim(txn):
        snap = ref.get(transaction=txn)
        data = snap.to_dict() or {}
        if data.get("status") not in ACTIVE_STATUSES:
            return None
        timestamp = now()
        if data.get("cancel_requested"):
            patch = {"status": "cancelled", "stage": "cancelled", "updated_at": timestamp,
                     "finished_at": timestamp}
        else:
            attempts = int(data.get("attempts", 0)) + 1
            if attempts > config.JOB_MAX_ATTEMPTS:
                patch = {"status": "failed", "stage": "failed", "updated_at": timestamp,
                         "finished_at": timestamp,
                         "error": {"code": "attempts_exhausted",
                                   "message": "Job retry limit reached."}}
            else:
                patch = {"status": "running", "stage": "starting", "updated_at": timestamp,
                         "progress": max(1, int(data.get("progress", 0))), "attempts": attempts}
        txn.set(ref, patch, merge=True)
        data.update(patch)
        return build_public(data)

    return claim(transaction)


def _update(ref, data: dict, changes: dict) -> dict:
    allowed = {"status", "progress", "stage", "result", "error", "attempts", "cancel_requested"}
    patch = {key: value for key, value in changes.items() if key in allowed}
    patch["updated_at"] = now()
    if patch.get("status") in TERMINAL_STATUSES:
        patch["finished_at"] = now()
    ref.set(patch, merge=True)
    data.update(patch)
    return data


# ---------------------------------------------------------------------------
# Matter-scoped jobs (chat, document_ingest)
# ---------------------------------------------------------------------------

def _job_ref(matter_ref, job_id: str):
    return matter_ref.collection("jobs").document(str(job_id))


def create_job(matter_id: str, uid: str, kind: str, payload: dict,
               idempotency_key: str | None = None) -> tuple[dict, bool]:
    workspace_id, matter_ref, _ = require_matter(str(matter_id), str(uid))
    key = (idempotency_key or "").strip()
    job_id = deterministic_job_id(matter_id, kind, key) if key else f"job-{uuid.uuid4().hex}"
    ref = _job_ref(matter_ref, job_id)
    data = _new_job_data(kind, payload, key, "requested_by", uid,
                         extra={"workspace_id": workspace_id, "matter_id": str(matter_id)})
    try:
        ref.create(data)
    except AlreadyExists:
        existing = ref.get()
        return _public(existing.to_dict() or {}, job_id, matter_id), False
    return _public(data, job_id, matter_id), True


def get_job(matter_id: str, job_id: str, uid: str) -> dict | None:
    _, matter_ref, _ = require_matter(str(matter_id), str(uid))
    snap = _job_ref(matter_ref, job_id).get()
    return _public(snap.to_dict() or {}, job_id, matter_id) if snap.exists else None


def get_job_internal(matter_id: str, job_id: str):
    from services.matters import locate_matter
    _, matter_ref = locate_matter(str(matter_id))
    if not matter_ref:
        return None, None
    ref = _job_ref(matter_ref, job_id)
    snap = ref.get()
    return (ref, snap.to_dict() or {}) if snap.exists else (None, None)


def update_job(matter_id: str, job_id: str, **changes) -> dict | None:
    ref, data = get_job_internal(matter_id, job_id)
    if not ref:
        return None
    data = _update(ref, data, changes)
    return _public(data, job_id, matter_id)


def claim_job(matter_id: str, job_id: str) -> dict | None:
    ref, _ = get_job_internal(matter_id, job_id)
    if not ref:
        return None
    return _claim(ref, lambda data: _public(data, job_id, matter_id))


def cancel_job(matter_id: str, job_id: str, uid: str) -> dict | None:
    job = get_job(matter_id, job_id, uid)
    if not job:
        return None
    if job["status"] in TERMINAL_STATUSES:
        return job
    if job["status"] == "queued":
        return update_job(matter_id, job_id, status="cancelled", stage="cancelled")
    return update_job(matter_id, job_id, cancel_requested=True, stage="cancelling")


def retry_job(matter_id: str, job_id: str, uid: str) -> dict | None:
    job = get_job(matter_id, job_id, uid)
    if (not job or job["status"] not in {"failed", "cancelled"}
            or job.get("kind") == "document_ingest"):
        return None
    return update_job(matter_id, job_id, status="queued", progress=0, stage="queued",
                      error=None, result=None, cancel_requested=False, attempts=0)


def cancellation_requested(matter_id: str, job_id: str) -> bool:
    _, data = get_job_internal(matter_id, job_id)
    return not data or bool(data.get("cancel_requested"))


# ---------------------------------------------------------------------------
# Account-scoped jobs (account_export)
# ---------------------------------------------------------------------------

def _account_job_ref(uid: str, job_id: str):
    return (get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION)
            .document(str(uid)).collection("jobs").document(str(job_id)))


def create_account_job(uid: str, kind: str, payload: dict,
                       idempotency_key: str | None = None) -> tuple[dict, bool]:
    key = (idempotency_key or "").strip()
    job_id = deterministic_job_id(str(uid), kind, key) if key else f"job-{uuid.uuid4().hex}"
    ref = _account_job_ref(uid, job_id)
    data = _new_job_data(kind, payload, key, "uid", uid)
    try:
        ref.create(data)
    except AlreadyExists:
        existing = ref.get()
        return _public_account(existing.to_dict() or {}, job_id, uid), False
    return _public_account(data, job_id, uid), True


def get_account_job_internal(uid: str, job_id: str):
    ref = _account_job_ref(uid, job_id)
    snap = ref.get()
    return (ref, snap.to_dict() or {}) if snap.exists else (None, None)


def get_account_job(uid: str, job_id: str) -> dict | None:
    ref, data = get_account_job_internal(uid, job_id)
    return _public_account(data, job_id, uid) if ref else None


def update_account_job(uid: str, job_id: str, **changes) -> dict | None:
    ref, data = get_account_job_internal(uid, job_id)
    if not ref:
        return None
    data = _update(ref, data, changes)
    return _public_account(data, job_id, uid)


def claim_account_job(uid: str, job_id: str) -> dict | None:
    ref, _ = get_account_job_internal(uid, job_id)
    if not ref:
        return None
    return _claim(ref, lambda data: _public_account(data, job_id, uid))
