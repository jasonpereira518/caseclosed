import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.user import User
from services import clerk_auth


class ClerkAuthenticationTests(unittest.TestCase):
    def _state(self, payload, authenticated=True):
        return SimpleNamespace(
            is_authenticated=authenticated,
            payload=payload,
            reason=None,
        )

    @patch("services.clerk_auth.load_user")
    @patch("services.clerk_auth.verify_clerk_request")
    def test_migrated_user_uses_legacy_app_id(self, verify, load_user):
        verify.return_value = self._state({
            "sub": "user_clerk",
            "userId": "firebase-uid",
        })
        expected = User(id="firebase-uid", clerk_user_id="user_clerk")
        load_user.return_value = expected

        with patch.object(clerk_auth.config, "CLERK_SECRET_KEY", "sk_test"), \
                patch.object(clerk_auth.config, "CLERK_AUTHORIZED_PARTIES", ["http://localhost"]):
            result = clerk_auth.authenticate_clerk_request(MagicMock())

        self.assertIs(result, expected)
        load_user.assert_called_once_with("firebase-uid")
        options = verify.call_args.args[1]
        self.assertEqual(options.accepts_token, ["session_token"])
        self.assertEqual(options.authorized_parties, ["http://localhost"])

    @patch("services.clerk_auth.load_user")
    @patch("services.clerk_auth.sync_clerk_user")
    @patch("services.clerk_auth.get_clerk_client")
    @patch("services.clerk_auth.verify_clerk_request")
    def test_new_clerk_user_is_provisioned_synchronously(
        self, verify, get_client, sync_user, load_user
    ):
        verify.return_value = self._state({"sub": "user_new"})
        provisioned = User(id="user_new", clerk_user_id="user_new")
        load_user.side_effect = [None, provisioned]
        clerk_record = MagicMock()
        get_client.return_value.users.get.return_value = clerk_record

        with patch.object(clerk_auth.config, "CLERK_SECRET_KEY", "sk_test"):
            result = clerk_auth.authenticate_clerk_request(MagicMock())

        self.assertIs(result, provisioned)
        sync_user.assert_called_once_with(clerk_record, app_user_id="user_new")

    @patch("services.clerk_auth.load_user")
    @patch("services.clerk_auth.verify_clerk_request")
    def test_pending_session_is_not_authenticated(self, verify, load_user):
        verify.return_value = self._state({"sub": "user_new", "sts": "pending"})

        with patch.object(clerk_auth.config, "CLERK_SECRET_KEY", "sk_test"):
            result = clerk_auth.authenticate_clerk_request(MagicMock())

        self.assertIsNone(result)
        load_user.assert_not_called()

    @patch("services.clerk_auth.ensure_user")
    def test_clerk_profile_sync_preserves_external_id(self, ensure_user):
        ensure_user.return_value = {"uid": "firebase-uid"}
        payload = {
            "id": "user_clerk",
            "external_id": "firebase-uid",
            "primary_email_address_id": "email_1",
            "email_addresses": [{
                "id": "email_1",
                "email_address": "lawyer@example.com",
                "verification": {"status": "verified"},
            }],
            "first_name": "Jordan",
            "last_name": "Parker",
            "image_url": "https://example.com/avatar.png",
            "external_accounts": [{"provider": "google"}],
        }

        result = clerk_auth.sync_clerk_user(payload)

        self.assertEqual(result, {"uid": "firebase-uid"})
        claims = ensure_user.call_args.args[0]
        self.assertEqual(claims["uid"], "firebase-uid")
        self.assertEqual(claims["clerk_user_id"], "user_clerk")
        self.assertEqual(claims["legacy_firebase_uid"], "firebase-uid")
        self.assertTrue(claims["email_verified"])


class ClerkWebhookTests(unittest.TestCase):
    @patch("routes.webhooks.sync_clerk_user")
    @patch("routes.webhooks.get_firestore_client")
    @patch("routes.webhooks.Webhook")
    def test_verified_user_webhook_is_processed_once(self, webhook, get_db, sync_user):
        from app import app

        webhook.return_value.verify.return_value = {
            "type": "user.updated",
            "data": {"id": "user_clerk"},
        }
        event_ref = MagicMock()
        event_ref.get.return_value.exists = False
        get_db.return_value.collection.return_value.document.return_value = event_ref
        app.config.update(TESTING=True)

        with patch("routes.webhooks.config.CLERK_WEBHOOK_SIGNING_SECRET", "whsec_test"):
            response = app.test_client().post(
                "/webhooks/clerk",
                data=b"{}",
                headers={"svix-id": "msg_1", "svix-timestamp": "1", "svix-signature": "v1,test"},
            )

        self.assertEqual(response.status_code, 200)
        sync_user.assert_called_once_with({"id": "user_clerk"})
        event_ref.set.assert_called_once()


if __name__ == "__main__":
    unittest.main()
