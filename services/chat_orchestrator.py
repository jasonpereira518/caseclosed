"""Intent-based chat pipeline executed by the background worker."""
from __future__ import annotations

import re

from services.courtlistener import query_courtlistener
from services.grounding import answer_from_sources
from services.jobs import cancellation_requested, update_job
from services.llm import (
    check_if_more_info_needed, extract_case_strength,
    extract_structured_analysis, extract_timeline, generate_query,
    generate_session_title, grade_case, rerank_cases, summarize_case,
)
from services.matters import append_message, load_matter, patch_matter, replace_matter_records
from services.retrieval import citation_for, retrieve


RESEARCH_RE = re.compile(
    r"\b(find|research|search|look up|precedent|case law|cases supporting|authorit(?:y|ies))\b", re.I)
SUMMARY_RE = re.compile(r"\b(summarize|summary|recap|what (?:do|did) we know)\b", re.I)


def classify_intent(message: str) -> str:
    if RESEARCH_RE.search(message or ""):
        return "legal_research"
    if SUMMARY_RE.search(message or ""):
        return "matter_summary"
    value = (message or "").strip().lower()
    if "?" not in value and not re.match(
            r"^(who|what|when|where|why|how|can|could|should|does|do|is|are)\b", value):
        return "matter_update"
    return "grounded_question"


def process_chat_job(matter_id: str, job_id: str, data: dict) -> dict:
    payload = data.get("payload") or {}
    uid = str(data.get("requested_by") or "")
    message = str(payload.get("message") or "").strip()
    matter = load_matter(matter_id, uid)
    if not matter:
        raise PermissionError("matter is unavailable")

    if matter.get("title") == "New Session":
        try:
            patch_matter(matter_id, uid, root={"title": generate_session_title(message)})
        except Exception:
            pass

    intent = "legal_research" if matter.get("pending_questions") else classify_intent(message)
    update_job(matter_id, job_id, progress=10, stage="routing")
    if intent == "legal_research":
        result = _research(matter_id, job_id, uid, message, matter)
    elif intent == "matter_update":
        result = _update_matter(matter_id, job_id, uid, message, matter)
    else:
        result = _answer(matter_id, job_id, uid, message, matter, intent)
    append_message(matter_id, uid, "assistant", result["message"], metadata={
        "job_id": job_id, "intent": intent, "citations": result.get("citations") or [],
    }, message_id=f"assistant-{job_id}")
    refreshed = load_matter(matter_id, uid) or {}
    result.update({"context_id": matter_id, "matter_id": matter_id,
                   "title": refreshed.get("title") or matter.get("title") or "New Session"})
    return result


def _update_matter(matter_id: str, job_id: str, uid: str, message: str, matter: dict) -> dict:
    update_job(matter_id, job_id, progress=35, stage="updating_matter")
    description = " ".join(filter(None, [str(matter.get("description") or "").strip(), message])).strip()
    analysis = extract_structured_analysis(description)
    patch_matter(matter_id, uid, root={"description": description}, state={"analysis": analysis})
    return {"status": "answer", "intent": "matter_update", "grounded": True,
            "message": "I added that information to the matter record. Ask a question about it or ask me to research authorities when you're ready.",
            "citations": []}


def _answer(matter_id: str, job_id: str, uid: str, message: str,
            matter: dict, intent: str) -> dict:
    update_job(matter_id, job_id, progress=35, stage="retrieving_sources")
    sources = retrieve(matter_id, uid, message,
                       jurisdiction=_jurisdiction(matter.get("analysis") or {},
                                                  matter.get("intake") or {}))
    description = str(matter.get("description") or "").strip()
    if description:
        sources.append({"source_id": "matter-narrative", "source_type": "matter",
                        "title": matter.get("title") or "Matter narrative",
                        "locator": "matter description", "text": description})
    if cancellation_requested(matter_id, job_id):
        raise JobCancelled()
    update_job(matter_id, job_id, progress=65, stage="drafting_answer")
    grounded = answer_from_sources(message, sources,
                                   client_role=str(matter.get("role") or "").strip() or None)
    return {"status": "answer", "intent": intent, "message": grounded["answer"],
            "citations": grounded["citations"], "grounded": grounded["grounded"]}


def _research(matter_id: str, job_id: str, uid: str, message: str, matter: dict) -> dict:
    description = " ".join(filter(None, [str(matter.get("description") or "").strip(), message])).strip()
    analysis = matter.get("analysis") if isinstance(matter.get("analysis"), dict) else {}
    attempts = int(matter.get("clarify_attempts", 0) or 0)
    update_job(matter_id, job_id, progress=18, stage="checking_facts")
    needs_more, questions = check_if_more_info_needed(message, description, analysis)
    questions = list(questions or [])[:5]
    if needs_more and questions and attempts < 2:
        patch_matter(matter_id, uid, root={"description": description,
                     "pending_questions": questions, "clarify_attempts": attempts + 1})
        lines = "\n".join(f"{index + 1}. {question}" for index, question in enumerate(questions))
        return {"status": "clarifying", "intent": "legal_research", "questions": questions,
                "clarify_attempts": attempts + 1,
                "message": f"I need a bit more information:\n\n{lines}\n\nPlease answer these questions in your next message.",
                "citations": []}

    patch_matter(matter_id, uid, root={"description": description,
                 "pending_questions": [], "clarify_attempts": 0})
    analysis = extract_structured_analysis(description)
    summary = summarize_case(description)
    patch_matter(matter_id, uid, state={"analysis": analysis, "summary": summary})
    update_job(matter_id, job_id, progress=32, stage="searching_case_law")

    cases, seen, queries = [], set(), []
    for _ in range(3):
        if cancellation_requested(matter_id, job_id):
            raise JobCancelled()
        query = str(generate_query(summary, analysis) or "").strip()
        if not query or query in queries:
            continue
        queries.append(query)
        for case in query_courtlistener(query):
            key = case.get("pdf_link") or case.get("citation") or case.get("title")
            if key and key not in seen:
                seen.add(key)
                cases.append(case)

    update_job(matter_id, job_id, progress=55, stage="grading_authorities")
    results = []
    for case in cases:
        grading = grade_case(summary, case.get("title", ""), case.get("snippet", ""), analysis)
        score = int(grading.get("score", 0) or 0)
        if score >= 15:
            results.append({**case, "initial_score": score, "relevance_score": score,
                            "relevance_reason": grading.get("reason", ""),
                            "relevance_dimensions": grading.get("dimensions", {})})
    if len(results) > 3:
        reranked = rerank_cases(summary, analysis, results)
        if isinstance(reranked, list):
            results = reranked
    results.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    results = [_compact_case(item) for item in results[:20]]

    update_job(matter_id, job_id, progress=75, stage="building_matter_analysis")
    timeline = extract_timeline(description)
    timeline = timeline if isinstance(timeline, list) else []
    legal_sources = retrieve(matter_id, uid, summary,
                             jurisdiction=_jurisdiction(analysis, matter.get("intake") or {}),
                             top_k=12)
    statutes = [_statute_from_source(source) for source in legal_sources
                if source.get("source_type") in {"statute", "regulation", "rule"}]
    strength = extract_case_strength(description, analysis, statutes, results)
    replace_matter_records(matter_id, uid, "cases", results)
    replace_matter_records(matter_id, uid, "timeline_events", timeline)
    patch_matter(matter_id, uid, state={"analysis": analysis, "summary": summary,
                 "search_query": "\n\n".join(queries), "statutes": statutes, "strength": strength})
    citations = [citation_for({
        "source_id": str(case.get("cluster_id") or case.get("citation") or f"case-{index}"),
        "source_type": "case_law", "title": case.get("title"),
        "locator": case.get("citation"), "canonical_url": case.get("pdf_link"),
    }) for index, case in enumerate(results)]
    citations.extend(citation_for(source) for source in legal_sources
                     if source.get("source_type") in {"statute", "regulation", "rule"})
    message_text = (f"Found {len(results)} relevant authorities. Review the Authority panel."
                    if results else "I did not find a sufficiently relevant authority for this search.")
    return {"status": "results", "intent": "legal_research", "message": message_text,
            "summary": summary, "analysis": analysis, "timeline": timeline,
            "statutes": statutes, "strength": strength, "cases": results,
            "query": "\n\n".join(queries), "citations": citations}


def _jurisdiction(analysis: dict, intake: dict | None = None) -> str | None:
    """Intake's explicitly selected jurisdiction outranks model extraction."""
    declared = str((intake or {}).get("jurisdiction") or "").strip()
    if declared:
        return declared
    value = analysis.get("jurisdiction") or analysis.get("jurisdictions")
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value else None


def _statute_from_source(source: dict) -> dict:
    return {"code": source.get("locator") or source.get("legal_source_id") or "",
            "title": source.get("title") or "Untitled authority",
            "jurisdiction": source.get("jurisdiction") or "",
            "description": str(source.get("text") or "")[:600],
            "relevance": "Retrieved from the configured official legal corpus.",
            "source_id": source.get("source_id"),
            "url": source.get("canonical_url") or ""}


def _compact_case(case: dict) -> dict:
    value = dict(case)
    for key, limit in {"snippet": 5_000, "relevance_reason": 2_000,
                       "description": 5_000}.items():
        if key in value:
            value[key] = str(value.get(key) or "")[:limit]
    return value


class JobCancelled(RuntimeError):
    pass
