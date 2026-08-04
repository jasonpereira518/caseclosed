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

    @patch("routes.auth.ensure_user")
    @patch("routes.auth.get_firestore_client")
    @patch("routes.auth.firebase_auth.create_session_cookie")
    @patch("routes.auth.firebase_auth.verify_id_token")
    def test_firebase_token_creates_secure_server_session(
        self, verify_id_token, create_session_cookie, get_firestore_client, ensure_user
    ):
        verify_id_token.return_value = {
            "uid": self.user.id, "email": self.user.email, "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        ensure_user.return_value = {"uid": self.user.id, "email": self.user.email}
        create_session_cookie.return_value = "signed-cookie"

        response = self.client.post(
            "/auth/session", json={"id_token": "firebase-id-token"},
            headers={"Origin": "http://localhost"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("__session=signed-cookie", response.headers["Set-Cookie"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        verify_id_token.assert_called_once_with("firebase-id-token", check_revoked=True)
        ensure_user.assert_called_once()

    @patch("routes.auth.get_firestore_client")
    @patch("routes.auth.firebase_auth.verify_id_token")
    def test_unverified_password_identity_is_rejected(self, verify_id_token, get_firestore_client):
        verify_id_token.return_value = {
            "uid": self.user.id, "email": self.user.email, "email_verified": False,
            "firebase": {"sign_in_provider": "password"},
        }
        response = self.client.post("/auth/session", json={"id_token": "token"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("verify", response.get_json()["error"])

    @patch("models.user.load_user")
    def test_logout_returns_to_public_landing(self, load_user):
        load_user.return_value = self.user
        self._sign_in()

        response = self.client.get("/auth/logout")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))


if __name__ == "__main__":
    unittest.main()
