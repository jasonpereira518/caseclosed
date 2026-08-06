"""Compatibility aggregate over normalized, workspace-scoped matter records."""
import uuid
from datetime import datetime, timezone

from services.matters import (
    LIST_COLLECTIONS,
    ROOT_FIELDS,
    STATE_FIELDS,
    create_matter,
    delete_matter,
    list_matters,
    load_matter,
    locate_matter,
    patch_matter,
    save_matter,
)
from services.tenancy import active_workspace, personal_workspace_id
import config
from services.firestore import get_firestore_client, load_context as load_legacy_context


class FirestoreBackedDict(dict):
    __slots__ = ("_context_id", "_user_id")

    def __init__(self, context_id, user_id, initial=None):
        self._context_id = str(context_id)
        self._user_id = str(user_id)
        super().__init__(initial or {})

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        _touch_updated_at(self)
        _persist_fields(self._context_id, self._user_id, self, {key})

    def set(self, key, value, touch=True):
        super().__setitem__(key, value)
        if touch:
            _touch_updated_at(self)
        _persist_fields(self._context_id, self._user_id, self, {key})

    def update(self, *args, **kwargs):
        changed = set(dict(*args, **kwargs))
        super().update(*args, **kwargs)
        _touch_updated_at(self)
        _persist_fields(self._context_id, self._user_id, self, changed)


def _persist_fields(context_id, user_id, context, changed):
    """Persist only changed matter sections so unrelated worker writes survive."""
    changed = set(changed or ())
    root = {key: context.get(key) for key in changed if key in ROOT_FIELDS}
    state = {key: context.get(key) for key in changed if key in STATE_FIELDS}
    if root or state:
        patch_matter(str(context_id), str(user_id),
                     root=root or None, state=state or None)
    draft = {key: context.get(key) for key in changed if key in {"draft", "draft_type"}}
    if draft:
        save_matter(str(context_id), draft)
    for key in changed & set(LIST_COLLECTIONS):
        save_matter(str(context_id), {key: context.get(key) or []})


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _touch_updated_at(ctx):
    if isinstance(ctx, FirestoreBackedDict):
        dict.__setitem__(ctx, "updated_at", _now_iso())
    elif isinstance(ctx, dict):
        ctx["updated_at"] = _now_iso()


def _ensure_metadata(ctx):
    if not isinstance(ctx, dict):
        return ctx
    timestamp = _now_iso()
    ctx.setdefault("title", "New Session")
    ctx.setdefault("created_at", timestamp)
    ctx.setdefault("updated_at", timestamp)
    return ctx


def default_context():
    timestamp = _now_iso()
    return {
        "description": "", "uploaded_documents": [], "total_seconds": 0,
        "clarify_attempts": 0, "pending_questions": [], "messages": [],
        "analysis": {}, "summary": "", "search_query": "", "cases": [],
        "timeline": [], "statutes": [], "strength": {}, "intake": {},
        "draft": "", "title": "New Session", "created_at": timestamp,
        "updated_at": timestamp, "status": "active",
    }


def get_context_id(session_obj):
    if "context_id" not in session_obj:
        session_obj["context_id"] = str(uuid.uuid4())
    return session_obj["context_id"]


def get_context(context_id, user_id=None):
    if not context_id or not user_id:
        return {}
    loaded = load_matter(str(context_id), str(user_id)) or _migrate_legacy_context(
        str(context_id), str(user_id))
    return FirestoreBackedDict(context_id, user_id, _ensure_metadata(loaded)) if loaded else {}


def get_context_or_default(context_id, user_id=None):
    if not user_id:
        return default_context()
    loaded = load_matter(str(context_id), str(user_id)) or _migrate_legacy_context(
        str(context_id), str(user_id))
    if loaded:
        return FirestoreBackedDict(context_id, user_id, _ensure_metadata(loaded))
    _, ctx = create_new_context(str(user_id), context_id=str(context_id))
    return FirestoreBackedDict(context_id, user_id, ctx)


def get_or_create_context(context_id, user_id=None):
    if not user_id:
        return None
    loaded = load_matter(str(context_id), str(user_id)) or _migrate_legacy_context(
        str(context_id), str(user_id))
    if loaded:
        return FirestoreBackedDict(context_id, user_id, _ensure_metadata(loaded))
    # A missing indexed matter is new. A matter that exists but is inaccessible
    # must never be recreated in the caller's workspace under the same ID.
    workspace_id, _ = locate_matter(str(context_id))
    if workspace_id:
        return None
    _, ctx = create_new_context(str(user_id), context_id=str(context_id))
    return FirestoreBackedDict(context_id, user_id, ctx)


def save_context(context_id, data):
    if isinstance(data, FirestoreBackedDict):
        # Field assignments on this wrapper are persisted immediately and
        # granularly; rewriting the aggregate here would reintroduce races.
        return
    save_matter(str(context_id), dict(data))


def update_context(context_id, data, user_id=None):
    context = get_or_create_context(context_id, user_id)
    if context is None:
        return None
    context.update(data)
    return context


def list_user_contexts(user_id, workspace_id=None):
    if not user_id:
        return []
    wid = workspace_id or active_workspace(str(user_id))
    _migrate_legacy_for_user(str(user_id), wid)
    return list_matters(wid, str(user_id))


def _migrate_legacy_context(context_id: str, user_id: str, workspace_id=None):
    """Lazily adopt only legacy records with an exact owner identity match."""
    existing_workspace, _ = locate_matter(context_id)
    if existing_workspace:
        return load_matter(context_id, user_id)
    legacy = load_legacy_context(context_id)
    if not legacy or str(legacy.get("user_id") or "") != str(user_id):
        return None
    wid = workspace_id or active_workspace(user_id) or personal_workspace_id(user_id)
    _, loaded = create_matter(wid, user_id, matter_id=context_id, initial=legacy)
    get_firestore_client().collection(config.FIRESTORE_COLLECTION).document(context_id).set({
        "migration_status": "migrated", "migrated_uid": user_id,
    }, merge=True)
    return loaded


def _migrate_legacy_for_user(user_id: str, workspace_id: str):
    if not workspace_id:
        return
    collection = get_firestore_client().collection(config.FIRESTORE_COLLECTION)
    for snap in collection.where("user_id", "==", user_id).stream():
        data = snap.to_dict() or {}
        if data.get("migration_status") == "migrated" or locate_matter(snap.id)[0]:
            continue
        _migrate_legacy_context(snap.id, user_id, workspace_id)


def context_belongs_to_user(context_id, user_id):
    return bool(user_id and get_context(str(context_id), str(user_id)))


def rename_context(context_id, user_id, title):
    context = get_context(context_id, user_id)
    if not context:
        return False
    context["title"] = (title or "").strip()[:120] or "New Session"
    return True


def delete_user_context(context_id, user_id):
    try:
        return delete_matter(str(context_id), str(user_id))
    except (PermissionError, ValueError):
        return False


def create_new_context(user_id, context_id=None, workspace_id=None):
    wid = workspace_id or active_workspace(str(user_id)) or personal_workspace_id(str(user_id))
    return create_matter(wid, str(user_id), matter_id=context_id, initial=default_context())


def cap_session_title(text: str, max_len: int = 28) -> str:
    text = (text or "").strip().strip("\"'“”‘’")
    while text and text[-1] in ".,;:!?":
        text = text[:-1].strip()
    if not text:
        return "New Session"
    if len(text) <= max_len:
        return text
    chunk = text[:max_len + 1]
    return (text[:max_len].rsplit(" ", 1)[0].strip() if " " in chunk else text[:max_len].strip()) or "New Session"


def _strip_conversational_lead_in(text: str) -> str:
    value = (text or "").strip()
    lowered = value.lower()
    for prefix in ("i need help with ", "i need help ", "can you help with ", "help with ",
                   "question about ", "i have a question about "):
        if lowered.startswith(prefix):
            return value[len(prefix):].strip()
    return value


def _first_line_preview_words(text: str, max_words: int = 5) -> str:
    words = _strip_conversational_lead_in((text or "").strip().split("\n", 1)[0]).split()
    return " ".join(words[:max_words])


def auto_generate_title(context):
    messages = context.get("messages") or [] if isinstance(context, dict) else []
    if messages:
        first = messages[0]
        text = first.get("content") or first.get("text") if isinstance(first, dict) else str(first)
        if text:
            return cap_session_title(_first_line_preview_words(text))
    description = str(context.get("description", "")).strip() if isinstance(context, dict) else ""
    if description:
        return cap_session_title(_first_line_preview_words(description))
    return "New Session"
