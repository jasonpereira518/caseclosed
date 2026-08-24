"""Structural tests for the rebuilt account centre.

The page is server-rendered markup plus one client script, so these assert the
contract the two share: the tablist wiring the sub-nav depends on, the route
variables the template must actually consume, and the absence of the classes and
native dialogs the rebuild removed.

They are deliberately structural. Behaviour lives in
tests/test_account_client_script.py, which executes static/account.js for real.
"""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from models.user import User

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_JS = (REPO_ROOT / "static" / "account.js").read_text()
APP_CSS = (REPO_ROOT / "static" / "app.css").read_text()
SCRIPT_JS = (REPO_ROOT / "static" / "script.js").read_text()

SECTIONS = ("profile", "workspaces", "data", "danger")

# Every field the profile form is responsible for round-tripping.
PROFILE_FIELDS = (
    "display_name", "job_title", "organization", "phone", "timezone",
    "bar_number", "jurisdictions", "practice_areas", "office_address", "bio",
    "notification_email",
)

# Classes the rebuild deleted. Their CSS is gone, so markup referencing them
# would render unstyled rather than fail loudly.
RETIRED_CLASSES = (
    "account-center", "account-panel", "account-inline", "account-status",
    "workspace-entry", "workspace-row", "member-row", "matter-assignment",
    "team-manager", "team-activity", "activity-row", "activity-meta",
    "activity-event",
)


class AccountCenterPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(
            id="test-user",
            email="lawyer@example.com",
            name="Jordan Parker",
            profile_pic=None,
        )

    def _sign_in(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True

    def _page(self):
        with patch("models.user.load_user", return_value=self.user):
            self._sign_in()
            response = self.client.get("/account")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    # ------------------------------------------------------------- structure

    def test_sub_nav_is_a_wired_tablist(self):
        body = self._page()

        self.assertIn('role="tablist"', body)
        self.assertIn('aria-orientation="vertical"', body)

        for section in SECTIONS:
            self.assertIn(f'id="tab-{section}"', body)
            self.assertIn(f'aria-controls="pane-{section}"', body)
            self.assertIn(f'id="pane-{section}"', body)
            self.assertIn(f'aria-labelledby="tab-{section}"', body)

        self.assertEqual(len(re.findall(r'role="tab"', body)), len(SECTIONS))
        self.assertEqual(len(re.findall(r'role="tabpanel"', body)), len(SECTIONS))
        # Exactly one section may be open on arrival.
        self.assertEqual(len(re.findall(r'aria-selected="true"', body)), 1)

    def test_route_variables_reach_the_page(self):
        """main.account_center passed user_name/user_email/user_profile_pic to a
        template that used none of them, so the page never showed who was signed
        in. This is what stops that regressing."""
        body = self._page()

        self.assertIn("Jordan Parker", body)
        self.assertIn("lawyer@example.com", body)

    def test_profile_form_carries_every_field_grouped(self):
        body = self._page()

        for field in PROFILE_FIELDS:
            self.assertIn(f'name="{field}"', body)

        for group in ("Identity", "Practice", "Contact"):
            self.assertIn(group, body)

    def test_landing_route_assertions_still_hold(self):
        """test_landing_routes.py pins this copy; keep the two in step."""
        body = self._page()

        self.assertIn("Account center", body)
        self.assertIn("Create portable ZIP", body)

    # ---------------------------------------------------------------- wiring

    def test_page_loads_its_own_scripts_and_not_the_workspace(self):
        """script.js boots the workspace via matters.js functions. Loading it
        here would throw ReferenceError and abort init."""
        body = self._page()

        self.assertIn("job-poller.js", body)
        self.assertIn("account.js", body)
        self.assertNotIn("matters.js", body)
        self.assertNotIn("/static/script.js", body)

    def test_ui_primitives_are_global_and_left_script_js(self):
        with patch("models.user.load_user", return_value=self.user):
            self._sign_in()
            self.assertIn("ui.js", self.client.get("/account").get_data(as_text=True))
            self.assertIn("ui.js", self.client.get("/app").get_data(as_text=True))

        with patch("config.CLERK_PUBLISHABLE_KEY", "pk_test_example"), \
                patch("config.CLERK_SECRET_KEY", "sk_test_example"), \
                patch("config.CLERK_FRONTEND_API_URL", "https://clerk.example"):
            self.assertIn("ui.js", self.client.get("/auth/login").get_data(as_text=True))

        # Re-declaring these in script.js would be a SyntaxError once both load.
        for symbol in ("function showToast", "const FOCUSABLE", "let _modalStack",
                       "function openModal", "function escapeHtml"):
            self.assertNotIn(symbol, SCRIPT_JS)

    # --------------------------------------------------------------- hygiene

    def test_retired_classes_are_gone_from_markup_and_stylesheet(self):
        body = self._page()

        for name in RETIRED_CLASSES:
            self.assertNotIn(f'class="{name}"', body)
            self.assertNotIn(f'"{name}"', ACCOUNT_JS)
            self.assertNotIn(f".{name} ", APP_CSS)
            self.assertNotIn(f".{name} {{", APP_CSS)

    def test_no_native_dialogs_remain(self):
        """This page hosts the product's most destructive actions; they go
        through the shared modal component, not browser dialogs."""
        self.assertNotIn("window.prompt", ACCOUNT_JS)
        self.assertNotIn("window.confirm", ACCOUNT_JS)
        self.assertIsNone(re.search(r"(?<![.\w])confirm\(", ACCOUNT_JS))

    def test_account_css_section_uses_tokens_only(self):
        """The old block was the only place in app.css with raw pixels and a hex
        literal. Guard the replacement against the same drift."""
        start = APP_CSS.index("Account centre")
        # The section runs from its banner to the next top-level comment banner.
        end = APP_CSS.index("/* Cycle 1 additions", start)
        rules = APP_CSS[APP_CSS.index("*/", start) + 2:end]
        # Prose explains the pixels it replaced; breakpoints cannot be variables
        # (tokens.css documents this). Neither is a declaration.
        rules = re.sub(r"/\*.*?\*/", "", rules, flags=re.S)
        rules = re.sub(r"@media[^{]*", "", rules)

        self.assertNotIn("#", rules, "hex literal in the account section")

        stray = [px for px in re.findall(r"\b(\d+)px\b", rules) if px not in {"1", "2"}]
        self.assertEqual(stray, [], f"raw pixel values in the account section: {stray}")

    def test_template_carries_no_inline_styles(self):
        body = self._page()
        account_markup = body[body.index("app--account"):]
        self.assertNotIn("style=", account_markup)


if __name__ == "__main__":
    unittest.main()
