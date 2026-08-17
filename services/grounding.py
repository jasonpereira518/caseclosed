"""Grounded answer generation with a closed citation set."""
from __future__ import annotations

import json
import logging

import config
from services.llm import client
from services.retrieval import validate_citations
from utils.helpers import extract_json_object


def answer_from_sources(question: str, sources: list[dict], *, client_role: str | None = None) -> dict:
    if not sources:
        return {
            "answer": "I couldn't find support for that in this matter's documents or the connected legal sources.",
            "citations": [], "grounded": False,
        }
    packets = []
    for source in sources:
        packets.append({
            "source_id": source.get("source_id"), "title": source.get("title"),
            "locator": source.get("locator"), "text": str(source.get("text") or "")[:6000],
        })
    role_line = (
        f"The asking lawyer represents the {client_role} in this matter; frame the analysis "
        "from that side's perspective while staying accurate about weaknesses.\n"
        if client_role else ""
    )
    prompt = (
        "Answer the legal-work question using ONLY the supplied sources. Do not invent law, facts, "
        "citations, or source IDs. Distinguish source facts from cautious analysis. This is legal "
        "information, not a guarantee of outcome. Return strict JSON with keys answer and citations. "
        "Each citation must contain source_id and an optional exact quote found in that source.\n"
        f"{role_line}\n"
        f"QUESTION:\n{question}\n\nSOURCES:\n{json.dumps(packets, ensure_ascii=False)}"
    )
    response = client.chats.create(model=config.CHAT_FAST_MODEL).send_message(prompt)
    parsed = extract_json_object(response.text.strip()) or {}
    answer = str(parsed.get("answer") or "").strip()
    proposed = parsed.get("citations") or []
    citations = validate_citations(proposed, sources)
    if len(citations) != len(proposed):
        logging.warning("grounding_rejected_citations proposed=%s accepted=%s",
                        len(proposed), len(citations))
    if not answer or not citations:
        return {
            "answer": "I couldn't produce a sufficiently supported answer from the retrieved sources.",
            "citations": [], "grounded": False,
        }
    return {"answer": answer, "citations": citations, "grounded": True}
