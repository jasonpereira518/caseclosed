import uuid


def default_context():
    return {
        "description": "",
        "clarify_attempts": 0,
        "pending_questions": [],
        "analysis": {},
        "summary": "",
        "search_query": "",
        "cases": []
    }


user_contexts = {}  # {session_id: context}


def get_context_id(session_obj):
    if "context_id" not in session_obj:
        session_obj["context_id"] = str(uuid.uuid4())
    return session_obj["context_id"]


def get_context(context_id):
    return user_contexts.get(context_id, {})


def get_context_or_default(context_id):
    return user_contexts.get(context_id, default_context())


def get_or_create_context(context_id):
    return user_contexts.setdefault(context_id, default_context())


def update_context(context_id, data):
    context = get_or_create_context(context_id)
    context.update(data)
    return context
