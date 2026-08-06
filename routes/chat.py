import uuid

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required

from models.context import (
    context_belongs_to_user,
    get_context,
    get_context_id,
    get_or_create_context,
)
from services.courtlistener import (
    check_case_treatment,
    extract_cluster_id,
)
from services.llm import (
    ask_about_case,
    describe_case,
)
from services.jobs import create_job, update_job
from services.matters import append_message
from services.task_queue import enqueue_job
from services.tenancy import AuthorizationError


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    """Acknowledge chat immediately; all retrieval/model work runs in a job."""
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 20_000:
        return jsonify({"error": "message is too long"}), 413
    context_id = str(payload.get("matter_id") or payload.get("context_id") or get_context_id(session))
    session["context_id"] = context_id
    context = get_or_create_context(context_id, str(current_user.get_id()))
    if context is None:
        return jsonify({"error": "forbidden", "title": "New Session"}), 403
    client_message_id = str(payload.get("client_message_id") or uuid.uuid4())[:128]
    try:
        job, created = create_job(context_id, str(current_user.get_id()), "chat",
                                  {"message": message}, client_message_id)
        if created:
            append_message(context_id, str(current_user.get_id()), "user", message,
                           metadata={"client_message_id": client_message_id, "job_id": job["job_id"]})
            enqueue_job(context_id, job["job_id"])
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    except Exception as exc:
        if "job" in locals():
            update_job(context_id, job["job_id"], status="failed", stage="enqueue_failed",
                       error={"code": "enqueue_failed", "message": str(exc)[:300]})
        return jsonify({"error": "unable to queue chat"}), 503
    job["status_url"] = f"/api/matters/{context_id}/jobs/{job['job_id']}"
    job["context_id"] = context_id
    job["deduplicated"] = not created
    return jsonify(job), 202


@chat_bp.route("/case/describe", methods=["POST"])
@chat_bp.route("/case/describe/", methods=["POST"])
@chat_bp.route("/chat/case/describe", methods=["POST"])
@chat_bp.route("/chat/case/describe/", methods=["POST"])
@login_required
def case_describe():
    payload = request.get_json(silent=True) or {}
    request_context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
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
    request_context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
    session_context_id = str(session.get("context_id", "")).strip()
    context_id = request_context_id or session_context_id
    case_index = payload.get("case_index")
    question = str(payload.get("question") or "").strip()
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


@chat_bp.route("/case/treatment", methods=["POST"])
@chat_bp.route("/chat/case/treatment", methods=["POST"])
@login_required
def case_treatment():
    default_error = {
        "status": "unknown",
        "label": "",
        "details": "",
        "checked": True
    }
    try:
        payload = request.get_json(silent=True) or {}
        request_context_id = str(payload.get("matter_id") or payload.get("context_id", "")).strip()
        session_context_id = str(session.get("context_id", "")).strip()
        context_id = request_context_id or session_context_id
        case_index = payload.get("case_index")
        user_id = str(current_user.get_id())

        if not context_id:
            return jsonify({"treatment": default_error})
        try:
            idx = int(case_index)
        except (TypeError, ValueError):
            return jsonify({"treatment": default_error})

        belongs = context_belongs_to_user(context_id, user_id)
        if not belongs:
            return jsonify({"error": "forbidden", "treatment": default_error}), 403

        context = get_context(context_id, user_id)
        if not context:
            return jsonify({"treatment": default_error})

        cases = list(context.get("cases") or [])
        if idx < 0 or idx >= len(cases):
            return jsonify({"treatment": default_error})

        case = dict(cases[idx])
        treatment = case.get("treatment", {})
        if treatment.get("checked"):
            return jsonify({"treatment": treatment})

        cluster_id = extract_cluster_id(case.get("pdf_link", ""))
        treatment_result = check_case_treatment(cluster_id, case.get("citation", ""))
        case["treatment"] = treatment_result
        cases[idx] = case
        context["cases"] = cases

        return jsonify({"treatment": treatment_result})
    except Exception:
        return jsonify({"treatment": default_error})


@chat_bp.route("/case/bookmark", methods=["POST"])
@login_required
def bookmark_case():
    data = request.get_json(silent=True) or {}
    context_id = data.get("matter_id") or data.get("context_id")
    try:
        case_index = int(data.get("case_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid case index"}), 400
    bookmarked = data.get("bookmarked", False)
    if not isinstance(bookmarked, bool):
        return jsonify({"error": "bookmarked must be a boolean"}), 400

    if not context_id:
        return jsonify({"error": "Missing parameters"}), 400

    user_id = str(current_user.get_id())
    if not context_belongs_to_user(context_id, user_id):
        return jsonify({"error": "Unauthorized"}), 403

    ctx = get_context(context_id, user_id)
    if not ctx:
        return jsonify({"error": "Context not found"}), 404

    cases = ctx.get("cases", [])
    if case_index < 0 or case_index >= len(cases):
        return jsonify({"error": "Invalid case index"}), 400

    cases[case_index]["bookmarked"] = bookmarked
    ctx["cases"] = cases  # Mutate to trigger save in FirestoreBackedDict

    return jsonify({"status": "ok", "bookmarked": bookmarked})
