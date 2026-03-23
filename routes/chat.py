from flask import Blueprint, jsonify, request, session

from models.context import get_context_id, get_or_create_context
from services.courtlistener import query_courtlistener
from services.llm import (
    check_if_more_info_needed,
    extract_answers_from_message,
    extract_structured_analysis,
    generate_query,
    grade_case,
    summarize_case,
)


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
def chat():
    payload = request.json or {}
    message = payload.get("message", "").strip()
    clarified = payload.get("clarified", False)
    clarification_answers = payload.get("clarification_answers", None)
    clarify_attempts = int(payload.get("clarify_attempts", 0) or 0)
    adding_info = payload.get("adding_info", False)

    context_id = get_context_id(session)
    context = get_or_create_context(context_id)

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
            return jsonify(
                {
                    "status": "clarifying",
                    "questions": questions,
                    "clarify_attempts": context["clarify_attempts"],
                    "context_id": context_id,
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
            return jsonify(
                {
                    "status": "clarifying",
                    "questions": questions,
                    "clarify_attempts": context["clarify_attempts"],
                    "context_id": context_id,
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

    cases = []
    try:
        for i in range(3):
            search_query = generate_query(summary, analysis)
            context["search_query"] += f"{i}th search query: {search_query}\n\n"
            cases_for_query = query_courtlistener(search_query)
            for c in cases_for_query:
                if c not in cases:
                    cases.append(c)
            # cases += cases_for_query
    except Exception as e:
        return jsonify({"status": "error", "message": f"CourtListener error: {e}"}), 500

    results = []
    for c in cases:
        grading = grade_case(summary, c["title"], c["snippet"], analysis)
        results.append(
            {
                **c,
                "relevance_score": grading["score"],
                "relevance_reason": grading["reason"],
            }
        )

    # Sort by descending relevance
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    context["cases"] = results

    # -------------------------------------------------
    # Step 7: Return results
    # -------------------------------------------------
    return jsonify(
        {
            "status": "results",
            "context_id": context_id,
            "query": context["search_query"],
            "summary": summary,
            "analysis": analysis,
            "cases": results,
        }
    )
