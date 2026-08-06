"""Cloud Tasks transport with an inline development fallback.

Both matter-scoped jobs (chat, document_ingest) and account-scoped jobs
(account_export) share this transport and land on the single
/internal/jobs/run worker entrypoint; the request body's "scope" field
tells the worker which job kernel (matter or account) to dispatch through.
"""
import json
import threading

import config


def enqueue_job(matter_id: str, job_id: str, task_suffix: str = ""):
    return _enqueue({"matter_id": matter_id, "job_id": job_id}, job_id, task_suffix)


def enqueue_account_job(uid: str, job_id: str, task_suffix: str = ""):
    return _enqueue({"uid": uid, "job_id": job_id, "scope": "account"},
                    f"account-{job_id}", task_suffix)


def _run_inline(body: dict):
    if body.get("scope") == "account":
        from services.worker import process_account_job
        return process_account_job(body["uid"], body["job_id"])
    from services.worker import process_job
    return process_job(body["matter_id"], body["job_id"])


def _enqueue(body: dict, task_name: str, task_suffix: str):
    if config.TASKS_MODE == "inline":
        def run_inline():
            for _ in range(config.JOB_MAX_ATTEMPTS):
                result = _run_inline(body)
                if not result or result.get("status") != "queued":
                    break
        thread = threading.Thread(target=run_inline, daemon=True,
                                  name=f"caseclosed-{body['job_id'][:18]}")
        thread.start()
        return {"transport": "inline"}
    if config.TASKS_MODE != "cloud":
        raise RuntimeError("TASKS_MODE must be 'inline' or 'cloud'")
    if not all((config.TASKS_PROJECT_ID, config.TASKS_LOCATION, config.TASKS_QUEUE,
                config.TASKS_WORKER_URL, config.TASKS_SERVICE_ACCOUNT)):
        raise RuntimeError("Cloud Tasks configuration is incomplete")
    from google.cloud import tasks_v2
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(config.TASKS_PROJECT_ID, config.TASKS_LOCATION, config.TASKS_QUEUE)
    request_body = json.dumps(body).encode()
    full_task_name = task_name + (f"-{task_suffix}" if task_suffix else "")
    task = {"name": client.task_path(config.TASKS_PROJECT_ID, config.TASKS_LOCATION,
                                     config.TASKS_QUEUE, full_task_name),
            "http_request": {"http_method": tasks_v2.HttpMethod.POST,
                "url": config.TASKS_WORKER_URL, "headers": {"Content-Type": "application/json"},
                "body": request_body, "oidc_token": {"service_account_email": config.TASKS_SERVICE_ACCOUNT,
                                               "audience": config.TASKS_WORKER_AUDIENCE}}}
    if config.INTERNAL_WORKER_TOKEN:
        task["http_request"]["headers"]["X-Worker-Token"] = config.INTERNAL_WORKER_TOKEN
    try:
        response = client.create_task(parent=parent, task=task)
    except Exception as exc:
        if exc.__class__.__name__ != "AlreadyExists":
            raise
        return {"transport": "cloud", "deduplicated": True}
    return {"transport": "cloud", "task_name": response.name}
