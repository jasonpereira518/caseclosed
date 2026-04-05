from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.context import get_context as get_stored_context, get_or_create_context
from services.llm import extract_structured_analysis, extract_timeline, sort_timeline, extract_statutes, extract_case_strength


analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("/analyze", methods=["POST"])
@login_required
def analyze():
    """Extract structured analysis from text or use existing context."""
    payload = request.json or {}
    text = payload.get("text", "").strip()
    context_id = payload.get("context_id")

    uid = str(current_user.get_id())
    if not text and context_id:
        context = get_stored_context(context_id, uid)
        text = context.get("description", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    analysis = extract_structured_analysis(text)
    timeline = extract_timeline(text)
    statutes = extract_statutes(text, analysis)

    # Note logic explicitly requested by user mapping
    strength = extract_case_strength(text, analysis, statutes, context.get("cases", []) if context_id else [])

    # Update context if provided
    if context_id:
        ctx = get_or_create_context(context_id, uid)
        if ctx is None:
            return jsonify({"error": "forbidden"}), 403
        ctx["analysis"] = analysis
        ctx["timeline"] = timeline
        ctx["statutes"] = statutes
        ctx["strength"] = strength
        if not ctx["description"]:
            ctx["description"] = text

    return jsonify({"status": "success", "analysis": analysis, "timeline": timeline, "statutes": statutes, "strength": strength, "context_id": context_id})


@analyze_bp.route("/timeline/add", methods=["POST"])
@login_required
def add_timeline_event():
    payload = request.json or {}
    context_id = payload.get("context_id")
    if not context_id:
        return jsonify({"error": "Missing context_id"}), 400
        
    uid = str(current_user.get_id())
    ctx = get_stored_context(context_id, uid)
    if not ctx:
        return jsonify({"error": "forbidden or not found"}), 403
        
    date_val = payload.get("date", "").strip()
    desc_val = payload.get("description", "").strip()
    cat_val = payload.get("category", "other").strip()
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
