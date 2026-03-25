import traceback

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required

from models.context import (
    context_belongs_to_user,
    get_context,
    get_context_id,
    get_or_create_context,
)
from services.courtlistener import query_courtlistener
from services.llm import (
    ask_about_case,
    check_if_more_info_needed,
    describe_case,
    extract_answers_from_message,
    extract_structured_analysis,
    generate_query,
    generate_session_title,
    grade_case,
    rerank_cases,
    summarize_case,
)


chat_bp = Blueprint("chat", __name__)


def _append_chat_message(context, role, content):
    """Persist one chat message; reassign list so FirestoreBackedDict saves."""
    text = (content or "").strip()
    if not text:
        return
    messages = list(context.get("messages") or [])
    messages.append({"role": role, "content": text})
    context["messages"] = messages


@chat_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    payload = request.json or {}
    message = payload.get("message", "").strip()
    clarified = payload.get("clarified", False)
    clarification_answers = payload.get("clarification_answers", None)
    clarify_attempts = int(payload.get("clarify_attempts", 0) or 0)
    adding_info = payload.get("adding_info", False)

    context_id = get_context_id(session)
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden", "title": "New Session"}), 403

    if message:
        _append_chat_message(context, "user", message)

    if message and context.get("title") == "New Session":
        try:
            context["title"] = generate_session_title(message)
        except Exception:
            pass

    if adding_info and message:
        context["description"] += " " + message
        # Re-analyze with new info
        combined_text = context["description"].strip()
        context["analysis"] = extract_structured_analysis(combined_text)

    # Store previous questions if we're in clarification mode
    previous_questions = context.get("pending_questions", [])

    # If we have pending questions, extract answers from user's message
    if previous_questions and not clarified:
        extracted = extract_answers_from_message(message, previous_questions)
        # Add the user's message to context
        context["description"] += " " + message
        combined_text = context["description"].strip()

        # Check if we still need more info
        needs_more, questions = check_if_more_info_needed(message, combined_text, context.get("analysis"))

        if needs_more and questions and clarify_attempts < 2:
            context["pending_questions"] = questions
            context["clarify_attempts"] = clarify_attempts + 1
            _qj_items = [f"{idx + 1}. {q}" for idx, q in enumerate(questions)]
            lines = "\n".join(_qj_items)
            _append_chat_message(
                context,
                "assistant",
                f"I need a bit more information:\n\n{lines}\n\nPlease provide answers to these questions in your next message.",
            )
            return jsonify(
                {
                    "status": "clarifying",
                    "questions": questions,
                    "clarify_attempts": context["clarify_attempts"],
                    "context_id": context_id,
                    "title": context.get("title", "New Session"),
                    "analysis": context.get("analysis", {}),
                }
            )
        # If we have enough info, continue to analysis
        context["pending_questions"] = []
        context["clarify_attempts"] = 0
    elif not clarified and clarify_attempts < 2:
        # First time or no pending questions - check if we need info
        combined_text = (context["description"] + " " + message).strip()
        needs_more, questions = check_if_more_info_needed(message, combined_text, context.get("analysis"))

        if needs_more and questions:
            context["description"] += " " + message
            context["pending_questions"] = questions
            context["clarify_attempts"] = clarify_attempts + 1
            _qj_items = [f"{idx + 1}. {q}" for idx, q in enumerate(questions)]
            lines = "\n".join(_qj_items)
            _append_chat_message(
                context,
                "assistant",
                f"I need a bit more information:\n\n{lines}\n\nPlease provide answers to these questions in your next message.",
            )
            return jsonify(
                {
                    "status": "clarifying",
                    "questions": questions,
                    "clarify_attempts": context["clarify_attempts"],
                    "context_id": context_id,
                    "title": context.get("title", "New Session"),
                    "analysis": context.get("analysis", {}),
                }
            )
        # If we have enough info, continue
        context["description"] += " " + message
        context["pending_questions"] = []
    else:
        # User explicitly clarified or we're past attempts
        context["description"] += " " + message
        context["pending_questions"] = []
        context["clarify_attempts"] = 0

    combined_text = context["description"].strip()
    analysis = extract_structured_analysis(combined_text)
    context["analysis"] = analysis

    summary = summarize_case(combined_text)
    context["summary"] = summary

    seen_keys = set()
    cases = []
    results = []
    try:
        for i in range(3):
            search_query = generate_query(summary, analysis)
            search_query = str(search_query).strip() if search_query is not None else ""
            context["search_query"] += f"{i}th search query: {search_query}\n\n"
            cases_for_query = query_courtlistener(search_query)
            for c in cases_for_query:
                key = c.get("pdf_link") or c.get("citation") or c.get("title") or ""
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    cases.append(c)
            # cases += cases_for_query

        results = []
        for c in cases:
            grading = grade_case(summary, c["title"], c["snippet"], analysis)
            results.append(
                {
                    **c,
                    "initial_score": grading["score"],
                    "relevance_score": grading["score"],
                    "relevance_reason": grading["reason"],
                    "relevance_dimensions": grading.get("dimensions", {}),
                }
            )

        results = [r for r in results if r["relevance_score"] >= 15]

        if len(results) > 3:
            results = rerank_cases(summary, analysis, results)

        # Sort by descending relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        context["cases"] = results
    except Exception as e:
        print(f"[ERROR] Full traceback:")
        traceback.print_exc()
        return jsonify(
            {
                "status": "error",
                "message": str(e),
                "context_id": context_id,
                "title": context.get("title", "New Session"),
            }
        ), 500

    if results:
        _append_chat_message(
            context,
            "assistant",
            f"Found {len(results)} relevant cases. Check the Cases panel.",
        )
    else:
        _append_chat_message(context, "assistant", "No relevant cases found.")
    _append_chat_message(
        context,
        "assistant",
        "You can add more information to refine the search or generate a document.",
    )

    # -------------------------------------------------
    # Step 7: Return results
    # -------------------------------------------------
    return jsonify(
        {
            "status": "results",
            "context_id": context_id,
            "title": context.get("title", "New Session"),
            "query": context["search_query"],
            "summary": summary,
            "analysis": analysis,
            "cases": results,
        }
    )


@chat_bp.route("/case/describe", methods=["POST"])
@chat_bp.route("/case/describe/", methods=["POST"])
@chat_bp.route("/chat/case/describe", methods=["POST"])
@chat_bp.route("/chat/case/describe/", methods=["POST"])
@login_required
def case_describe():
    payload = request.get_json(silent=True) or {}
    request_context_id = str(payload.get("context_id", "")).strip()
    session_context_id = str(session.get("context_id", "")).strip()
    context_id = request_context_id or session_context_id
    case_index = payload.get("case_index")
    user_id = str(current_user.get_id())

    if not context_id:
        return jsonify({"error": "context_id is required"}), 400
    try:
        idx = int(case_index)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid case_index"}), 400

    belongs = context_belongs_to_user(context_id, user_id)
    if not belongs:
        return jsonify({"error": "forbidden"}), 403

    context = get_context(context_id, user_id)
    if not context:
        return jsonify({"error": "context not found"}), 404

    cases = list(context.get("cases") or [])
    if idx < 0 or idx >= len(cases):
        return jsonify({"error": "invalid case_index"}), 400

    case = dict(cases[idx])
    existing = case.get("description")
    if isinstance(existing, str) and existing.strip():
        return jsonify({"description": existing.strip()})

    text = describe_case(case).strip()
    case["description"] = text
    cases[idx] = case
    context["cases"] = cases

    return jsonify({"description": text})


@chat_bp.route("/case/ask", methods=["POST"])
@chat_bp.route("/chat/case/ask", methods=["POST"])
@login_required
def case_ask():
    payload = request.get_json(silent=True) or {}
    request_context_id = str(payload.get("context_id", "")).strip()
    session_context_id = str(session.get("context_id", "")).strip()
    context_id = request_context_id or session_context_id
    case_index = payload.get("case_index")
    question = (payload.get("question") or "").strip()
    user_id = str(current_user.get_id())

    if not context_id or not question:
        return jsonify({"error": "context_id and question are required"}), 400
    try:
        idx = int(case_index)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid case_index"}), 400

    belongs = context_belongs_to_user(context_id, user_id)
    if not belongs:
        return jsonify({"error": "forbidden"}), 403

    context = get_context(context_id, user_id)
    if not context:
        return jsonify({"error": "context not found"}), 404

    cases = list(context.get("cases") or [])
    if idx < 0 or idx >= len(cases):
        return jsonify({"error": "invalid case_index"}), 400

    case = dict(cases[idx])
    summary = (context.get("summary") or context.get("description") or "").strip()
    analysis = context.get("analysis") if isinstance(context.get("analysis"), dict) else {}

    answer = ask_about_case(summary, analysis, case, question)

    title = case.get("title") or "Untitled"
    follow_ups = list(case.get("follow_ups") or [])
    follow_ups.append({"question": question, "answer": answer})
    case["follow_ups"] = follow_ups
    cases[idx] = case
    context["cases"] = cases

    return jsonify({"answer": answer, "case_title": title})
