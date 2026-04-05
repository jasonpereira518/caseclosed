import re
import requests

import config

def query_courtlistener(query: str):
    import re
    query = re.sub(r'[{}\[\]\\`"\'()]', '', query).strip()
    base = config.COURTLISTENER_BASE_URL
    headers = {}
    if config.COURTLISTENER_TOKEN:
        headers["Authorization"] = f"Token {config.COURTLISTENER_TOKEN}"
    resp = requests.get(base, params={"q": query}, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", []):
        title = item.get("caseName") or item.get("name") or "Untitled"
        citation = item.get("citation") or ""
        pdf_link = item.get("absolute_url") or item.get("url") or ""
        if pdf_link.startswith("/"):
            pdf_link = "https://www.courtlistener.com" + pdf_link
        snippet = item.get("snippet") or item.get("summary") or ""
        decision_date = item.get("decision_date") or ""
        results.append({
            "title": title,
            "citation": citation,
            "pdf_link": pdf_link,
            "snippet": snippet,
            "decision_date": decision_date,
        })
    return results[:4]


def extract_cluster_id(pdf_link: str):
    """Extract CourtListener cluster_id from the case's pdf_link/absolute_url."""
    if not pdf_link:
        return None
    match = re.search(r'/opinion/(\d+)/', pdf_link)
    if match:
        return match.group(1)
    return None


def check_case_treatment(cluster_id: str, citation_string: str = "") -> dict:
    """Check if case has been overturned or negatively treated using citing search."""
    base_treatment = {
        "status": "unknown",
        "label": "",
        "details": "",
        "checked": True
    }
    
    if not cluster_id:
        return base_treatment
        
    base = config.COURTLISTENER_BASE_URL
    headers = {}
    if config.COURTLISTENER_TOKEN:
        headers["Authorization"] = f"Token {config.COURTLISTENER_TOKEN}"
        
    query = f"cites:({cluster_id}) AND (overruled OR superseded OR overturned OR distinguished OR criticized OR questioned OR limited)"
    
    try:
        resp = requests.get(base, params={"q": query, "type": "o"}, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        results = data.get("results", [])
        if not results:
            base_treatment["status"] = "good"
            base_treatment["label"] = "✓ No Negative Treatment Found"
            return base_treatment
            
        is_negative = False
        is_warning = False
        details_case = ""
        negative_verb = "Overturned"
        warning_verb = "Distinguished"
        
        for item in results:
            snippet = (item.get("snippet") or item.get("summary") or "").lower()
            if not snippet:
                continue
                
            if "overruled" in snippet or "overturned" in snippet:
                is_negative = True
                negative_verb = "Overturned"
                details_case = item.get("caseName") or item.get("name") or "a subsequent case"
                break
            elif "superseded" in snippet:
                is_negative = True
                negative_verb = "Superseded"
                details_case = item.get("caseName") or item.get("name") or "a subsequent case"
                break
            elif "distinguished" in snippet:
                is_warning = True
                warning_verb = "Distinguished"
                if not details_case:
                    details_case = item.get("caseName") or item.get("name") or "a subsequent case"
            elif "criticized" in snippet:
                is_warning = True
                warning_verb = "Criticized"
                if not details_case:
                    details_case = item.get("caseName") or item.get("name") or "a subsequent case"
            elif "questioned" in snippet or "limited" in snippet:
                is_warning = True
                if "questioned" in snippet:
                    warning_verb = "Questioned"
                else:
                    warning_verb = "Limited"
                if not details_case:
                    details_case = item.get("caseName") or item.get("name") or "a subsequent case"
                    
        if is_negative:
            base_treatment["status"] = "negative"
            base_treatment["label"] = f"⚠ Possibly {negative_verb}"
            base_treatment["details"] = f"Cited as {negative_verb.lower()} in {details_case}"
        elif is_warning:
            base_treatment["status"] = "warning"
            base_treatment["label"] = f"⚠ Possibly {warning_verb}"
            base_treatment["details"] = f"Cited as {warning_verb.lower()} in {details_case}"
        else:
            base_treatment["status"] = "good"
            base_treatment["label"] = "✓ No Negative Treatment Found"
            
    except Exception as e:
        # Don't crash on rate limits or API failures
        pass
        
    return base_treatment
