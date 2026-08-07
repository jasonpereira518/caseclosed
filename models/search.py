"""
Cross-session search — in-memory ranked text search across all user
Firestore context documents (sessions, cases, notes, messages, etc.).
"""
import re
from html import escape as html_escape

from services.matters import list_matters, load_matter
from services.tenancy import list_workspaces

# Weight map: higher = more relevant when matched
_FIELD_WEIGHTS = {
    "session_title": 10,
    "case_title": 8,
    "case_citation": 8,
    "note": 6,
    "message": 4,
    "description": 3,
    "summary": 3,
    "case_snippet": 2,
    "case_reason": 2,
    "follow_up": 4,
}


def _extract_snippet(text, query, context_chars=60):
    """Return a snippet of *text* centred on the first occurrence of *query*."""
    if not text or not query:
        return ""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        # Return the start of the text as fallback
        return text[:context_chars * 2].strip()
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _highlight_snippet(snippet, query):
    """Wrap all occurrences of *query* in the *snippet* with <mark> tags."""
    if not snippet or not query:
        return html_escape(snippet or "")
    safe_snippet = html_escape(snippet)
    safe_query = html_escape(query)
    # Case-insensitive replacement preserving original case
    pattern = re.compile(re.escape(safe_query), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", safe_snippet)


def _text_matches(text, query_lower):
    """Check if query appears in text (case-insensitive)."""
    if not text:
        return False
    return query_lower in text.lower()


def _add_result(results, *, result_type, field_type, title, snippet_raw, query,
                context_id, session_title, case_index=None, updated_at=None):
    """Build and append a search result dict."""
    snippet = _extract_snippet(snippet_raw, query)
    highlighted = _highlight_snippet(snippet, query)
    weight = _FIELD_WEIGHTS.get(field_type, 1)
    results.append({
        "type": result_type,
        "field_type": field_type,
        "title": title,
        "snippet": highlighted,
        "rank": weight,
        "context_id": context_id,
        "session_title": session_title,
        "case_index": case_index,
        "updated_at": updated_at,
    })


def search_user_contexts(user_id, query, filters=None):
    """
    Load all Firestore contexts for *user_id* and search across their fields.

    Returns a list of result dicts sorted by rank (descending), capped at 50.
    """
    if not user_id or not query or not query.strip():
        return []

    query = query.strip()
    query_lower = query.lower()
    filters = filters or {}
    content_types = set(filters.get("content_types") or
                        ["sessions", "cases", "notes", "messages"])

    results = []

    authorized = []
    try:
        for workspace in list_workspaces(str(user_id)):
            for summary in list_matters(workspace["workspace_id"], str(user_id)):
                authorized.append((summary["matter_id"], load_matter(summary["matter_id"], str(user_id)) or {}))
    except RuntimeError:
        return []

    for ctx_id, data in authorized:
        sess_title = data.get("title") or "New Session"
        updated_at = data.get("updated_at")

        # --- Session-level fields ---
        if "sessions" in content_types:
            if _text_matches(sess_title, query_lower):
                _add_result(results, result_type="session", field_type="session_title",
                            title=sess_title, snippet_raw=sess_title, query=query,
                            context_id=ctx_id, session_title=sess_title,
                            updated_at=updated_at)

            desc = data.get("description") or ""
            if _text_matches(desc, query_lower):
                _add_result(results, result_type="session", field_type="description",
                            title=sess_title, snippet_raw=desc, query=query,
                            context_id=ctx_id, session_title=sess_title,
                            updated_at=updated_at)

            summary = data.get("summary") or ""
            if summary and _text_matches(summary, query_lower):
                _add_result(results, result_type="session", field_type="summary",
                            title=sess_title, snippet_raw=summary, query=query,
                            context_id=ctx_id, session_title=sess_title,
                            updated_at=updated_at)

        # --- Messages ---
        if "messages" in content_types:
            messages = data.get("messages") or []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content") or msg.get("text") or ""
                if _text_matches(content, query_lower):
                    role = msg.get("role", "user")
                    _add_result(results, result_type="message", field_type="message",
                                title=f"{'You' if role == 'user' else 'Assistant'} — {sess_title}",
                                snippet_raw=content, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                updated_at=updated_at)

        # --- Cases ---
        cases = data.get("cases") or []
        for ci, case in enumerate(cases):
            if not isinstance(case, dict):
                continue

            if "cases" in content_types:
                case_title = case.get("title") or ""
                if _text_matches(case_title, query_lower):
                    _add_result(results, result_type="case", field_type="case_title",
                                title=case_title, snippet_raw=case_title, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                case_index=ci, updated_at=updated_at)

                citation = case.get("citation") or ""
                if citation and _text_matches(citation, query_lower):
                    _add_result(results, result_type="case", field_type="case_citation",
                                title=case_title or citation,
                                snippet_raw=citation, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                case_index=ci, updated_at=updated_at)

                snippet_text = case.get("snippet") or ""
                if snippet_text and _text_matches(snippet_text, query_lower):
                    _add_result(results, result_type="case", field_type="case_snippet",
                                title=case_title or "Untitled Case",
                                snippet_raw=snippet_text, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                case_index=ci, updated_at=updated_at)

                reason = case.get("relevance_reason") or ""
                if reason and _text_matches(reason, query_lower):
                    _add_result(results, result_type="case", field_type="case_reason",
                                title=case_title or "Untitled Case",
                                snippet_raw=reason, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                case_index=ci, updated_at=updated_at)

            # --- Notes (on cases) ---
            if "notes" in content_types:
                notes = case.get("notes") or ""
                if notes and _text_matches(notes, query_lower):
                    _add_result(results, result_type="note", field_type="note",
                                title=f"Note — {case.get('title') or 'Untitled Case'}",
                                snippet_raw=notes, query=query,
                                context_id=ctx_id, session_title=sess_title,
                                case_index=ci, updated_at=case.get("notes_updated_at") or updated_at)

            # --- Follow-ups (on cases) ---
            if "messages" in content_types:
                follow_ups = case.get("follow_ups") or []
                for fu in follow_ups:
                    if not isinstance(fu, dict):
                        continue
                    q_text = fu.get("question") or ""
                    a_text = fu.get("answer") or ""
                    if _text_matches(q_text, query_lower):
                        _add_result(results, result_type="message", field_type="follow_up",
                                    title=f"Q&A — {case.get('title') or 'Untitled Case'}",
                                    snippet_raw=q_text, query=query,
                                    context_id=ctx_id, session_title=sess_title,
                                    case_index=ci, updated_at=updated_at)
                    if _text_matches(a_text, query_lower):
                        _add_result(results, result_type="message", field_type="follow_up",
                                    title=f"Q&A — {case.get('title') or 'Untitled Case'}",
                                    snippet_raw=a_text, query=query,
                                    context_id=ctx_id, session_title=sess_title,
                                    case_index=ci, updated_at=updated_at)

    # Sort by rank descending, then by updated_at descending
    results.sort(key=lambda r: (r["rank"], r.get("updated_at") or ""), reverse=True)
    return results[:50]
