"""Cycle 12: time-inclusive exports, latest-only export retention, avatar
removal."""
import io
import json
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


class ExportTimeTests(unittest.TestCase):
    def test_export_zip_contains_time_json(self):
        from services import account_export

        captured = {}

        def capture_upload(file_object, storage_path, content_type):
            file_object.seek(0)
            captured["bytes"] = file_object.read()
            captured["path"] = storage_path
            return storage_path

        user_snap = MagicMock()
        user_snap.to_dict.return_value = {}
        db = MagicMock()
        db.collection.return_value.document.return_value.get.return_value = user_snap

        with patch.object(account_export, "get_profile", return_value={"uid": "u1"}), \
                patch.object(account_export, "list_workspaces",
                             return_value=[{"workspace_id": "w1"}]), \
                patch.object(account_export, "get_firestore_client", return_value=db), \
                patch.object(account_export, "list_matters",
                             return_value=[{"matter_id": "m1"}]), \
                patch.object(account_export, "load_matter",
                             return_value={"title": "Rivera", "total_seconds": 3600,
                                           "uploaded_documents": []}), \
                patch.object(account_export, "list_time_entries",
                             return_value=[{"seconds": 3600,
                                            "created_at": "2026-08-01T00:00:00Z"}]), \
                patch.object(account_export, "upload_file_object",
                             side_effect=capture_upload), \
                patch.object(account_export, "delete_prefix_except") as cleanup:
            result = account_export.run_account_export("u1", "job-1", {})

        bundle = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        time_payload = json.loads(bundle.read("workspaces/w1/matters/m1/time.json"))
        self.assertEqual(time_payload["total_seconds"], 3600)
        self.assertEqual(time_payload["entries"][0]["seconds"], 3600)
        # Older exports are cleaned up, keeping the object just uploaded.
        cleanup.assert_called_once_with("users/u1/exports/", result["storage_path"])


class DeletePrefixExceptTests(unittest.TestCase):
    def test_only_other_objects_are_deleted(self):
        from services import storage

        keep = MagicMock(name="keep")
        keep.name = "users/u1/exports/job-2.zip"
        old = MagicMock(name="old")
        old.name = "users/u1/exports/job-1.zip"
        bucket = MagicMock()
        bucket.list_blobs.return_value = [old, keep]

        with patch.object(storage, "_bucket", return_value=bucket):
            storage.delete_prefix_except("users/u1/exports/", "users/u1/exports/job-2.zip")

        old.delete.assert_called_once()
        keep.delete.assert_not_called()


class AvatarRemovalTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_unauthenticated_is_401_json(self):
        response = self.client.delete("/api/account/avatar")
        self.assertEqual(response.status_code, 401)

    @patch("routes.account.get_profile", return_value={"uid": "test-user"})
    @patch("routes.account.delete_path")
    @patch("routes.account.get_firestore_client")
    @patch("models.user.load_user")
    def test_removal_deletes_object_and_clears_field(
        self, load_user, get_db, delete_path, get_profile
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        user_snap = MagicMock()
        user_snap.to_dict.return_value = {"avatar_storage_path": "users/test-user/avatar/a.png"}
        ref = MagicMock()
        ref.get.return_value = user_snap
        get_db.return_value.collection.return_value.document.return_value = ref

        response = self.client.delete("/api/account/avatar")

        self.assertEqual(response.status_code, 200)
        delete_path.assert_called_once_with("users/test-user/avatar/a.png")
        payload = ref.set.call_args.args[0]
        self.assertIn("avatar_storage_path", payload)

    @patch("routes.account.get_profile", return_value={"uid": "test-user"})
    @patch("routes.account.delete_path")
    @patch("routes.account.get_firestore_client")
    @patch("models.user.load_user")
    def test_no_avatar_is_a_clean_no_op(self, load_user, get_db, delete_path, get_profile):
        load_user.return_value = _user()
        _sign_in(self.client)
        user_snap = MagicMock()
        user_snap.to_dict.return_value = {}
        get_db.return_value.collection.return_value.document.return_value.get.return_value = user_snap

        response = self.client.delete("/api/account/avatar")

        self.assertEqual(response.status_code, 200)
        delete_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
