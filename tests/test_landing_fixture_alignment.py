"""The landing page and the demo fixture must tell the same story.

The landing page advertises concrete numbers (documents, events, issues,
authorities) and previews matter content. Both must come from the one
synthetic matter in static/demo-fixture.json — and the fixture's rule is that
every case name is invented, so real authority can never be mistaken for a
product claim.
"""
import json
import re
import unittest
from pathlib import Path

from app import app

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "static" / "demo-fixture.json").read_text())
LANDING_JS = (ROOT / "static" / "landing.js").read_text()

# Real decisions that previously appeared in the product-tab preview content.
REAL_CASE_NAMES = ("Kwan", "Andalex", "Gorman-Bakos", "Cornell", "Summa", "Hofstra")


class LandingFixtureAlignmentTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_outcome_row_numbers_match_the_fixture(self):
        html = self.client.get("/").data.decode()
        counts = [int(value) for value in re.findall(r'data-count="(\d+)"', html)]

        expected = [
            len(FIXTURE["uploaded_documents"]),
            len(FIXTURE["timeline"]),
            len(FIXTURE["analysis"]["legal_issues"]),
            len(FIXTURE["cases"]),
            1,  # one memo draft
        ]
        self.assertEqual(counts, expected)

    def test_product_previews_use_no_real_case_names(self):
        for name in REAL_CASE_NAMES:
            self.assertNotIn(name, LANDING_JS)

    def test_product_previews_draw_from_the_fixture_matter(self):
        # The preview content must be the Rivera matter, not a second
        # hand-maintained fictional matter that can drift.
        self.assertIn("Rivera", LANDING_JS)
        fixture_case_names = [case["title"].split(" v.")[0] for case in FIXTURE["cases"]]
        previewed = [name for name in fixture_case_names if name in LANDING_JS]
        self.assertGreaterEqual(
            len(previewed), 2,
            f"expected the authority preview to cite fixture cases, found {previewed}",
        )

    def test_fixture_narrative_matches_its_own_case_count(self):
        joined = " ".join(m["content"] for m in FIXTURE["messages"])
        self.assertNotIn("nine authorities", joined)


class DemoEnhancementTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_fixture_has_seeded_chat_questions(self):
        seeded = FIXTURE.get("seeded_chat")
        self.assertIsInstance(seeded, list)
        self.assertGreaterEqual(len(seeded), 3)
        for entry in seeded:
            self.assertTrue(entry.get("question"))
            self.assertTrue(entry.get("answer"))

    def test_demo_page_has_a_conversion_cta_that_escapes_the_iframe(self):
        html = self.client.get("/demo").data.decode()
        cta = re.search(r'<a[^>]*class="[^"]*demo-start-cta[^"]*"[^>]*>', html)
        self.assertIsNotNone(cta, "demo page is missing the start-your-own-matter CTA")
        self.assertIn('target="_top"', cta.group(0))
        self.assertIn("/auth/login", cta.group(0))

    def test_demo_page_account_name_is_not_a_link(self):
        html = self.client.get("/demo").data.decode()
        self.assertIn('<span class="account-name">', html)
        self.assertNotIn('<a class="account-name"', html)

    def test_real_workspace_account_name_is_still_a_link(self):
        from unittest.mock import patch
        from models.user import User

        with self.client.session_transaction() as session:
            session["_user_id"] = "test-user"
            session["_fresh"] = True
        with patch("models.user.load_user") as load_user:
            load_user.return_value = User(
                id="test-user", email="lawyer@example.com",
                name="Jordan Parker", profile_pic=None,
            )
            html = self.client.get("/app").data.decode()
        self.assertIn('<a class="account-name"', html)

    def test_demo_page_loads_the_tour_script(self):
        html = self.client.get("/demo").data.decode()
        self.assertIn("demo-tour.js", html)
        self.assertIn("demo-tour-start", html)

    def test_real_workspace_never_loads_demo_scripts(self):
        from unittest.mock import patch
        from models.user import User

        with self.client.session_transaction() as session:
            session["_user_id"] = "test-user"
            session["_fresh"] = True
        with patch("models.user.load_user") as load_user:
            load_user.return_value = User(
                id="test-user", email="lawyer@example.com",
                name="Jordan Parker", profile_pic=None,
            )
            html = self.client.get("/app").data.decode()
        self.assertNotIn("demo-tour.js", html)
        self.assertNotIn("demo.js", html)


if __name__ == "__main__":
    unittest.main()
