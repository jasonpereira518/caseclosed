from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.context import get_context as get_stored_context
from services.jobs import create_job, update_job
from services.llm import sort_timeline
from services.request_context import resolve_matter_id
from services.task_queue import enqueue_job
from services.tenancy import AuthorizationError


analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("/analyze", methods=["POST"])
@login_required
def analyze():
    """Queue a matter_analysis job; all LLM work runs in the job."""
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    matter_id = resolve_matter_id(payload)
    if not matter_id:
        return jsonify({"error": "matter_id is required"}), 400

    uid = str(current_user.get_id())
    try:
        job, created = create_job(matter_id, uid, "matter_analysis", {"text": text})
        if created:
            enqueue_job(matter_id, job["job_id"])
    except AuthorizationError:
        return jsonify({"error": "forbidden"}), 403
    except Exception as exc:
        if "job" in locals():
            update_job(matter_id, job["job_id"], status="failed", stage="enqueue_failed",
                       error={"code": "enqueue_failed", "message": str(exc)[:300]})
        return jsonify({"error": "unable to queue analysis"}), 503
    job["status_url"] = f"/api/matters/{matter_id}/jobs/{job['job_id']}"
    job["context_id"] = matter_id
    return jsonify(job), 202


@analyze_bp.route("/timeline/add", methods=["POST"])
@login_required
def add_timeline_event():
    payload = request.json or {}
    context_id = resolve_matter_id(payload)
    if not context_id:
        return jsonify({"error": "Missing context_id"}), 400
        
    uid = str(current_user.get_id())
    ctx = get_stored_context(context_id, uid)
    if not ctx:
        return jsonify({"error": "forbidden or not found"}), 403
        
    date_val = str(payload.get("date") or "").strip()
    desc_val = str(payload.get("description") or "").strip()
    cat_val = str(payload.get("category") or "other").strip()
    if cat_val not in {"incident", "event"}:
        cat_val = "event"
        
    if not date_val and not desc_val:
        return jsonify({"error": "Missing event data"}), 400
        
    new_event = {
        "date": date_val,
        "description": desc_val,
        "category": cat_val,
        "source": "manual"
    }
    
    current_timeline = ctx.get("timeline", [])
    if not isinstance(current_timeline, list):
        current_timeline = []
        
    current_timeline.append(new_event)
    current_timeline = sort_timeline(current_timeline)
    
    ctx["timeline"] = current_timeline
    return jsonify({"status": "success", "timeline": current_timeline})
