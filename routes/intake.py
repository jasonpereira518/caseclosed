import re

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from models.context import get_or_create_context
from services.jobs import create_job, update_job
from services.request_context import resolve_matter_id
from services.task_queue import enqueue_job
from services.tenancy import AuthorizationError

intake_bp = Blueprint("intake", __name__)

# The intake block in the description is marker-delimited so a resubmission
# replaces it in place instead of stacking duplicates. Legacy descriptions
# with an unmarked block keep it as history; the marked block is appended.
INTAKE_START = "===== CASE INTAKE ====="
INTAKE_END = "===== END CASE INTAKE ====="
_INTAKE_BLOCK = re.compile(re.escape(INTAKE_START) + r".*?" + re.escape(INTAKE_END), re.DOTALL)

@intake_bp.route("/intake", methods=["POST"])
@login_required
def process_intake():
    payload = request.json or {}
    context_id = resolve_matter_id(payload)
    if not context_id:
        return jsonify({"error": "No context_id provided"}), 400

    uid = str(current_user.get_id())
    ctx = get_or_create_context(context_id, uid)
    if ctx is None:
        return jsonify({"error": "forbidden"}), 403

    case_title = str(payload.get("case_title") or "").strip()
    legal_category = str(payload.get("legal_category") or "").strip()
    jurisdiction = str(payload.get("jurisdiction") or "").strip()
    court_level = str(payload.get("court_level") or "").strip()
    user_role = str(payload.get("user_role") or "").strip()
    description = str(payload.get("description") or "").strip()
    key_dates = payload.get("key_dates", [])
    if not isinstance(key_dates, list) or any(not isinstance(item, dict) for item in key_dates):
        return jsonify({"error": "key_dates must be an array of objects"}), 400
    prior_legal_actions = str(payload.get("prior_legal_actions") or "").strip()
    opposing_party = str(payload.get("opposing_party") or "").strip()

    previous_intake = dict(ctx.get("intake") or {})
    ctx["intake"] = payload

    # The intake title tracks the matter title until the user manually
    # renames; a rename is never overwritten by a later intake edit.
    previous_case_title = str(previous_intake.get("case_title") or "").strip()
    if case_title and ctx["title"] in ("New Session", "", previous_case_title):
        ctx["title"] = case_title

    if user_role:
        ctx["role"] = user_role.strip().lower()

    formatted = f"""CASE INTAKE
Title: {case_title}
Category: {legal_category}
Jurisdiction: {jurisdiction}
Court Level: {court_level}
Role: {user_role}

Description:
{description}"""

    if key_dates:
        formatted += "\n\nKey Dates:\n"
        for date_obj in key_dates:
            formatted += f"• {date_obj.get('date', 'Unknown')} — {date_obj.get('label', '')}\n"

    if prior_legal_actions:
        formatted += f"\nPrior Legal Actions:\n{prior_legal_actions}"

    if opposing_party:
        formatted += f"\n\nOpposing Party: {opposing_party}"

    block = f"{INTAKE_START}\n{formatted}\n{INTAKE_END}"
    existing_description = str(ctx.get("description") or "")
    updating = INTAKE_START in existing_description
    if updating:
        ctx["description"] = _INTAKE_BLOCK.sub(block, existing_description, count=1).strip()
    else:
        ctx["description"] = (existing_description + "\n\n" + block).strip()

    messages = list(ctx.get("messages") or [])
    messages.append({
        "role": "user",
        "content": formatted.replace("CASE INTAKE", "CASE INTAKE (UPDATED)", 1) if updating else formatted,
    })
    ctx["messages"] = messages

    # The structured-analysis chain runs in a "matter_analysis" job against
    # the description just persisted above; the payload is empty so the job
    # body falls back to the matter's stored description.
    try:
        job, created = create_job(context_id, uid, "matter_analysis", {})
        if created:
            enqueue_job(context_id, job["job_id"])
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    except Exception as exc:
        if "job" in locals():
            update_job(context_id, job["job_id"], status="failed", stage="enqueue_failed",
                       error={"code": "enqueue_failed", "message": str(exc)[:300]})
        return jsonify({"error": "unable to queue analysis"}), 503
    job["status_url"] = f"/api/matters/{context_id}/jobs/{job['job_id']}"
    job["context_id"] = context_id
    job["title"] = ctx["title"]
    return jsonify(job), 202
