"""Public, sandboxed demonstration of the workspace.

Serves the real workspace template with a fixture matter so the landing page
can show the actual product instead of a hand-maintained replica of it.

ISOLATION IS STRUCTURAL, NOT INCIDENTAL. This module deliberately imports no
service layer: no ``services.llm``, no ``services.courtlistener``, no
``services.firestore``, no ``models``. It cannot reach Gemini, CourtListener or
Firestore because it has no path to them. ``tests/test_demo_route.py`` asserts
this by inspecting the module's imports, so the guarantee cannot regress
quietly when someone later adds a convenience import.

The client-side half of the sandbox lives in ``static/demo.js``, which replaces
``window.fetch`` so that every request the workspace would normally make is
answered from the same fixture without touching the network.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template

demo_bp = Blueprint("demo", __name__)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "static" / "demo-fixture.json"


@lru_cache(maxsize=1)
def load_fixture() -> dict:
    """Read the synthetic matter once and memoize it.

    Returns an empty dict if the file is missing or malformed so that a broken
    fixture degrades the demo rather than taking down the landing page that
    frames it.
    """
    try:
        with FIXTURE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@demo_bp.route("/demo")
def demo_workspace():
    """Render the workspace with fixture data, unauthenticated and inert."""
    fixture = load_fixture()
    if not fixture:
        abort(503, "Demo fixture unavailable")

    response = render_template(
        "workspace.html",
        demo_mode=True,
        user_name="Jordan Parker",
        user_email="demo@example.com",
        user_profile_pic=None,
    )
    # The landing page frames this route in an iframe on the same origin.
    # Deny cross-origin framing without denying our own.
    return response, 200, {
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
        "Cache-Control": "public, max-age=300",
    }


@demo_bp.route("/demo/fixture")
def demo_fixture():
    """The synthetic matter as JSON.

    ``static/demo.js`` fetches this once and answers every subsequent workspace
    request from it locally.
    """
    fixture = load_fixture()
    if not fixture:
        abort(503, "Demo fixture unavailable")
    return jsonify(fixture)
