"""Tests for the public sandboxed demo at /demo.

The point of these tests is the isolation guarantee. /demo is unauthenticated
and publicly reachable, so it must never be able to spend an LLM call, hit
CourtListener, or touch Firestore. That is enforced structurally — routes/demo.py
imports no service module — and the import test below is what stops someone
adding a convenience import later and quietly breaking it.
"""

import ast
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")

from app import app  # noqa: E402
from routes import demo as demo_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_IMPORT_ROOTS = {"services", "models", "firebase_admin", "google", "requests"}


class DemoRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    # ---------------------------------------------------------------- access

    def test_demo_renders_without_authentication(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        # The matter itself is injected client-side from the fixture, so the
        # server response is asserted on the shell rather than on its content.
        self.assertIn("demo.js", body)
        self.assertIn('data-demo="1"', body)
        for panel in ("tab-record", "tab-chronology", "tab-authority", "tab-draft"):
            self.assertIn(panel, body)

    def test_demo_is_labelled_as_synthetic(self):
        """A visitor must never be able to mistake the fixture for a real matter."""
        body = self.client.get("/demo").get_data(as_text=True)
        self.assertIn("Demonstration.", body)
        self.assertIn("synthetic", body)

    def test_demo_allows_same_origin_framing_only(self):
        """The landing page frames this route; nobody else may."""
        response = self.client.get("/demo")
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("frame-ancestors 'self'", response.headers.get("Content-Security-Policy", ""))

    def test_fixture_endpoint_serves_valid_json(self):
        response = self.client.get("/demo/fixture")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.get_data(as_text=True))
        for key in ("title", "analysis", "timeline", "statutes", "cases", "draft"):
            self.assertIn(key, payload)
        self.assertTrue(payload["cases"])

    def test_fixture_citations_are_marked_fictional(self):
        """LANDING_PAGE_IMPLEMENTATION_PLAN.md §12 forbids fabricating a citation
        that could be mistaken for real authority."""
        payload = json.loads(self.client.get("/demo/fixture").get_data(as_text=True))
        for case in payload["cases"]:
            self.assertIn("Fict.", case["citation"], f"{case['title']} is not marked fictional")

    # ------------------------------------------------------------- isolation

    def test_demo_module_imports_no_service_layer(self):
        """Structural guarantee: the module cannot reach Gemini, CourtListener
        or Firestore because it has no import path to any of them."""
        source = (REPO_ROOT / "routes" / "demo.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imported_roots.add(node.module.split(".")[0])
                elif node.level:
                    self.fail(f"routes/demo.py uses a relative import: {ast.dump(node)}")

        offending = imported_roots & FORBIDDEN_IMPORT_ROOTS
        self.assertEqual(
            offending,
            set(),
            f"routes/demo.py must not import {offending}. The demo is public and "
            f"unauthenticated; it must have no path to an LLM, an external API, or the database.",
        )

    def test_demo_is_not_in_protected_json_paths(self):
        """/demo must stay publicly reachable rather than 401-ing as JSON."""
        from app import PROTECTED_JSON_PATHS

        self.assertNotIn("/demo", PROTECTED_JSON_PATHS)
        self.assertNotIn("/demo/fixture", PROTECTED_JSON_PATHS)

    def test_client_sandbox_shim_is_loaded_before_the_app_script(self):
        """demo.js replaces window.fetch, so it has to run first."""
        body = self.client.get("/demo").get_data(as_text=True)
        self.assertLess(
            body.index("demo.js"),
            body.index("script.js"),
            "demo.js must be loaded before script.js or the fetch shim misses early calls",
        )

    # ------------------------------------------------ the real app is unchanged

    def test_workspace_still_requires_login(self):
        response = self.client.get("/app")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
