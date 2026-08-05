"""Tenant-safe indexing, retrieval, and citation validation."""
from __future__ import annotations

import hashlib
import logging
import re
import config
from services.firestore import get_firestore_client
from services.matters import require_matter
from services.jurisdictions import normalize_jurisdiction
from services.tenancy import now


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]{1,}", re.I)
CHUNK_CHARS = 3_500
CHUNK_OVERLAP = 350


def chunk_text(text: str, *, max_chars: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    value = re.sub(r"\r\n?", "\n", str(text or "")).strip()
    if not value:
        return []
    chunks, start = [], 0
    while start < len(value):
        end = min(len(value), start + max_chars)
        if end < len(value):
            boundary = max(value.rfind("\n\n", start, end), value.rfind(". ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunks.append(value[start:end].strip())
        if end >= len(value):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def index_matter_document(matter_id: str, uid: str, document_id: str,
                          title: str, text: str, *, source_type="uploaded_document",
                          included: bool = False) -> int:
    workspace_id, matter_ref, _ = require_matter(str(matter_id), str(uid))
    collection = matter_ref.collection("knowledge_chunks")
    prefix = f"{document_id}-"
    for snap in collection.stream():
        if snap.id.startswith(prefix):
            snap.reference.delete()
    chunks = chunk_text(text)
    for position, content in enumerate(chunks):
        chunk_id = f"{document_id}-{position:05d}"
        data = {
            "source_id": chunk_id, "document_id": str(document_id), "source_type": source_type,
            "title": str(title or "Untitled document"), "text": content,
            "locator": f"chunk {position + 1}", "position": position,
            "workspace_id": workspace_id, "matter_id": str(matter_id),
            "owner_id": str(uid), "included": bool(included), "updated_at": now(),
        }
        collection.document(chunk_id).set(data)
        _vector_upsert(config.VECTOR_PRIVATE_COLLECTION, chunk_id, data)
    return len(chunks)


def index_legal_source(source_id: str, title: str, text: str, *, jurisdiction: str,
                       canonical_url: str, source_type: str = "statute") -> int:
    """Upsert a shared legal source after an official-source adapter validates it."""
    collection = get_firestore_client().collection(config.FIRESTORE_LEGAL_SOURCES_COLLECTION)
    prefix = "law-" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:20] + "-"
    for snap in collection.stream():
        if snap.id.startswith(prefix):
            snap.reference.delete()
    chunks = chunk_text(text)
    for position, content in enumerate(chunks):
        chunk_id = f"{prefix}{position:05d}"
        data = {"source_id": chunk_id, "legal_source_id": source_id,
                "source_type": source_type, "title": title, "text": content,
                "locator": f"chunk {position + 1}", "position": position,
                "jurisdiction": jurisdiction, "canonical_url": canonical_url,
                "updated_at": now()}
        collection.document(chunk_id).set(data)
        _vector_upsert(config.VECTOR_LEGAL_COLLECTION, chunk_id, data)
    return len(chunks)


def delete_matter_document_index(matter_id: str, uid: str, document_id: str):
    _, matter_ref, _ = require_matter(str(matter_id), str(uid))
    prefix = f"{document_id}-"
    for snap in matter_ref.collection("knowledge_chunks").stream():
        if snap.id.startswith(prefix):
            snap.reference.delete()
            _vector_delete(config.VECTOR_PRIVATE_COLLECTION, snap.id)


def set_matter_document_included(matter_id: str, uid: str, document_id: str, included: bool):
    _, matter_ref, _ = require_matter(str(matter_id), str(uid))
    prefix = f"{document_id}-"
    for snap in matter_ref.collection("knowledge_chunks").stream():
        if not snap.id.startswith(prefix):
            continue
        data = snap.to_dict() or {}
        data.update({"included": bool(included), "updated_at": now()})
        snap.reference.set({"included": bool(included), "updated_at": now()}, merge=True)
        _vector_upsert(config.VECTOR_PRIVATE_COLLECTION, snap.id, data)


def retrieve(matter_id: str, uid: str, query: str, *, jurisdiction: str | None = None,
             top_k: int | None = None) -> list[dict]:
    """Retrieve private matter evidence plus shared law with hard tenant filters."""
    workspace_id, matter_ref, _ = require_matter(str(matter_id), str(uid))
    limit = max(1, min(int(top_k or config.RETRIEVAL_TOP_K), 20))
    jurisdiction = normalize_jurisdiction(jurisdiction)
    if config.VECTOR_SEARCH_ENABLED:
        try:
            private = _vector_search(config.VECTOR_PRIVATE_COLLECTION, query, limit, {
                "workspace_id": workspace_id, "matter_id": str(matter_id), "included": True,
            })
            legal = _vector_search(config.VECTOR_LEGAL_COLLECTION, query, limit, {
                "jurisdiction": jurisdiction,
            } if jurisdiction else {})
            return _dedupe_rank([*private, *legal], query, limit)
        except Exception as exc:
            # Local/emergency fallback is intentionally tenant-filtered below.
            logging.warning("Vector retrieval failed; using Firestore fallback: %s", exc)
    candidates = [item for item in (snap.to_dict() or {}
                  for snap in matter_ref.collection("knowledge_chunks").stream())
                  if item.get("included") is not False]
    for snap in get_firestore_client().collection(config.FIRESTORE_LEGAL_SOURCES_COLLECTION).stream():
        item = snap.to_dict() or {}
        if jurisdiction and item.get("jurisdiction") not in {jurisdiction, "federal"}:
            continue
        candidates.append(item)
    return _dedupe_rank(candidates, query, limit)


def _dedupe_rank(items: list[dict], query: str, limit: int) -> list[dict]:
    terms = set(token.lower() for token in TOKEN_RE.findall(query))
    ranked, seen = [], set()
    for raw in items:
        text = str(raw.get("text") or "")
        source_id = str(raw.get("source_id") or raw.get("canonical_url") or "")
        signature = (source_id, raw.get("locator"), text[:80])
        if not text or signature in seen:
            continue
        seen.add(signature)
        words = set(token.lower() for token in TOKEN_RE.findall(text))
        score = len(terms & words) / max(1, len(terms))
        if score or not terms:
            item = dict(raw)
            item["retrieval_score"] = round(score, 4)
            ranked.append(item)
    ranked.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return ranked[:limit]


def citation_for(source: dict, *, quote: str = "") -> dict:
    return {
        "source_id": str(source.get("source_id") or ""),
        "source_type": str(source.get("source_type") or "unknown"),
        "title": str(source.get("title") or "Untitled source"),
        "locator": str(source.get("locator") or ""),
        "url": str(source.get("canonical_url") or source.get("url") or ""),
        "quote": str(quote or "")[:400],
    }


def validate_citations(citations: list, sources: list[dict]) -> list[dict]:
    """Drop model-provided citations that do not map to retrieved evidence."""
    allowed = {}
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if source_id:
            allowed[source_id] = source
    valid, seen = [], set()
    for raw in citations or []:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("source_id") or "")
        if source_id not in allowed or source_id in seen:
            continue
        seen.add(source_id)
        source = allowed[source_id]
        quote = str(raw.get("quote") or "")
        if quote and quote.lower() not in str(source.get("text") or "").lower():
            quote = ""
        valid.append(citation_for(source, quote=quote))
    return valid


def _parent(collection_id: str) -> str:
    return (f"projects/{config.VECTOR_SEARCH_PROJECT_ID}/locations/"
            f"{config.VECTOR_SEARCH_LOCATION}/collections/{collection_id}")


def _vector_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "d-" + cleaned
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    return f"{cleaned[:53]}-{digest}"[:63].rstrip("-")


def _vector_upsert(collection_id: str, object_id: str, data: dict):
    if not config.VECTOR_SEARCH_ENABLED:
        return
    from google.cloud import vectorsearch_v1
    from google.api_core.exceptions import AlreadyExists
    from google.protobuf.field_mask_pb2 import FieldMask
    client = vectorsearch_v1.DataObjectServiceClient()
    vector_id = _vector_id(object_id)
    try:
        client.create_data_object(parent=_parent(collection_id),
                                  data_object=vectorsearch_v1.DataObject(data=data),
                                  data_object_id=vector_id)
    except AlreadyExists:
        client.update_data_object(
            data_object=vectorsearch_v1.DataObject(
                name=f"{_parent(collection_id)}/dataObjects/{vector_id}", data=data),
            update_mask=FieldMask(paths=["data"]),
        )


def _vector_delete(collection_id: str, object_id: str):
    if not config.VECTOR_SEARCH_ENABLED:
        return
    from google.cloud import vectorsearch_v1
    from google.api_core.exceptions import NotFound
    client = vectorsearch_v1.DataObjectServiceClient()
    try:
        client.delete_data_object(name=f"{_parent(collection_id)}/dataObjects/{_vector_id(object_id)}")
    except NotFound:
        pass


def _vector_search(collection_id: str, query: str, top_k: int, filters: dict) -> list[dict]:
    from google.cloud import vectorsearch_v1
    client = vectorsearch_v1.DataObjectSearchServiceClient()
    semantic = vectorsearch_v1.SemanticSearch(
        search_text=query, search_field=config.VECTOR_SEARCH_FIELD, task_type="RETRIEVAL_QUERY",
        filter={key: {"$eq": value} for key, value in filters.items() if value is not None},
        top_k=top_k,
        output_fields=["source_id", "source_type", "title", "text", "locator",
                       "canonical_url", "jurisdiction", "workspace_id", "matter_id",
                       "document_id", "legal_source_id"],
    )
    response = client.search_data_objects(request=vectorsearch_v1.SearchDataObjectsRequest(
        parent=_parent(collection_id), semantic_search=semantic))
    results = []
    for item in response:
        obj = getattr(item, "data_object", item)
        results.append(dict(getattr(obj, "data", {}) or {}))
    return results
