"""Structured analysis and drafting job bodies, run inside the async job worker.

process_analysis_job is shared by /analyze and /intake (routes/analyze.py,
routes/intake.py), which both queue a "matter_analysis" job against a
matter's description -- the only difference between the two routes is what
populates that description before the job is queued. process_draft_job
backs /draft's "matter_draft" job kind.

Mirrors chat_orchestrator.py's pattern: both run outside Flask request
context, so they read/write matter state through services/matters.py
directly rather than models/context.py's FirestoreBackedDict, which is only
safe to use from an in-request route.
"""
from __future__ import annotations

from services.jobs import update_job
from services.llm import (
    draft_legal_document, extract_case_strength, extract_statutes,
    extract_structured_analysis, extract_timeline,
)
from services.matters import load_matter, patch_matter, replace_matter_records, save_matter


def process_analysis_job(matter_id: str, job_id: str, data: dict) -> dict:
    payload = data.get("payload") or {}
    uid = str(data.get("requested_by") or "")
    matter = load_matter(matter_id, uid) or {}
    supplied_text = str(payload.get("text") or "").strip()
    text = supplied_text or str(matter.get("description") or "").strip()
    if not text:
        raise ValueError("no text available to analyze")

    update_job(matter_id, job_id, progress=20, stage="analyzing")
    analysis = extract_structured_analysis(text)

    update_job(matter_id, job_id, progress=45, stage="building_timeline")
    timeline = extract_timeline(text)
    timeline = timeline if isinstance(timeline, list) else []

    update_job(matter_id, job_id, progress=65, stage="checking_statutes")
    statutes = extract_statutes(text, analysis)

    update_job(matter_id, job_id, progress=85, stage="scoring_strength")
    cases = matter.get("cases") or []
    strength = extract_case_strength(text, analysis, statutes, cases)

    root_updates = {}
    if supplied_text and not str(matter.get("description") or "").strip():
        root_updates["description"] = text
    patch_matter(matter_id, uid, root=root_updates or None,
                state={"analysis": analysis, "statutes": statutes, "strength": strength})
    replace_matter_records(matter_id, uid, "timeline_events", timeline)

    return {"status": "success", "analysis": analysis, "timeline": timeline,
            "statutes": statutes, "strength": strength}


def process_draft_job(matter_id: str, job_id: str, data: dict) -> dict:
    payload = data.get("payload") or {}
    uid = str(data.get("requested_by") or "")
    doc_type = str(payload.get("doc_type") or "memo")
    matter = load_matter(matter_id, uid)
    if matter is None:
        raise PermissionError("matter is unavailable")

    analysis = matter.get("analysis")
    if not analysis:
        description = str(matter.get("description") or "").strip()
        if not description:
            raise ValueError("no case information available")
        update_job(matter_id, job_id, progress=30, stage="analyzing")
        analysis = extract_structured_analysis(description)
        patch_matter(matter_id, uid, state={"analysis": analysis})
        matter["analysis"] = analysis

    update_job(matter_id, job_id, progress=65, stage="drafting_document")
    document = draft_legal_document(matter, doc_type)
    save_matter(matter_id, {"draft": document, "draft_type": doc_type})

    return {"status": "success", "document": document, "doc_type": doc_type}
