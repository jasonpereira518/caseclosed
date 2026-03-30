import uuid
from datetime import datetime, timezone

import config
from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore import (
    delete_context as delete_context_doc,
    get_firestore_client,
    load_context,
    save_context,
    try_startup_init,
)


try_startup_init()


class FirestoreBackedDict(dict):
    """
    Persists top-level context mutations to Firestore so route handlers that
    mutate the returned dict in place stay in sync without changing routes.
    """

    __slots__ = ("_context_id",)

    def __init__(self, context_id, initial=None):
        self._context_id = context_id
        if initial is None:
            initial = {}
        super().__init__(initial)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        _touch_updated_at(self)
        save_context(self._context_id, dict(self))

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        _touch_updated_at(self)
        save_context(self._context_id, dict(self))


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _touch_updated_at(ctx):
    if isinstance(ctx, dict):
        if isinstance(ctx, FirestoreBackedDict):
            dict.__setitem__(ctx, "updated_at", _now_iso())
        else:
            ctx["updated_at"] = _now_iso()


def _ensure_metadata(ctx):
    if not isinstance(ctx, dict):
        return ctx
    now = _now_iso()
    ctx.setdefault("title", "New Session")
    ctx.setdefault("created_at", now)
    ctx.setdefault("updated_at", now)
    return ctx


def default_context():
    now = _now_iso()
    return {
        "description": "",
        "clarify_attempts": 0,
        "pending_questions": [],
        "messages": [],
        "analysis": {},
        "summary": "",
        "search_query": "",
        "cases": [],
        "timeline": [],
        "statutes": [],
        "title": "New Session",
        "created_at": now,
        "updated_at": now,
    }


def _context_allowed_for_user(loaded, user_id):
    """Return True if loaded context may be accessed by user_id (str or None)."""
    if loaded is None:
        return False
    if user_id is None:
        return True
    doc_uid = loaded.get("user_id")
    if doc_uid is None:
        return True
    return str(doc_uid) == str(user_id)


def get_context_id(session_obj):
    if "context_id" not in session_obj:
        session_obj["context_id"] = str(uuid.uuid4())
    return session_obj["context_id"]


def get_context(context_id, user_id=None):
    loaded = load_context(context_id)
    if loaded is None or not _context_allowed_for_user(loaded, user_id):
        return {}
    loaded = _ensure_metadata(loaded)
    return FirestoreBackedDict(context_id, loaded)


def get_context_or_default(context_id, user_id=None):
    loaded = load_context(context_id)
    if loaded is None:
        return default_context()
    if not _context_allowed_for_user(loaded, user_id):
        return default_context()
    loaded = _ensure_metadata(loaded)
    return FirestoreBackedDict(context_id, loaded)


def get_or_create_context(context_id, user_id=None):
    loaded = load_context(context_id)
    if loaded is not None:
        loaded = _ensure_metadata(loaded)
        if user_id is not None:
            doc_uid = loaded.get("user_id")
            if doc_uid is not None and str(doc_uid) != str(user_id):
                return None
            if doc_uid is None:
                merged = dict(loaded)
                merged["user_id"] = str(user_id)
                save_context(context_id, merged)
                loaded = merged
        return FirestoreBackedDict(context_id, loaded)

    ctx = default_context()
    if user_id is not None:
        ctx["user_id"] = str(user_id)
    wrapped = FirestoreBackedDict(context_id, ctx)
    save_context(context_id, dict(wrapped))
    return wrapped


def update_context(context_id, data, user_id=None):
    context = get_or_create_context(context_id, user_id)
    if context is None:
        return None
    _touch_updated_at(data)
    context.update(data)
    return context


def list_user_contexts(user_id):
    """Return context metadata list owned by user_id."""
    if not user_id:
        return []
    try:
        db = get_firestore_client()
    except RuntimeError:
        return []
    col = db.collection(config.FIRESTORE_COLLECTION)
    sessions = []
    for doc in col.where(filter=FieldFilter("user_id", "==", str(user_id))).stream():
        data = _ensure_metadata(doc.to_dict() or {})
        sessions.append(
            {
                "context_id": doc.id,
                "title": data.get("title", "New Session"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
        )
    return sessions


def context_belongs_to_user(context_id, user_id):
    loaded = load_context(context_id)
    return _context_allowed_for_user(loaded, user_id)


def rename_context(context_id, user_id, title):
    context = get_context(context_id, user_id)
    if not context:
        return False
    clean_title = (title or "").strip()[:120] or "New Session"
    context["title"] = clean_title
    return True


def delete_user_context(context_id, user_id):
    if not context_belongs_to_user(context_id, user_id):
        return False
    try:
        delete_context_doc(context_id)
        return True
    except Exception:
        return False


def create_new_context(user_id, context_id=None):
    if not context_id:
        context_id = str(uuid.uuid4())
    ctx = default_context()
    ctx["user_id"] = str(user_id)
    save_context(context_id, ctx)
    return context_id, ctx


def cap_session_title(text: str, max_len: int = 28) -> str:
    """Trim to max_len characters at the last full word; strip noise punctuation."""
    text = (text or "").strip()
    text = text.strip("\"'“”‘’")
    while text and text[-1] in ".,;:!?":
        text = text[:-1].strip()
    if not text:
        return "New Session"
    if len(text) <= max_len:
        return text
    chunk = text[: max_len + 1]
    if " " in chunk:
        cut = text[:max_len].rsplit(" ", 1)[0].strip()
        return cut if cut else text[:max_len].strip()
    return text[:max_len].strip()


def _strip_conversational_lead_in(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    low = t.lower()
    for prefix in (
        "i need help with ",
        "i need help ",
        "can you help with ",
        "help with ",
        "question about ",
        "i have a question about ",
    ):
        if low.startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def _first_line_preview_words(text: str, max_words: int = 5) -> str:
    line = _strip_conversational_lead_in((text or "").strip().split("\n", 1)[0])
    words = line.split()
    return " ".join(words[:max_words]) if words else ""


def auto_generate_title(context):
    """Non-LLM fallback: short topic (≤28 chars) from first user message or description."""
    if not isinstance(context, dict):
        return "New Session"

    messages = context.get("messages") or []
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            text = str(first.get("content") or first.get("text") or "").strip()
        else:
            text = str(first).strip()
        snippet = _first_line_preview_words(text, 5)
        if snippet:
            return cap_session_title(snippet)

    description = str(context.get("description", "")).strip()
    if description:
        for line in description.splitlines():
            line = line.strip()
            if line.startswith("[PDF:") and "]" in line:
                name = line[5 : line.index("]")].strip()
                base = name.replace(".pdf", "").replace("_", " ").strip()
                if base:
                    return cap_session_title(_first_line_preview_words(base, 5) or base)
        for line in description.splitlines():
            line = line.strip()
            if line and not line.startswith("[PDF:"):
                snippet = _first_line_preview_words(line, 5)
                if snippet:
                    return cap_session_title(snippet)

    return "New Session"
