import uuid

import config

from services.firestore import get_firestore_client, load_context, save_context, try_startup_init


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
        save_context(self._context_id, dict(self))

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        save_context(self._context_id, dict(self))


def default_context():
    return {
        "description": "",
        "clarify_attempts": 0,
        "pending_questions": [],
        "analysis": {},
        "summary": "",
        "search_query": "",
        "cases": [],
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
    return FirestoreBackedDict(context_id, loaded)


def get_context_or_default(context_id, user_id=None):
    loaded = load_context(context_id)
    if loaded is None:
        return default_context()
    if not _context_allowed_for_user(loaded, user_id):
        return default_context()
    return FirestoreBackedDict(context_id, loaded)


def get_or_create_context(context_id, user_id=None):
    loaded = load_context(context_id)
    if loaded is not None:
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
    context.update(data)
    return context


def list_user_contexts(user_id):
    """Return context document IDs owned by user_id."""
    if not user_id:
        return []
    try:
        db = get_firestore_client()
    except RuntimeError:
        return []
    col = db.collection(config.FIRESTORE_COLLECTION)
    return [doc.id for doc in col.where("user_id", "==", str(user_id)).stream()]
