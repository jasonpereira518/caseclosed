import unittest
from unittest.mock import patch

from app import app
from models.user import User


class LandingRouteTests(unittest.TestCase):
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

    def test_public_landing_renders_for_signed_out_visitor(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"From case file to first draft, faster.", response.data)
        self.assertIn(b'href="/auth/login"', response.data)
        self.assertNotIn(b"/static/script.js", response.data)

    @patch("models.user.load_user")
    def test_public_landing_renders_for_signed_in_visitor(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/app"', response.data)
        self.assertIn(b"Workspace", response.data)

    def test_workspace_requires_authentication(self):
        response = self.client.get("/app")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/auth/login"))

    def test_login_exposes_only_google_authentication(self):
        with patch("config.CLERK_PUBLISHABLE_KEY", "pk_test_example"), \
                patch("config.CLERK_SECRET_KEY", "sk_test_example"), \
                patch("config.CLERK_FRONTEND_API_URL", "https://clerk.example"):
            response = self.client.get("/auth/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="auth-root"', response.data)
        self.assertIn(b'id="auth-google"', response.data)
        self.assertIn(b"Continue with Google", response.data)
        self.assertIn(b'data-sso-callback="/auth/sso-callback', response.data)
        self.assertIn(b"Use your Google account to sign in or create your account.", response.data)
        self.assertNotIn(b'type="password"', response.data)
        self.assertNotIn(b"magic link", response.data)

    def test_invitation_login_has_invitation_context(self):
        with patch("config.CLERK_PUBLISHABLE_KEY", "pk_test_example"), \
                patch("config.CLERK_SECRET_KEY", "sk_test_example"), \
                patch("config.CLERK_FRONTEND_API_URL", "https://clerk.example"):
            response = self.client.get("/auth/login?invite=workspace-token")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Join your team workspace", response.data)
        self.assertIn(b"/auth/complete", response.data)
        self.assertIn(b"invite=workspace-token", response.data)

    def test_sso_callback_renders_and_round_trips_next_and_invite(self):
        response = self.client.get("/auth/sso-callback?next=%2Fapp&invite=workspace-token")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="auth-callback-root"', response.data)
        self.assertIn(b'data-next="/app"', response.data)
        self.assertIn(b'data-invite="workspace-token"', response.data)
        self.assertIn(b"invite=workspace-token", response.data)

    @patch("models.user.load_user")
    def test_sso_callback_redirects_already_authenticated_users_to_complete(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/auth/sso-callback?next=%2Fapp")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/complete", response.headers["Location"])

    def test_api_requires_authentication_as_json(self):
        response = self.client.get("/api/account")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "unauthorized"})

    @patch("models.user.load_user")
    def test_workspace_renders_for_signed_in_user(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Jordan Parker", response.data)
        # The workspace shell: history rail, conversation, and the four matter
        # panels. ("Legal Assistant" was the old chat-pane heading; the redesign
        # replaced it with the matter caption in the header.)
        for panel in (b"tab-record", b"tab-chronology", b"tab-authority", b"tab-draft"):
            self.assertIn(panel, response.data)
        self.assertNotIn(b"data-demo", response.data)

    @patch("models.user.load_user")
    def test_account_center_renders_for_signed_in_user(self, load_user):
        load_user.return_value = self.user
        self._sign_in()
        response = self.client.get("/account")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account center", response.data)
        self.assertIn(b"Create portable ZIP", response.data)

    def test_internal_job_worker_rejects_requests_without_secret(self):
        response = self.client.post("/internal/jobs/run", json={"job_id": "not-a-job"})
        self.assertEqual(response.status_code, 403)

    @patch("models.user.load_user")
    def test_logout_renders_the_clerk_sign_out_interstitial(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"logout", response.data.lower())


if __name__ == "__main__":
    unittest.main()
