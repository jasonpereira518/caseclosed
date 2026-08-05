"""Cloud Tasks transport with an inline development fallback."""
import json
import threading

import config


def enqueue_job(matter_id: str, job_id: str, task_suffix: str = ""):
    if config.TASKS_MODE == "inline":
        from services.worker import process_job
        def run_inline():
            for _ in range(config.JOB_MAX_ATTEMPTS):
                result = process_job(matter_id, job_id)
                if not result or result.get("status") != "queued":
                    break
        thread = threading.Thread(target=run_inline, daemon=True,
                                  name=f"caseclosed-{job_id[:18]}")
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
    body = json.dumps({"matter_id": matter_id, "job_id": job_id}).encode()
    task_name = job_id + (f"-{task_suffix}" if task_suffix else "")
    task = {"name": client.task_path(config.TASKS_PROJECT_ID, config.TASKS_LOCATION,
                                     config.TASKS_QUEUE, task_name),
            "http_request": {"http_method": tasks_v2.HttpMethod.POST,
                "url": config.TASKS_WORKER_URL, "headers": {"Content-Type": "application/json"},
                "body": body, "oidc_token": {"service_account_email": config.TASKS_SERVICE_ACCOUNT,
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
