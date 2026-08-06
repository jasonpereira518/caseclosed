"""Single place to resolve which matter a request is scoped to.

Routes accept both `matter_id` (current) and `context_id` (legacy alias
from the session/context -> workspace/matter data model migration) in
request payloads. This keeps that dual-naming acceptance in one place
instead of each route repeating `payload.get("matter_id") or
payload.get("context_id")`.
"""


def resolve_matter_id(payload: dict, *, session=None) -> str | None:
    source = payload or {}
    matter_id = source.get("matter_id") or source.get("context_id")
    if not matter_id and session is not None:
        matter_id = session.get("context_id")
    matter_id = str(matter_id).strip() if matter_id else ""
    return matter_id or None
