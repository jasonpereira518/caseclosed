"""Cycle 2: Clerk-only identity, invite-approves-access, admin signup signal,
visible invite errors, and local enforcement of soft-deleted identities."""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


class FirebaseRetirementTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_firebase_session_route_is_gone(self):
        response = self.client.post("/auth/session", json={"id_token": "tok"})
        self.assertEqual(response.status_code, 404)

    def test_login_page_has_no_firebase_variant(self):
        with patch("config.CLERK_PUBLISHABLE_KEY", "pk_test_example"), \
                patch("config.CLERK_SECRET_KEY", "sk_test_example"), \
                patch("config.CLERK_FRONTEND_API_URL", "https://clerk.example"):
            response = self.client.get("/auth/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="auth-google"', response.data)
        self.assertNotIn(b"firebase-config", response.data)
        self.assertNotIn(b"firebase_auth.js", response.data)

    def test_config_no_longer_defines_the_provider_switch(self):
        import config
        self.assertFalse(hasattr(config, "AUTH_PROVIDER"))
        self.assertFalse(hasattr(config, "FIREBASE_WEB_CONFIG"))

    def test_logout_renders_clerk_interstitial(self):
        response = self.client.get("/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"logout", response.data.lower())


def _tenancy_db(*, invitation=None, user_doc=None):
    """A firestore mock that routes by collection name for tenancy calls."""
    import config

    db = MagicMock()
    invitation_snap = None
    if invitation is not None:
        invitation_snap = MagicMock(id="invite-1")
        invitation_snap.to_dict.return_value = invitation

    user_ref = MagicMock()
    user_snap = MagicMock(exists=user_doc is not None)
    user_snap.to_dict.return_value = user_doc or {}
    user_ref.get.return_value = user_snap

    workspace_ref = MagicMock()

    def collection(name):
        col = MagicMock()
        if name == config.FIRESTORE_INVITATIONS_COLLECTION:
            col.where.return_value.limit.return_value.stream.return_value = (
                [invitation_snap] if invitation_snap else []
            )
        elif name == config.FIRESTORE_USERS_COLLECTION:
            col.document.return_value = user_ref
        elif name == config.FIRESTORE_WORKSPACES_COLLECTION:
            col.document.return_value = workspace_ref
        return col

    db.collection.side_effect = collection
    return db, user_ref


class InviteApprovesAccessTests(unittest.TestCase):
    def _invitation(self):
        from services import tenancy
        return {
            "email": "new@example.com",
            "status": "pending",
            "expires_at": tenancy.now().replace(year=2999),
            "workspace_id": "team-1",
            "role": "member",
        }

    def _accept(self, user_doc):
        from services import tenancy

        db, user_ref = _tenancy_db(invitation=self._invitation(), user_doc=user_doc)
        with patch.object(tenancy, "get_firestore_client", return_value=db), \
                patch.object(tenancy, "audit"):
            tenancy.accept_invitation("u1", "new@example.com", "tok")
        (payload,), kwargs = user_ref.set.call_args
        self.assertTrue(kwargs.get("merge"))
        return payload

    def test_pending_account_is_approved_on_redemption(self):
        payload = self._accept({"access_status": "pending"})
        self.assertEqual(payload.get("access_status"), "approved")
        self.assertIn("access_updated_at", payload)

    def test_revoked_account_is_not_resurrected(self):
        payload = self._accept({"access_status": "revoked"})
        self.assertNotIn("access_status", payload)

    def test_grandfathered_account_is_untouched(self):
        payload = self._accept({})
        self.assertNotIn("access_status", payload)


class SignupNotificationTests(unittest.TestCase):
    def _ensure_user(self, *, exists):
        from services import tenancy

        snap = MagicMock(exists=exists)
        snap.to_dict.return_value = {"email": "new@example.com"} if exists else {}
        user_ref = MagicMock()
        user_ref.get.return_value = snap
        db = MagicMock()
        db.collection.return_value.document.return_value = user_ref

        with patch.object(tenancy, "get_firestore_client", return_value=db), \
                patch.object(tenancy, "ensure_personal_workspace"), \
                patch.object(tenancy, "_notify_admins_of_access_request") as notify:
            tenancy.ensure_user({"uid": "new-user", "email": "new@example.com"})
        return notify

    def test_new_account_notifies_admins(self):
        notify = self._ensure_user(exists=False)
        notify.assert_called_once_with("new@example.com")

    def test_existing_account_does_not_notify(self):
        notify = self._ensure_user(exists=True)
        notify.assert_not_called()

    @patch("services.mailer.smtplib.SMTP")
    def test_access_request_mail_links_the_admin_page(self, smtp):
        from services.mailer import send_access_request_notification

        client = smtp.return_value.__enter__.return_value
        with patch("services.mailer.config.SMTP_HOST", "smtp.example"), \
                patch("services.mailer.config.SMTP_FROM", "noreply@example.com"):
            sent = send_access_request_notification("admin@example.com", "new@example.com")

        self.assertTrue(sent)
        message = client.send_message.call_args[0][0]
        self.assertEqual(message["To"], "admin@example.com")
        self.assertIn("new@example.com", message.get_content())
        self.assertIn("/admin/access", message.get_content())


class InviteErrorPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("services.tenancy.accept_invitation")
    @patch("models.user.load_user")
    def test_failed_invite_shows_an_error_page(self, load_user, accept):
        from services.tenancy import ValidationError

        load_user.return_value = User(
            id="u1", email="lawyer@example.com", name="Jordan", profile_pic=None
        )
        with self.client.session_transaction() as session:
            session["_user_id"] = "u1"
            session["_fresh"] = True
        accept.side_effect = ValidationError("invitation has expired or was already used")

        response = self.client.get("/auth/complete?invite=stale-token")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"invitation", response.data.lower())
        self.assertIn(b"expired", response.data.lower())
        self.assertIn(b"/app", response.data)


class DeletedIdentityTests(unittest.TestCase):
    def _load(self, doc):
        from models import user as user_model

        snap = MagicMock(exists=True)
        snap.to_dict.return_value = doc
        db = MagicMock()
        db.collection.return_value.document.return_value.get.return_value = snap
        with patch.object(user_model, "get_firestore_client", return_value=db):
            return user_model.load_user("u1")

    def test_deleted_identity_loads_as_none(self):
        self.assertIsNone(self._load({"email": "x@example.com", "auth_status": "deleted"}))

    def test_active_identity_still_loads(self):
        user = self._load({"email": "x@example.com", "auth_status": "active"})
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "x@example.com")


if __name__ == "__main__":
    unittest.main()
