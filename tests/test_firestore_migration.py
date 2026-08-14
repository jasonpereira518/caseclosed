import unittest
from unittest.mock import MagicMock, patch

from scripts import migrate_firestore_v2


class FirestoreMigrationTests(unittest.TestCase):
    @patch("scripts.migrate_firestore_v2.locate_matter", return_value=("workspace-1", {"title": "Existing"}))
    @patch("scripts.migrate_firestore_v2.get_firestore_client")
    def test_existing_matter_is_skipped_without_firebase_identity(self, get_client, _locate):
        user_collection = MagicMock()
        user_collection.stream.return_value = []

        legacy = MagicMock()
        legacy.id = "matter-1"
        legacy.to_dict.return_value = {"user_id": "removed-firebase-user"}
        context_collection = MagicMock()
        context_collection.stream.return_value = [legacy]

        db = MagicMock()
        db.collection.side_effect = lambda name: (
            user_collection
            if name == migrate_firestore_v2.config.FIRESTORE_USERS_COLLECTION
            else context_collection
        )
        get_client.return_value = db

        report = migrate_firestore_v2.migrate(apply=False)

        self.assertEqual(report["migrated"], [])
        self.assertEqual(report["quarantined"], [])
        self.assertEqual(
            report["skipped"],
            [{"context_id": "matter-1", "reason": "already migrated"}],
        )


if __name__ == "__main__":
    unittest.main()
