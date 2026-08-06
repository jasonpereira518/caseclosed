"""Durable scheduling for account jobs and workspace-scoped matter jobs."""

from __future__ import annotations

import hashlib
import uuid

import config
from google.cloud import firestore as gc_firestore
from google.api_core.exceptions import AlreadyExists
from services.firestore import get_firestore_client
from services.matters import require_matter
from services.tenancy import now


def enqueue_account_job(job_id: str):
    if config.TASKS_MODE == "inline":
        return False
    if config.TASKS_MODE != "cloud":
        raise RuntimeError("TASKS_MODE must be 'inline' or 'cloud'")
    if not all((config.TASKS_PROJECT_ID, config.TASKS_LOCATION, config.TASKS_QUEUE,
                config.APP_BASE_URL, config.TASKS_SERVICE_ACCOUNT,
                config.TASKS_WORKER_AUDIENCE)):
        raise RuntimeError("Cloud Tasks configuration is incomplete")
    from google.cloud import tasks_v2
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(config.TASKS_PROJECT_ID, config.TASKS_LOCATION, config.TASKS_QUEUE)
    task = {
        "name": client.task_path(config.TASKS_PROJECT_ID, config.TASKS_LOCATION,
                                 config.TASKS_QUEUE, f"account-{job_id}"),
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{config.APP_BASE_URL.rstrip('/')}/internal/account-jobs/{job_id}",
            "oidc_token": {
                "service_account_email": config.TASKS_SERVICE_ACCOUNT,
                "audience": config.TASKS_WORKER_AUDIENCE,
            },
        }
    }
    if config.INTERNAL_WORKER_TOKEN:
        task["http_request"]["headers"] = {"X-Worker-Token": config.INTERNAL_WORKER_TOKEN}
    try:
        client.create_task(parent=parent, task=task)
    except AlreadyExists:
        pass
    return True


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset({"queued"})


def deterministic_job_id(matter_id: str, kind: str, idempotency_key: str) -> str:
    raw = f"{matter_id}:{kind}:{idempotency_key}".encode("utf-8")
    return "job-" + hashlib.sha256(raw).hexdigest()[:32]


def _job_ref(matter_ref, job_id: str):
    return matter_ref.collection("jobs").document(str(job_id))


def create_job(matter_id: str, uid: str, kind: str, payload: dict,
               idempotency_key: str | None = None) -> tuple[dict, bool]:
    workspace_id, matter_ref, _ = require_matter(str(matter_id), str(uid))
    key = (idempotency_key or "").strip()
    job_id = deterministic_job_id(matter_id, kind, key) if key else f"job-{uuid.uuid4().hex}"
    ref = _job_ref(matter_ref, job_id)
    timestamp = now()
    data = {"kind": kind, "status": "queued", "progress": 0, "stage": "queued",
            "payload": dict(payload or {}), "result": None, "error": None, "attempts": 0,
            "requested_by": str(uid), "workspace_id": workspace_id, "matter_id": str(matter_id),
            "idempotency_key": key or None, "cancel_requested": False,
            "created_at": timestamp, "updated_at": timestamp}
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
    allowed = {"status", "progress", "stage", "result", "error", "attempts", "cancel_requested"}
    patch = {key: value for key, value in changes.items() if key in allowed}
    patch["updated_at"] = now()
    if patch.get("status") in TERMINAL_STATUSES:
        patch["finished_at"] = now()
    ref.set(patch, merge=True)
    data.update(patch)
    return _public(data, job_id, matter_id)


def claim_job(matter_id: str, job_id: str) -> dict | None:
    ref, _ = get_job_internal(matter_id, job_id)
    if not ref:
        return None
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
        return _public(data, job_id, matter_id)

    return claim(transaction)


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


def _public(data: dict, job_id: str, matter_id: str) -> dict:
    result = {key: data.get(key) for key in (
        "kind", "status", "progress", "stage", "result", "error", "attempts",
        "created_at", "updated_at", "finished_at") if key in data}
    for key in ("created_at", "updated_at", "finished_at"):
        if hasattr(result.get(key), "isoformat"):
            result[key] = result[key].isoformat()
    result.update({"job_id": str(job_id), "matter_id": str(matter_id)})
    return result
