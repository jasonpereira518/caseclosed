"""Job status/control API and private worker callback."""
import hmac
import uuid

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import config
from services.jobs import cancel_job, get_job, retry_job
from services.task_queue import enqueue_job
from services.tenancy import AuthorizationError
from services.worker import process_account_job, process_job
from services.legal_corpus import sync_configured_sources
from services.oidc import verify_service_account_request, verify_worker_request


jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/api/matters/<matter_id>/jobs/<job_id>", methods=["GET"])
@login_required
def job_status(matter_id, job_id):
    try:
        job = get_job(matter_id, job_id, str(current_user.get_id()))
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    return (jsonify(job), 200) if job else (jsonify({"error": "job not found"}), 404)


@jobs_bp.route("/api/matters/<matter_id>/jobs/<job_id>", methods=["DELETE"])
@login_required
def job_cancel(matter_id, job_id):
    try:
        job = cancel_job(matter_id, job_id, str(current_user.get_id()))
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    return (jsonify(job), 202) if job else (jsonify({"error": "job not found"}), 404)


@jobs_bp.route("/api/matters/<matter_id>/jobs/<job_id>/retry", methods=["POST"])
@login_required
def job_retry(matter_id, job_id):
    try:
        job = retry_job(matter_id, job_id, str(current_user.get_id()))
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    if not job:
        return jsonify({"error": "job is not retryable"}), 409
    enqueue_job(matter_id, job_id, task_suffix=f"manual-{uuid.uuid4().hex[:10]}")
    return jsonify(job), 202


@jobs_bp.route("/internal/jobs/run", methods=["POST"])
def run_job():
    if config.TASKS_MODE != "cloud" or not verify_worker_request(request):
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return jsonify({"error": "job_id is required"}), 400
    if payload.get("scope") == "account":
        uid = str(payload.get("uid") or "")
        if not uid:
            return jsonify({"error": "uid is required"}), 400
        job = process_account_job(uid, job_id)
    else:
        matter_id = str(payload.get("matter_id") or "")
        if not matter_id:
            return jsonify({"error": "matter_id is required"}), 400
        job = process_job(matter_id, job_id)
    status_code = 503 if job and job.get("status") == "queued" and job.get("stage") == "retrying" else 200
    return jsonify(job or {"status": "ignored"}), status_code


@jobs_bp.route("/internal/legal-corpus/sync", methods=["POST"])
def sync_legal_corpus():
    supplied = request.headers.get("X-Legal-Corpus-Token", "")
    token_ok = bool(config.LEGAL_CORPUS_SYNC_TOKEN and hmac.compare_digest(
        supplied, config.LEGAL_CORPUS_SYNC_TOKEN))
    oidc_ok = bool(verify_service_account_request(
        request, expected_email=config.LEGAL_CORPUS_SYNC_SERVICE_ACCOUNT,
        audience=config.LEGAL_CORPUS_SYNC_AUDIENCE))
    if not (token_ok or oidc_ok):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(sync_configured_sources())
