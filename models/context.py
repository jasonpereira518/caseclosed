import uuid
import time


MAX_CONTEXTS = 100


def default_context():
    return {
        "description": "",
        "clarify_attempts": 0,
        "pending_questions": [],
        "analysis": {},
        "summary": "",
        "search_query": "",
        "cases": [],
        "last_accessed": time.time(),
    }


user_contexts = {}  # {session_id: context}


def get_context_id(session_obj):
    if "context_id" not in session_obj:
        session_obj["context_id"] = str(uuid.uuid4())
    return session_obj["context_id"]


def get_context(context_id):
    context = user_contexts.get(context_id)
    if context is not None:
        context["last_accessed"] = time.time()
        return context
    return {}


def get_context_or_default(context_id):
    context = user_contexts.get(context_id)
    if context is not None:
        context["last_accessed"] = time.time()
        return context
    return default_context()


def get_or_create_context(context_id):
    now = time.time()
    context = user_contexts.get(context_id)
    created = False
    if context is None:
        context = default_context()
        user_contexts[context_id] = context
        created = True
    context["last_accessed"] = now

    if created:
        cleanup_stale_contexts()
    return context


def cleanup_stale_contexts(max_age_seconds=3600):
    now = time.time()
    stale_ids = [
        context_id
        for context_id, context in user_contexts.items()
        if now - context.get("last_accessed", 0) > max_age_seconds
    ]
    for context_id in stale_ids:
        user_contexts.pop(context_id, None)

    if len(user_contexts) > MAX_CONTEXTS:
        # If still above limit after stale cleanup, evict oldest contexts.
        oldest_first = sorted(
            user_contexts.items(),
            key=lambda item: item[1].get("last_accessed", 0),
        )
        overflow = len(user_contexts) - MAX_CONTEXTS
        for context_id, _ in oldest_first[:overflow]:
            user_contexts.pop(context_id, None)


def update_context(context_id, data):
    context = get_or_create_context(context_id)
    context.update(data)
    return context
