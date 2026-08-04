import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    @patch("models.user.load_user")
    def test_workspace_renders_for_signed_in_user(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Legal Assistant", response.data)
        self.assertIn(b"Jordan Parker", response.data)

    @patch("routes.auth.load_user")
    @patch("routes.auth.save_user")
    @patch("routes.auth.requests.get")
    @patch("routes.auth._build_flow")
    def test_oauth_callback_redirects_to_workspace(
        self,
        build_flow,
        requests_get,
        save_user,
        load_user,
    ):
        flow = MagicMock()
        flow.credentials = SimpleNamespace(token="test-token")
        build_flow.return_value = flow

        profile_response = MagicMock()
        profile_response.json.return_value = {
            "id": self.user.id,
            "email": self.user.email,
            "name": self.user.name,
        }
        requests_get.return_value = profile_response
        load_user.return_value = self.user

        with self.client.session_transaction() as session:
            session["oauth_state"] = "expected-state"

        response = self.client.get(
            "/auth/callback?state=expected-state&code=test-code"
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/app"))
        flow.fetch_token.assert_called_once()
        profile_response.raise_for_status.assert_called_once()
        save_user.assert_called_once()

    @patch("models.user.load_user")
    def test_logout_returns_to_public_landing(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/auth/logout")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))


if __name__ == "__main__":
    unittest.main()
