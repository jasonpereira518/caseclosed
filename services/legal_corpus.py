"""Official-law source registry and bounded daily JSON-feed synchronization.

Every jurisdiction is represented in the registry. Source-specific adapters are
deployment configuration because state publishers expose incompatible formats.
Only entries explicitly marked ``official`` are ingested.
"""
from __future__ import annotations

import hashlib

import requests

import config
from services.firestore import get_firestore_client
from services.jurisdictions import JURISDICTIONS
from services.retrieval import index_legal_source
from services.tenancy import now


def ensure_registry() -> dict:
    configured = {str(item.get("jurisdiction", "")).lower(): item
                  for item in config.LEGAL_SOURCE_REGISTRY if isinstance(item, dict)}
    collection = get_firestore_client().collection("legal_source_registry")
    for code, name in JURISDICTIONS.items():
        source = configured.get(code) or {}
        collection.document(code).set({
            "jurisdiction": code, "name": name, "official": bool(source.get("official")),
            "source_url": source.get("url"),
            "status": "configured" if source.get("official") and source.get("url") else "configuration_required",
            "updated_at": now(),
        }, merge=True)
    return {"jurisdictions": len(JURISDICTIONS), "configured": len(configured)}


def sync_configured_sources(limit: int | None = None) -> dict:
    ensure_registry()
    remaining = max(1, int(limit or config.LEGAL_CORPUS_DAILY_LIMIT))
    report = {"processed": 0, "chunks": 0, "sources": [], "errors": []}
    for source in config.LEGAL_SOURCE_REGISTRY:
        if remaining <= 0:
            break
        try:
            processed, chunks = _sync_source(source, remaining)
            remaining -= processed
            report["processed"] += processed
            report["chunks"] += chunks
            report["sources"].append({"jurisdiction": source.get("jurisdiction"),
                                      "processed": processed, "chunks": chunks})
        except Exception as exc:
            report["errors"].append({"jurisdiction": source.get("jurisdiction"),
                                     "message": str(exc)[:300]})
    return report


def _sync_source(source: dict, limit: int) -> tuple[int, int]:
    jurisdiction = str(source.get("jurisdiction") or "").lower()
    url = str(source.get("url") or "")
    if jurisdiction not in JURISDICTIONS or not source.get("official") or not url.startswith("https://"):
        raise ValueError("source must identify a supported jurisdiction and an official HTTPS URL")
    response = requests.get(url, timeout=30, headers={"User-Agent": "CaseClosedLegalCorpus/1.0"})
    response.raise_for_status()
    records = _path(response.json(), source.get("records_path"))
    if not isinstance(records, list):
        raise ValueError("configured records_path did not resolve to a list")
    id_field = source.get("id_field", "id")
    title_field = source.get("title_field", "title")
    text_field = source.get("text_field", "text")
    url_field = source.get("canonical_url_field", "url")
    processed = chunks = 0
    for record in records[:limit]:
        if not isinstance(record, dict):
            continue
        text = str(record.get(text_field) or "").strip()
        if not text:
            continue
        raw_id = str(record.get(id_field) or hashlib.sha256(text.encode()).hexdigest())
        source_id = f"{jurisdiction}:{raw_id}"
        canonical = str(record.get(url_field) or source.get("canonical_url") or url)
        chunks += index_legal_source(source_id, str(record.get(title_field) or raw_id), text,
                                     jurisdiction=jurisdiction, canonical_url=canonical,
                                     source_type=str(source.get("source_type") or "statute"))
        processed += 1
    get_firestore_client().collection("legal_source_registry").document(jurisdiction).set({
        "status": "synced", "last_synced_at": now(), "last_record_count": processed,
    }, merge=True)
    return processed, chunks


def _path(value, path):
    for part in str(path or "").split("."):
        if part:
            value = value.get(part) if isinstance(value, dict) else None
    return value
