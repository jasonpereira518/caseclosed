"""Background job dispatcher."""
import logging
import time

import config

from services.chat_orchestrator import JobCancelled, process_chat_job
from services.jobs import claim_job, get_job_internal, update_job
from services.document_ingestion import cleanup_document_source, ingest_document_job
from services.matters import patch_document


def process_job(matter_id: str, job_id: str) -> dict | None:
    started = time.monotonic()
    claimed = claim_job(matter_id, job_id)
    if not claimed or claimed.get("status") != "running":
        return claimed
    _, data = get_job_internal(matter_id, job_id)
    logging.info("job_started job_id=%s matter_id=%s kind=%s attempt=%s",
                 job_id, matter_id, data.get("kind"), data.get("attempts"))
    try:
        kind = data.get("kind")
        if kind == "chat":
            result = process_chat_job(matter_id, job_id, data)
        elif kind == "document_ingest":
            update_job(matter_id, job_id, progress=15, stage="extracting_text")
            result = ingest_document_job(matter_id, job_id, data)
            cleanup_document_source(data)
        else:
            raise ValueError(f"unsupported job kind: {kind}")
        completed = update_job(matter_id, job_id, status="succeeded", progress=100,
                               stage="complete", result=result, error=None)
        logging.info("job_succeeded job_id=%s kind=%s duration_ms=%s", job_id, kind,
                     round((time.monotonic() - started) * 1000))
        return completed
    except JobCancelled:
        if data.get("kind") == "document_ingest":
            cleanup_document_source(data)
            payload = data.get("payload") or {}
            try:
                patch_document(matter_id, str(data.get("requested_by") or ""),
                               str(payload.get("document_id") or ""),
                               {"status": "cancelled", "error": None})
            except Exception:
                logging.exception("Could not mark cancelled document for job %s", job_id)
        return update_job(matter_id, job_id, status="cancelled", stage="cancelled", error=None)
    except Exception as exc:
        logging.exception("job_failed job_id=%s kind=%s duration_ms=%s", job_id,
                          data.get("kind"), round((time.monotonic() - started) * 1000))
        error = {"code": "job_failed", "message": str(exc)[:500]}
        retrying = int(data.get("attempts", 1)) < config.JOB_MAX_ATTEMPTS
        if data.get("kind") == "document_ingest":
            payload = data.get("payload") or {}
            try:
                patch_document(matter_id, str(data.get("requested_by") or ""),
                               str(payload.get("document_id") or ""),
                               {"status": "retrying" if retrying else "failed",
                                "error": error["message"]})
            except Exception:
                logging.exception("Could not mark failed document for job %s", job_id)
        if retrying:
            return update_job(matter_id, job_id, status="queued", stage="retrying", error=error)
        if data.get("kind") == "document_ingest":
            cleanup_document_source(data)
        return update_job(matter_id, job_id, status="failed", stage="failed", error=error)
