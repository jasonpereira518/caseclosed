"""Durable Cloud Tasks scheduling for account jobs."""

import config


def enqueue_account_job(job_id: str):
    if not config.CLOUD_TASKS_QUEUE:
        return False
    if not config.PROJECT_ID or not config.JOB_WORKER_SECRET:
        raise RuntimeError("PROJECT_ID and JOB_WORKER_SECRET are required with CLOUD_TASKS_QUEUE")
    from google.cloud import tasks_v2
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(config.PROJECT_ID, config.CLOUD_TASKS_LOCATION, config.CLOUD_TASKS_QUEUE)
    client.create_task(parent=parent, task={
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{config.APP_BASE_URL.rstrip('/')}/internal/account-jobs/{job_id}",
            "headers": {"X-Case-Closed-Worker": config.JOB_WORKER_SECRET},
        }
    })
    return True
