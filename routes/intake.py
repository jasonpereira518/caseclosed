from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
import traceback

from models.context import get_context as get_stored_context, get_or_create_context, save_context
from services.llm import extract_structured_analysis, extract_timeline, extract_statutes, extract_case_strength

intake_bp = Blueprint("intake", __name__)

@intake_bp.route("/intake", methods=["POST"])
@login_required
def process_intake():
    payload = request.json or {}
    context_id = payload.get("context_id")
    if not context_id:
        return jsonify({"error": "No context_id provided"}), 400

    uid = current_user.id
    ctx = get_or_create_context(context_id, uid)
    if ctx is None:
        return jsonify({"error": "forbidden"}), 403

    case_title = payload.get("case_title", "").strip()
    legal_category = payload.get("legal_category", "").strip()
    jurisdiction = payload.get("jurisdiction", "").strip()
    court_level = payload.get("court_level", "").strip()
    user_role = payload.get("user_role", "").strip()
    description = payload.get("description", "").strip()
    key_dates = payload.get("key_dates", [])
    prior_legal_actions = payload.get("prior_legal_actions", "").strip()
    opposing_party = payload.get("opposing_party", "").strip()

    ctx["intake"] = payload
    
    if ctx["title"] in ("New Session", "") and case_title:
        ctx["title"] = case_title

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
        
    ctx["description"] = (ctx["description"] + "\n\n" + formatted).strip()
    
    ctx["messages"].append({
        "role": "user",
        "content": formatted
    })

    try:
        analysis = extract_structured_analysis(ctx["description"])
        timeline = extract_timeline(ctx["description"])
        statutes = extract_statutes(ctx["description"], analysis)
        strength = extract_case_strength(ctx["description"], analysis, statutes, ctx.get("cases", []))

        ctx["analysis"] = analysis
        ctx["timeline"] = timeline
        ctx["statutes"] = statutes
        ctx["strength"] = strength
        
        save_context(context_id, ctx)
        
        return jsonify({
            "status": "success", 
            "analysis": analysis, 
            "timeline": timeline, 
            "statutes": statutes, 
            "strength": strength, 
            "context_id": context_id,
            "title": ctx["title"],
            "messages": ctx["messages"]
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
