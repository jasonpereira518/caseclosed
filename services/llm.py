import json

from google import genai

import config
from utils.helpers import extract_json_object


# Setup Vertex AI Client and Model Endpoints
# Note: Using Gemini 2.5 for optimal performance/cost balance
# Configuration managed via environment variables for security
client = genai.Client(
    vertexai=True,
    project=config.PROJECT_ID,
    location=config.GOOGLE_CLOUD_LOCATION,
)

# Independent agents
clarifier_agent = client.chats.create(model=config.CLARIFIER_MODEL)
summarizer_agent = client.chats.create(model=config.SUMMARIZER_MODEL)
scorer_agent = client.chats.create(model=config.SCORER_MODEL)
analyzer_agent = client.chats.create(model=config.ANALYZER_MODEL)
draft_agent = client.chats.create(model=config.DRAFT_MODEL)
query_agent = client.chats.create(model=config.QUERY_MODEL)


def ask_clarifying_questions(user_input: str, existing_analysis: dict = None, description: str = "") -> list:
    """
    Generate up to 3 clarifying legal questions relevant to building a case argument.
    Avoid repeating questions about information already in `existing_analysis` or `description`.
    """
    context_text = ""

    if existing_analysis:
        context_text += "KNOWN INFORMATION:\n"
        for key, val in existing_analysis.items():
            if val:
                context_text += f"- {key}: {json.dumps(val, indent=2)}\n"
    if description:
        context_text += f"\nFULL CASE DESCRIPTION (so far):\n{description}\n"

    prompt = (
        f"You are a professional legal paralegal assisting a lawyer in building a legal argument.\n"
        f"Given the user's most recent message:\n'{user_input}'\n\n"
        f"And the known case context below:\n{context_text}\n"
        "Ask up to 3 clarifying questions **only** about information that is missing and critical for legal analysis — "
        "such as damages, contract terms, jurisdiction, causes of action, or key facts.\n"
        "Do NOT ask about information already in the context.\n"
        "If you already have sufficient facts, respond exactly with 'NO QUESTIONS NEEDED'."
    )

    try:
        response = clarifier_agent.send_message(prompt)
        lines = [q.strip() for q in response.text.splitlines() if q.strip()]
        if any("NO QUESTIONS NEEDED" in q.upper() for q in lines):
            return []
        return lines[:3]
    except Exception as e:
        return [f"[Error asking clarifications: {e}]"]


def extract_answers_from_message(user_message: str, questions: list) -> dict:
    """Extract answers to questions from user's message."""
    prompt = (
        f"Given these questions:\n" + "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)]) + "\n\n"
        f"And this user response: '{user_message}'\n\n"
        "Extract the answers to each question from the user's response. "
        "Respond strictly in JSON format:\n"
        "{\n"
        '  "answers": {"1": "answer to question 1 or empty string if not answered", "2": "...", "3": "..."},\n'
        '  "has_sufficient_info": true/false\n'
        "}\n"
        "If the user's message doesn't answer a question, use an empty string for that answer. "
        "Set has_sufficient_info to false if critical information is still missing."
    )
    try:
        response = clarifier_agent.send_message(prompt)
        text = response.text.strip()
        parsed = extract_json_object(text)
        if parsed:
            return {
                "answers": parsed.get("answers", {}),
                "has_sufficient_info": parsed.get("has_sufficient_info", False)
            }
    except Exception:
        pass
    return {"answers": {}, "has_sufficient_info": False}


def filter_redundant_questions(questions, analysis):
    """
    Remove clarifying questions that are already covered by the analysis context.
    """
    if not analysis:
        return questions

    answered_keys = {k for k, v in analysis.items() if v}
    filtered = []
    for q in questions:
        lower_q = q.lower()
        if any(keyword in lower_q for keyword in answered_keys):
            continue
        filtered.append(q)
    return filtered


def check_if_more_info_needed(user_message: str, existing_context: str, analysis: dict = None) -> tuple:
    """
    Check if more information is needed and return up to 3 questions.
    Includes full description and structured analysis to avoid repeat questions.
    """
    context_text = ""
    if analysis:
        context_text += "CURRENT STRUCTURED ANALYSIS:\n"
        for key, val in analysis.items():
            if val:
                context_text += f"- {key}: {json.dumps(val, indent=2)}\n"

    combined = (existing_context + " " + user_message).strip()

    prompt = (
        f"You are a legal paralegal assistant reviewing a client's case.\n"
        f"Below is the full information currently known:\n{context_text}\n\n"
        f"Case description:\n{combined}\n\n"
        "Determine if critical legal information is missing for analysis "
        "(facts, jurisdiction, parties, legal issues, causes of action).\n"
        "Respond strictly in JSON format:\n"
        "{\n"
        '  "needs_more_info": true/false,\n'
        '  "questions": ["question 1", "question 2", ...]\n'
        "}\n"
        "Only ask questions if *essential* facts are missing, and avoid duplicates of already known information."
    )

    try:
        response = clarifier_agent.send_message(prompt)
        text = response.text.strip()
        parsed = extract_json_object(text)
        if parsed:
            needs_more = parsed.get("needs_more_info", False)
            questions = parsed.get("questions", [])
            if not isinstance(questions, list):
                questions = []
            # Filter redundant ones before returning
            questions = filter_redundant_questions(questions, analysis)
            return needs_more, questions
    except Exception:
        pass
    return False, []


def summarize_case(text: str) -> str:
    prompt = f"Summarize this legal situation clearly and factually for use in a case law search:\n\n{text}"
    try:
        response = summarizer_agent.send_message(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Error summarizing: {e}]"


def extract_structured_analysis(text: str) -> dict:
    """Extract structured facts, jurisdictions, parties, issues, causes of action, and penal codes."""
    prompt = (
        f"Analyze this legal text and extract comprehensive structured information:\n\n{text}\n\n"
        "Respond strictly in JSON format with the following structure:\n"
        "{\n"
        '  "facts": ["detailed fact1", "detailed fact2", ...],\n'
        '  "jurisdictions": ["jurisdiction1", ...],\n'
        '  "parties": [{"name": "party1", "role": "plaintiff/defendant/other", "details": "additional info"}, ...],\n'
        '  "legal_issues": ["detailed issue1 with context", "detailed issue2", ...],\n'
        '  "causes_of_action": ["detailed cause1", "detailed cause2", ...],\n'
        '  "penal_codes": [{"code": "PC 123", "description": "description of the code", "relevance": "why it applies"}, ...]\n'
        "}\n"
        "Be thorough and extract all relevant information. For penal codes, include any relevant state or federal codes "
        "(e.g., 'PC 187' for California Penal Code, '18 U.S.C. § 1001' for federal). Include descriptions and why each code is relevant. "
        "If information is not available, use empty arrays."
    )
    try:
        response = analyzer_agent.send_message(prompt)
        text = response.text.strip()
        parsed = extract_json_object(text)
        if parsed:
            return {
                "facts": parsed.get("facts", []),
                "jurisdictions": parsed.get("jurisdictions", []),
                "parties": parsed.get("parties", []),
                "legal_issues": parsed.get("legal_issues", []),
                "causes_of_action": parsed.get("causes_of_action", []),
                "penal_codes": parsed.get("penal_codes", [])
            }
    except Exception:
        pass
    return {
        "facts": [],
        "jurisdictions": [],
        "parties": [],
        "legal_issues": [],
        "causes_of_action": [],
        "penal_codes": []
    }


def generate_query(summary: str, analysis: dict = None) -> str:
    """Generate search query using summary and structured analysis."""
    context = ""
    if analysis:
        issues = ", ".join(analysis.get("legal_issues", []))
        causes = ", ".join(analysis.get("causes_of_action", []))
        jurisdictions = ", ".join(analysis.get("jurisdictions", []))
        context = f"\n\nExtracted Legal Issues: {issues}\nCauses of Action: {causes}\nJurisdictions: {jurisdictions}"

    prompt = (
        f"Generate exactly 5 words of short keyword-style legal search terms for CourtListener "
        + f"querying purposes based on the following summary and analysis. Output ONLY the 5 keywords with "
        + f"no numbering or explanation: \n\nSummary:\n{summary},\n\nAnalysis{context}"
    )
    try:
        query_agent = client.chats.create(model=config.QUERY_MODEL)
        response = query_agent.send_message(prompt)
        return response.text.strip() or summary
    except Exception:
        return summary


def grade_case(summary: str, case_title: str, snippet: str, analysis: dict = None) -> dict:
    # Build context from structured analysis if available
    context = ""
    if analysis:
        issues = ", ".join(analysis.get("legal_issues", [])) or ", ".join(analysis.get("issues", []))
        causes = ", ".join(analysis.get("causes_of_action", []))
        if issues or causes:
            context = "\n\nUser's Legal Context:\n"
            if issues:
                context += f"- Legal Issues: {issues}\n"
            if causes:
                context += f"- Causes of Action: {causes}\n"

    # Stronger, more structured grading prompt
    prompt = f"""
        You are an experienced legal research assistant.
        Your task is to assess how relevant the following case is to the user's described legal issue.

        User's Description:
        {summary}{context}

        Case to Evaluate:
        Title: {case_title}
        Excerpt: {snippet}

        Instructions:
        - Provide a relevance score from 0 to 100.
        - Consider overlap in facts, legal issues, causes of action, and jurisdictional or procedural context.
        - Be moderately lenient: if there is any meaningful thematic or factual connection, assign at least a partial score (e.g., 30–60 range).
        - Reserve very low scores (0–20) only for completely unrelated or irrelevant cases.
        - Higher scores (70–100) indicate strong legal and factual alignment.
        - Be fair, consistent, and nuanced — reward partial matches.
        - Output ONLY valid JSON in this exact format:
        {{"score": <integer>, "reason": "<one-sentence reason>"}}
    """

    try:
        response = scorer_agent.send_message(prompt)
        text = response.text.strip()
        parsed = extract_json_object(text) or {}
        score = int(parsed.get("score", 50))
        reason = parsed.get("reason", "No reason given.")
    except Exception as e:
        score, reason = 50, f"[Error grading case: {e}]"

    # Normalize and return safe output
    return {
        "score": max(0, min(100, score)),
        "reason": reason.strip()
    }


def draft_legal_document(context: dict, doc_type: str = "memo") -> str:
    """Generate professional legal memo or brief."""
    analysis = context.get("analysis", {})
    summary = context.get("summary", "")
    cases = context.get("cases", [])

    facts = "\n".join([f"- {f}" for f in analysis.get("facts", [])])
    issues = "\n".join([f"- {i}" for i in analysis.get("legal_issues", [])])
    parties = "\n".join([f"- {p.get('name', 'Unknown')} ({p.get('role', 'Unknown')})" for p in analysis.get("parties", [])])
    jurisdictions = ", ".join(analysis.get("jurisdictions", []))
    causes = "\n".join([f"- {c}" for c in analysis.get("causes_of_action", [])])

    relevant_cases = "\n\n".join([
        f"**{c.get('title', 'Unknown')}** ({c.get('citation', 'No citation')})\n"
        f"Relevance: {c.get('relevance_score', 0)}% - {c.get('relevance_reason', '')}\n"
        f"Snippet: {c.get('snippet', '')[:200]}..."
        for c in cases[:5]
    ])

    prompt = (
        f"Generate a professional legal {doc_type} with the following structure:\n\n"
        f"**FACTS**\n{facts if facts else summary}\n\n"
        f"**PARTIES**\n{parties if parties else 'To be determined'}\n\n"
        f"**JURISDICTION**\n{jurisdictions if jurisdictions else 'To be determined'}\n\n"
        f"**LEGAL ISSUES**\n{issues if issues else 'To be determined'}\n\n"
        f"**CAUSES OF ACTION**\n{causes if causes else 'To be determined'}\n\n"
        f"**APPLICABLE LAW**\nBased on the following relevant cases:\n{relevant_cases}\n\n"
        f"**ANALYSIS**\nProvide a thorough legal analysis connecting the facts to the applicable law.\n\n"
        f"**CONCLUSION**\nProvide a clear conclusion with recommendations.\n\n"
        "Use professional legal writing style, proper citations, and clear reasoning."
    )

    try:
        response = draft_agent.send_message(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Error drafting document: {e}]"
