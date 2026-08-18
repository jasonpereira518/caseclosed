"""Normalized Firestore persistence for legal matters.

The route layer still consumes an aggregate dictionary for compatibility with
the existing UI.  This module assembles that view from bounded Firestore
documents and writes lists into subcollections so a matter cannot hit the
single-document 1 MiB limit.
"""
from __future__ import annotations

import uuid

import config
from google.cloud import firestore as gc_firestore
from services.firestore import get_firestore_client
from services.tenancy import ADMIN_ROLES, AuthorizationError, audit, membership, now


ROOT_FIELDS = frozenset({
    "user_id", "title", "description", "total_seconds", "clarify_attempts",
    "pending_questions", "created_at", "updated_at", "assigned_user_ids",
    "created_by", "status",
})
STATE_FIELDS = frozenset({
    "analysis", "summary", "search_query", "statutes", "strength", "intake",
    "role",
})
LIST_COLLECTIONS = {
    "messages": "messages",
    "cases": "cases",
    "timeline": "timeline_events",
    "uploaded_documents": "documents",
}
TEXT_CHUNK_SIZE = 180_000


def _workspace_ref(workspace_id):
    return get_firestore_client().collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(str(workspace_id))


def _matter_ref(workspace_id, matter_id):
    return _workspace_ref(workspace_id).collection("matters").document(str(matter_id))


def locate_matter(matter_id: str) -> tuple[str, object] | tuple[None, None]:
    db = get_firestore_client()
    index = db.collection(config.FIRESTORE_MATTER_INDEX_COLLECTION).document(str(matter_id)).get()
    if not index.exists:
        return None, None
    workspace_id = (index.to_dict() or {}).get("workspace_id")
    if not workspace_id:
        return None, None
    return workspace_id, _matter_ref(workspace_id, matter_id)


def require_matter(matter_id: str, uid: str) -> tuple[str, object, dict]:
    workspace_id, ref = locate_matter(matter_id)
    if not ref:
        raise AuthorizationError("matter not found")
    member = membership(workspace_id, uid)
    if not member:
        raise AuthorizationError("matter access denied")
    snap = ref.get()
    if not snap.exists:
        raise AuthorizationError("matter not found")
    data = snap.to_dict() or {}
    workspace = _workspace_ref(workspace_id).get().to_dict() or {}
    if workspace.get("type") == "personal":
        if workspace.get("owner_id") != str(uid):
            raise AuthorizationError("matter access denied")
    elif member.get("role") not in ADMIN_ROLES:
        assigned = {str(item) for item in data.get("assigned_user_ids") or []}
        if str(uid) not in assigned:
            raise AuthorizationError("matter is not assigned to this user")
    return workspace_id, ref, data


def create_matter(workspace_id: str, uid: str, matter_id: str | None = None,
                  initial: dict | None = None) -> tuple[str, dict]:
    member = membership(workspace_id, uid)
    if not member:
        raise AuthorizationError("workspace access denied")
    db = get_firestore_client()
    matter_id = matter_id or str(uuid.uuid4())
    timestamp = now()
    data = dict(initial or {})
    data.update({
        "title": data.get("title") or "New Session",
        "created_by": str(uid),
        "assigned_user_ids": list(dict.fromkeys(data.get("assigned_user_ids") or [str(uid)])),
        "status": data.get("status") or "active",
        "created_at": data.get("created_at") or timestamp,
        "updated_at": timestamp,
    })
    ref = _matter_ref(workspace_id, matter_id)
    ref.set({key: value for key, value in data.items() if key in ROOT_FIELDS})
    db.collection(config.FIRESTORE_MATTER_INDEX_COLLECTION).document(matter_id).set({
        "workspace_id": workspace_id, "created_at": timestamp,
    })
    save_matter(matter_id, data)
    audit(workspace_id, uid, "matter.created", {"title": data["title"]}, matter_id)
    return matter_id, load_matter(matter_id, uid) or data


def _ordered(ref, collection_name):
    docs = list(ref.collection(collection_name).stream())
    docs.sort(key=lambda snap: ((snap.to_dict() or {}).get("position", 0), snap.id))
    result = []
    for snap in docs:
        item = snap.to_dict() or {}
        item.pop("position", None)
        item.setdefault("record_id", snap.id)
        result.append(item)
    return result


def _load_documents(ref, include_text: bool = True):
    result = _ordered(ref, "documents")
    for item in result:
        record_id = item.get("record_id")
        if not include_text:
            # Metadata-only consumers (global search) never read the text;
            # skipping the chunk fetch keeps them fast on document-heavy
            # matters.
            item.pop("text_chunked", None)
            continue
        if item.pop("text_chunked", False) and record_id:
            chunks = list(ref.collection("documents").document(record_id).collection("text_chunks").stream())
            chunks.sort(key=lambda snap: (snap.to_dict() or {}).get("position", 0))
            item["text"] = "".join((snap.to_dict() or {}).get("text", "") for snap in chunks)
    return result


def load_matter(matter_id: str, uid: str, *, include_document_text: bool = True) -> dict | None:
    try:
        workspace_id, ref, root = require_matter(matter_id, uid)
    except AuthorizationError:
        return None
    state_snap = ref.collection("state").document("current").get()
    data = dict(root)
    for field in ("created_at", "updated_at"):
        if hasattr(data.get(field), "isoformat"):
            data[field] = data[field].isoformat()
    if state_snap.exists:
        data.update(state_snap.to_dict() or {})
    draft_snap = ref.collection("drafts").document("current").get()
    if draft_snap.exists:
        data.update(draft_snap.to_dict() or {})
    for key, collection_name in LIST_COLLECTIONS.items():
        data[key] = (_load_documents(ref, include_text=include_document_text)
                     if key == "uploaded_documents" else _ordered(ref, collection_name))
    data["workspace_id"] = workspace_id
    data["matter_id"] = str(matter_id)
    return data


def _replace_collection(ref, collection_name: str, values: list[dict]):
    existing = {snap.id: snap for snap in ref.collection(collection_name).stream()}
    keep = set()
    for position, raw in enumerate(values or []):
        item = dict(raw) if isinstance(raw, dict) else {"value": raw}
        record_id = str(item.pop("record_id", "") or uuid.uuid4())
        keep.add(record_id)
        item["position"] = position
        ref.collection(collection_name).document(record_id).set(item)
    for record_id, snap in existing.items():
        if record_id not in keep:
            snap.reference.delete()


def _replace_documents(ref, values):
    existing = {snap.id: snap for snap in ref.collection("documents").stream()}
    keep = set()
    for position, raw in enumerate(values or []):
        item = dict(raw) if isinstance(raw, dict) else {"filename": str(raw)}
        record_id = str(item.pop("record_id", "") or uuid.uuid4())
        keep.add(record_id)
        text = str(item.pop("text", "") or "")
        item.update({"position": position, "text_chunked": bool(text)})
        doc_ref = ref.collection("documents").document(record_id)
        doc_ref.set(item)
        old_chunks = {snap.id: snap for snap in doc_ref.collection("text_chunks").stream()}
        chunk_ids = set()
        for chunk_position, start in enumerate(range(0, len(text), TEXT_CHUNK_SIZE)):
            chunk_id = f"{chunk_position:06d}"
            chunk_ids.add(chunk_id)
            doc_ref.collection("text_chunks").document(chunk_id).set({
                "position": chunk_position, "text": text[start:start + TEXT_CHUNK_SIZE]
            })
        for chunk_id, snap in old_chunks.items():
            if chunk_id not in chunk_ids:
                snap.reference.delete()
    for record_id, snap in existing.items():
        if record_id not in keep:
            for chunk in snap.reference.collection("text_chunks").stream():
                chunk.reference.delete()
            snap.reference.delete()


def save_matter(matter_id: str, data: dict):
    workspace_id, ref = locate_matter(matter_id)
    if not ref:
        raise ValueError(f"unknown matter: {matter_id}")
    root = {key: data.get(key) for key in ROOT_FIELDS if key in data}
    root["updated_at"] = data.get("updated_at") or now()
    ref.set(root, merge=True)
    state = {key: data.get(key) for key in STATE_FIELDS if key in data}
    if state:
        ref.collection("state").document("current").set(state, merge=True)
    if "draft" in data or "draft_type" in data:
        ref.collection("drafts").document("current").set(
            {key: data.get(key) for key in ("draft", "draft_type") if key in data}, merge=True)
    for key, collection_name in LIST_COLLECTIONS.items():
        if key not in data:
            continue
        if key == "uploaded_documents":
            _replace_documents(ref, data[key])
        else:
            _replace_collection(ref, collection_name, data[key])


def list_matters(workspace_id: str, uid: str) -> list[dict]:
    member = membership(workspace_id, uid)
    if not member:
        raise AuthorizationError("workspace access denied")
    workspace = _workspace_ref(workspace_id).get().to_dict() or {}
    result = []
    for snap in _workspace_ref(workspace_id).collection("matters").stream():
        data = snap.to_dict() or {}
        if workspace.get("type") == "team" and member.get("role") not in ADMIN_ROLES:
            if str(uid) not in {str(item) for item in data.get("assigned_user_ids") or []}:
                continue
        result.append({
            "matter_id": snap.id, "context_id": snap.id,
            "workspace_id": workspace_id, "title": data.get("title", "New Session"),
            "total_seconds": data.get("total_seconds", 0),
            "created_at": (data.get("created_at").isoformat() if hasattr(data.get("created_at"), "isoformat") else data.get("created_at")),
            "updated_at": (data.get("updated_at").isoformat() if hasattr(data.get("updated_at"), "isoformat") else data.get("updated_at")),
            "assigned_user_ids": data.get("assigned_user_ids") or [],
            "status": data.get("status", "active"),
        })
    result.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return result


def delete_matter(matter_id: str, uid: str) -> bool:
    workspace_id, ref, _ = require_matter(matter_id, uid)
    from services.retrieval import delete_matter_index
    delete_matter_index(matter_id, uid)
    for collection_name in [*LIST_COLLECTIONS.values(), "state", "drafts", "time_entries",
                            "jobs"]:
        for snap in ref.collection(collection_name).stream():
            if collection_name == "documents":
                for chunk in snap.reference.collection("text_chunks").stream():
                    chunk.reference.delete()
            snap.reference.delete()
    from services.storage import delete_prefix
    delete_prefix(f"workspaces/{workspace_id}/matters/{matter_id}/")
    delete_prefix(f"staging/{workspace_id}/{matter_id}/")
    ref.delete()
    get_firestore_client().collection(config.FIRESTORE_MATTER_INDEX_COLLECTION).document(matter_id).delete()
    audit(workspace_id, uid, "matter.deleted", {}, matter_id)
    return True


def append_time_entry(matter_id: str, uid: str, seconds: int):
    workspace_id, ref, _ = require_matter(matter_id, uid)
    value = max(0, int(seconds))
    if not value:
        raise ValueError("seconds must be positive")
    entry_ref = ref.collection("time_entries").document()
    transaction = get_firestore_client().transaction()

    @gc_firestore.transactional
    def record(txn):
        snap = ref.get(transaction=txn)
        if not snap.exists:
            raise AuthorizationError("matter not found")
        current = int((snap.to_dict() or {}).get("total_seconds", 0) or 0)
        timestamp = now()
        total = current + value
        txn.set(ref, {"total_seconds": total, "updated_at": timestamp}, merge=True)
        txn.set(entry_ref, {"user_id": str(uid), "seconds": value,
                            "created_at": timestamp})
        return total

    total = record(transaction)
    audit(workspace_id, uid, "time.recorded", {"seconds": value}, matter_id)
    return total


def append_message(matter_id: str, uid: str, role: str, content: str,
                   *, metadata: dict | None = None, message_id: str | None = None) -> dict:
    """Append one message without rewriting the complete matter aggregate."""
    _, ref, _ = require_matter(str(matter_id), str(uid))
    text = str(content or "").strip()
    if role not in {"user", "assistant", "system"} or not text:
        raise ValueError("a valid role and non-empty content are required")
    message_id = str(message_id or uuid.uuid4())
    message_ref = ref.collection("messages").document(message_id)
    existing = message_ref.get()
    existing_data = (existing.to_dict() or {}) if existing.exists else {}
    timestamp = existing_data.get("created_at") or now()
    payload = {
        "role": role,
        "content": text,
        "created_at": timestamp,
        "position": existing_data.get("position") or int(now().timestamp() * 1_000_000),
    }
    if metadata:
        payload["metadata"] = dict(metadata)
    message_ref.set(payload)
    ref.set({"updated_at": now()}, merge=True)
    payload["record_id"] = message_id
    return payload


def patch_matter(matter_id: str, uid: str, *, root: dict | None = None,
                 state: dict | None = None):
    """Apply bounded root/state changes without replacing subcollections."""
    _, ref, _ = require_matter(str(matter_id), str(uid))
    if root:
        values = {key: value for key, value in root.items() if key in ROOT_FIELDS}
        values["updated_at"] = now()
        ref.set(values, merge=True)
    if state:
        values = {key: value for key, value in state.items() if key in STATE_FIELDS}
        if values:
            ref.collection("state").document("current").set(values, merge=True)


def replace_matter_records(matter_id: str, uid: str, collection_name: str,
                           values: list[dict]):
    """Replace one normalized list after an explicit authorization check."""
    _, ref, _ = require_matter(str(matter_id), str(uid))
    if collection_name not in set(LIST_COLLECTIONS.values()):
        raise ValueError("unsupported matter collection")
    _replace_collection(ref, collection_name, values)


def upsert_document(matter_id: str, uid: str, document_id: str, metadata: dict, text: str):
    """Store document metadata, its private object path, and extracted text."""
    _, ref, _ = require_matter(str(matter_id), str(uid))
    doc_ref = ref.collection("documents").document(str(document_id))
    payload = {key: value for key, value in dict(metadata or {}).items()
               if key not in {"original_path", "text"}}
    payload.update({"text_chunked": bool(text), "updated_at": now()})
    doc_ref.set(payload, merge=True)
    existing = {snap.id: snap for snap in doc_ref.collection("text_chunks").stream()}
    keep = set()
    for position, start in enumerate(range(0, len(text or ""), TEXT_CHUNK_SIZE)):
        chunk_id = f"{position:06d}"
        keep.add(chunk_id)
        doc_ref.collection("text_chunks").document(chunk_id).set({
            "position": position, "text": text[start:start + TEXT_CHUNK_SIZE],
        })
    for chunk_id, snap in existing.items():
        if chunk_id not in keep:
            snap.reference.delete()
    ref.set({"updated_at": now()}, merge=True)


def delete_document(matter_id: str, uid: str, document_id: str):
    _, ref, _ = require_matter(str(matter_id), str(uid))
    doc_ref = ref.collection("documents").document(str(document_id))
    for snap in doc_ref.collection("text_chunks").stream():
        snap.reference.delete()
    doc_ref.delete()


def patch_document(matter_id: str, uid: str, document_id: str, metadata: dict):
    _, ref, _ = require_matter(str(matter_id), str(uid))
    values = {key: value for key, value in dict(metadata or {}).items()
              if key not in {"storage_path", "original_path", "text"}}
    values["updated_at"] = now()
    ref.collection("documents").document(str(document_id)).set(values, merge=True)
