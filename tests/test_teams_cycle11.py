"""Cycle 11: pending-invitation visibility, team rename, readable audit
trail."""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


class ListInvitationsServiceTests(unittest.TestCase):
    def _snap(self, doc_id, data):
        snap = MagicMock(id=doc_id)
        snap.to_dict.return_value = data
        return snap

    def test_returns_pending_only_without_token_hashes(self):
        from services import tenancy

        pending = self._snap("inv-1", {
            "workspace_id": "w1", "email": "a@example.com", "role": "member",
            "status": "pending", "token_hash": "sekrit",
            "created_at": "2026-08-18", "expires_at": "2026-08-25",
        })
        db = MagicMock()
        db.collection.return_value.where.return_value.stream.return_value = [pending]

        with patch.object(tenancy, "require_workspace") as gate, \
                patch.object(tenancy, "get_firestore_client", return_value=db):
            rows = tenancy.list_invitations("w1", "actor")

        gate.assert_called_once_with("w1", "actor", admin=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invitation_id"], "inv-1")
        self.assertEqual(rows[0]["email"], "a@example.com")
        self.assertNotIn("token_hash", rows[0])


class RenameWorkspaceServiceTests(unittest.TestCase):
    def _db(self, workspace):
        ref = MagicMock()
        snap = MagicMock()
        snap.to_dict.return_value = workspace
        ref.get.return_value = snap
        db = MagicMock()
        db.collection.return_value.document.return_value = ref
        return db, ref

    def test_team_rename_persists_and_audits(self):
        from services import tenancy

        db, ref = self._db({"type": "team", "name": "Old"})
        with patch.object(tenancy, "require_workspace") as gate, \
                patch.object(tenancy, "get_firestore_client", return_value=db), \
                patch.object(tenancy, "audit") as audit:
            result = tenancy.rename_workspace("w1", "actor", "  Litigation Group  ")

        gate.assert_called_once_with("w1", "actor", admin=True)
        payload = ref.set.call_args.args[0]
        self.assertEqual(payload["name"], "Litigation Group")
        self.assertEqual(result["name"], "Litigation Group")
        audit.assert_called_once()

    def test_personal_workspaces_refuse(self):
        from services import tenancy
        from services.tenancy import ValidationError

        db, _ = self._db({"type": "personal", "name": "Personal"})
        with patch.object(tenancy, "require_workspace"), \
                patch.object(tenancy, "get_firestore_client", return_value=db):
            with self.assertRaises(ValidationError):
                tenancy.rename_workspace("w1", "actor", "New name")

    def test_empty_name_refuses(self):
        from services import tenancy
        from services.tenancy import ValidationError

        with patch.object(tenancy, "require_workspace"):
            with self.assertRaises(ValidationError):
                tenancy.rename_workspace("w1", "actor", "   ")


class ListActivityServiceTests(unittest.TestCase):
    def test_returns_recent_events_newest_first(self):
        from services import tenancy

        snap = MagicMock(id="ev-1")
        snap.to_dict.return_value = {"event": "member.removed", "actor_uid": "u9",
                                     "matter_id": None, "metadata": {"target_uid": "u2"},
                                     "created_at": "2026-08-18"}
        db = MagicMock()
        (db.collection.return_value.document.return_value.collection
         .return_value.order_by.return_value.limit.return_value.stream.return_value) = [snap]

        with patch.object(tenancy, "require_workspace") as gate, \
                patch.object(tenancy, "get_firestore_client", return_value=db):
            events = tenancy.list_activity("w1", "actor")

        gate.assert_called_once_with("w1", "actor", admin=True)
        self.assertEqual(events[0]["event"], "member.removed")
        self.assertEqual(events[0]["metadata"], {"target_uid": "u2"})


class TeamRoutesTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_unauthenticated_calls_are_401_json(self):
        for method, path in (
            ("get", "/api/workspaces/w1/invitations"),
            ("patch", "/api/workspaces/w1"),
            ("get", "/api/workspaces/w1/activity"),
        ):
            with self.subTest(path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 401)

    @patch("routes.account.list_invitations")
    @patch("models.user.load_user")
    def test_invitations_route_returns_the_list(self, load_user, list_inv):
        load_user.return_value = _user()
        _sign_in(self.client)
        list_inv.return_value = [{"invitation_id": "inv-1", "email": "a@example.com"}]

        response = self.client.get("/api/workspaces/w1/invitations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["invitations"][0]["email"], "a@example.com")

    @patch("routes.account.list_invitations")
    @patch("models.user.load_user")
    def test_non_admin_gets_403(self, load_user, list_inv):
        from services.tenancy import AuthorizationError

        load_user.return_value = _user()
        _sign_in(self.client)
        list_inv.side_effect = AuthorizationError("no")

        response = self.client.get("/api/workspaces/w1/invitations")

        self.assertEqual(response.status_code, 403)

    @patch("routes.account.rename_workspace")
    @patch("models.user.load_user")
    def test_rename_route(self, load_user, rename):
        load_user.return_value = _user()
        _sign_in(self.client)
        rename.return_value = {"workspace_id": "w1", "name": "New Name"}

        response = self.client.patch("/api/workspaces/w1", json={"name": "New Name"})

        self.assertEqual(response.status_code, 200)
        rename.assert_called_once_with("w1", "test-user", "New Name")
        self.assertEqual(response.get_json()["workspace"]["name"], "New Name")

    @patch("routes.account.list_activity")
    @patch("models.user.load_user")
    def test_activity_route(self, load_user, activity):
        load_user.return_value = _user()
        _sign_in(self.client)
        activity.return_value = [{"event": "workspace.renamed", "actor_uid": "u1"}]

        response = self.client.get("/api/workspaces/w1/activity")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["events"][0]["event"], "workspace.renamed")


if __name__ == "__main__":
    unittest.main()
