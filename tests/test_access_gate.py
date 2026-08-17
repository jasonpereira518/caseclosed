"""Access gate: sign-in is the request, approval opens the product.

New accounts are created with access_status="pending" and can reach only the
public surface plus /waitlist until an admin approves them. A user document
with no access_status field predates the gate and is treated as approved, so
existing accounts keep working with zero migration.
"""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _user(status=None):
    profile = {} if status is None else {"access_status": status}
    return User(
        id="gate-user",
        email="gated@example.com",
        name="Gated User",
        profile_pic=None,
        **profile,
    )


class AccessGateTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _sign_in(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = "gate-user"
            session["_fresh"] = True

    @patch("models.user.load_user")
    def test_pending_user_is_redirected_to_waitlist_for_pages(self, load_user):
        load_user.return_value = _user("pending")
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/waitlist"))

    @patch("models.user.load_user")
    def test_pending_user_gets_403_json_on_api_paths(self, load_user):
        load_user.return_value = _user("pending")
        self._sign_in()

        response = self.client.get("/api/account")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "access_pending"})

    @patch("models.user.load_user")
    def test_revoked_user_is_gated_like_pending(self, load_user):
        load_user.return_value = _user("revoked")
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/waitlist"))

    @patch("models.user.load_user")
    def test_approved_user_passes_the_gate(self, load_user):
        load_user.return_value = _user("approved")
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)

    @patch("models.user.load_user")
    def test_user_without_access_status_is_grandfathered(self, load_user):
        load_user.return_value = _user(None)
        self._sign_in()

        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)

    @patch("models.user.load_user")
    def test_pending_user_still_reaches_public_pages_and_sign_out(self, load_user):
        load_user.return_value = _user("pending")
        self._sign_in()

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/demo").status_code, 200)
        with patch("routes.auth.config.AUTH_PROVIDER", "firebase"):
            self.assertEqual(self.client.get("/auth/logout").status_code, 302)


class WaitlistPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _sign_in(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = "gate-user"
            session["_fresh"] = True

    @patch("models.user.load_user")
    def test_pending_user_sees_waitlist_page_with_their_email(self, load_user):
        load_user.return_value = _user("pending")
        self._sign_in()

        response = self.client.get("/waitlist")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"gated@example.com", response.data)
        self.assertIn(b"on the list", response.data)

    @patch("models.user.load_user")
    def test_approved_user_is_redirected_from_waitlist_to_workspace(self, load_user):
        load_user.return_value = _user("approved")
        self._sign_in()

        response = self.client.get("/waitlist")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/app"))

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/waitlist")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["Location"])


class AdminAccessTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _sign_in_as(self, email):
        self._current = User(
            id="admin-user", email=email, name="Admin", profile_pic=None
        )
        with self.client.session_transaction() as session:
            session["_user_id"] = "admin-user"
            session["_fresh"] = True

    def test_anonymous_visitor_gets_404(self):
        self.assertEqual(self.client.get("/admin/access").status_code, 404)

    @patch("models.user.load_user")
    def test_non_admin_gets_404(self, load_user):
        self._sign_in_as("lawyer@example.com")
        load_user.return_value = self._current

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.get("/admin/access")

        self.assertEqual(response.status_code, 404)

    @patch("routes.admin.list_access_requests")
    @patch("models.user.load_user")
    def test_admin_sees_pending_users(self, load_user, list_requests):
        self._sign_in_as("admin@example.com")
        load_user.return_value = self._current
        list_requests.return_value = [
            {"uid": "u1", "email": "new@example.com", "display_name": "New Lawyer",
             "access_status": "pending", "created_at": "2026-08-16T00:00:00Z"},
        ]

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.get("/admin/access")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"new@example.com", response.data)

    @patch("routes.admin.send_access_approved")
    @patch("routes.admin.set_access_status")
    @patch("models.user.load_user")
    def test_admin_approval_sets_status_and_sends_mail(
        self, load_user, set_status, send_mail
    ):
        self._sign_in_as("admin@example.com")
        load_user.return_value = self._current
        set_status.return_value = {"uid": "u1", "email": "new@example.com",
                                   "access_status": "approved"}
        send_mail.return_value = True

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.post(
                "/api/admin/access/u1", json={"action": "approve"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["access_status"], "approved")
        self.assertTrue(response.get_json()["mail_sent"])
        set_status.assert_called_once_with("u1", "approved")
        send_mail.assert_called_once_with("new@example.com")

    @patch("routes.admin.send_access_approved")
    @patch("routes.admin.set_access_status")
    @patch("models.user.load_user")
    def test_mail_failure_does_not_roll_back_approval(
        self, load_user, set_status, send_mail
    ):
        self._sign_in_as("admin@example.com")
        load_user.return_value = self._current
        set_status.return_value = {"uid": "u1", "email": "new@example.com",
                                   "access_status": "approved"}
        send_mail.side_effect = RuntimeError("smtp down")

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.post(
                "/api/admin/access/u1", json={"action": "approve"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["access_status"], "approved")
        self.assertFalse(response.get_json()["mail_sent"])

    @patch("routes.admin.send_access_approved")
    @patch("routes.admin.set_access_status")
    @patch("models.user.load_user")
    def test_revoke_sets_status_without_mail(self, load_user, set_status, send_mail):
        self._sign_in_as("admin@example.com")
        load_user.return_value = self._current
        set_status.return_value = {"uid": "u1", "email": "new@example.com",
                                   "access_status": "revoked"}

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.post(
                "/api/admin/access/u1", json={"action": "revoke"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["access_status"], "revoked")
        send_mail.assert_not_called()

    @patch("models.user.load_user")
    def test_unknown_action_is_rejected(self, load_user):
        self._sign_in_as("admin@example.com")
        load_user.return_value = self._current

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.post(
                "/api/admin/access/u1", json={"action": "bless"}
            )

        self.assertEqual(response.status_code, 400)

    @patch("models.user.load_user")
    def test_non_admin_cannot_post(self, load_user):
        self._sign_in_as("lawyer@example.com")
        load_user.return_value = self._current

        with patch("config.ADMIN_EMAILS", {"admin@example.com"}):
            response = self.client.post(
                "/api/admin/access/u1", json={"action": "approve"}
            )

        self.assertEqual(response.status_code, 404)


class EnsureUserAccessStatusTests(unittest.TestCase):
    """New accounts start pending; existing documents are never stamped."""

    def _run_ensure_user(self, *, exists):
        from services import tenancy

        snap = MagicMock(exists=exists)
        snap.to_dict.return_value = {"email": "new@example.com"} if exists else {}
        user_ref = MagicMock()
        user_ref.get.return_value = snap
        db = MagicMock()
        db.collection.return_value.document.return_value = user_ref

        with patch.object(tenancy, "get_firestore_client", return_value=db), \
                patch.object(tenancy, "ensure_personal_workspace"):
            tenancy.ensure_user({"uid": "new-user", "email": "new@example.com"})

        (payload,), kwargs = user_ref.set.call_args
        self.assertTrue(kwargs.get("merge"))
        return payload

    def test_new_user_document_starts_pending(self):
        payload = self._run_ensure_user(exists=False)
        self.assertEqual(payload.get("access_status"), "pending")

    def test_existing_user_document_is_not_stamped(self):
        payload = self._run_ensure_user(exists=True)
        self.assertNotIn("access_status", payload)


class ApprovalMailTests(unittest.TestCase):
    @patch("services.mailer.smtplib.SMTP")
    def test_approval_mail_addresses_the_recipient(self, smtp):
        from services.mailer import send_access_approved

        client = smtp.return_value.__enter__.return_value
        with patch("services.mailer.config.SMTP_HOST", "smtp.example"), \
                patch("services.mailer.config.SMTP_FROM", "noreply@example.com"):
            sent = send_access_approved("new@example.com")

        self.assertTrue(sent)
        message = client.send_message.call_args[0][0]
        self.assertEqual(message["To"], "new@example.com")
        self.assertIn("Case Closed", message["Subject"])


if __name__ == "__main__":
    unittest.main()
