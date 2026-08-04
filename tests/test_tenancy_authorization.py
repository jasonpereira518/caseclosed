import unittest
from unittest.mock import MagicMock, patch

from services.matters import require_matter
from services.tenancy import AuthorizationError
from models.context import get_or_create_context
from services.tenancy import ValidationError, update_profile


class MatterAuthorizationTests(unittest.TestCase):
    def _refs(self, *, workspace_type="team", assigned=None):
        matter_ref = MagicMock()
        matter_snap = MagicMock(exists=True)
        matter_snap.to_dict.return_value = {"assigned_user_ids": assigned or []}
        matter_ref.get.return_value = matter_snap
        workspace_ref = MagicMock()
        workspace_snap = MagicMock()
        workspace_snap.to_dict.return_value = {"type": workspace_type, "owner_id": "owner"}
        workspace_ref.get.return_value = workspace_snap
        return matter_ref, workspace_ref

    @patch("services.matters._workspace_ref")
    @patch("services.matters.membership")
    @patch("services.matters.locate_matter")
    def test_unassigned_member_cannot_open_team_matter(self, locate, member, workspace_ref):
        matter_ref, workspace = self._refs(assigned=["someone-else"])
        locate.return_value = ("team-1", matter_ref)
        member.return_value = {"role": "member", "status": "active"}
        workspace_ref.return_value = workspace
        with self.assertRaises(AuthorizationError):
            require_matter("matter-1", "member-1")

    @patch("services.matters._workspace_ref")
    @patch("services.matters.membership")
    @patch("services.matters.locate_matter")
    def test_assigned_member_can_open_team_matter(self, locate, member, workspace_ref):
        matter_ref, workspace = self._refs(assigned=["member-1"])
        locate.return_value = ("team-1", matter_ref)
        member.return_value = {"role": "member", "status": "active"}
        workspace_ref.return_value = workspace
        wid, _, _ = require_matter("matter-1", "member-1")
        self.assertEqual(wid, "team-1")

    @patch("models.context.create_new_context")
    @patch("models.context.locate_matter")
    @patch("models.context.load_matter")
    def test_indexed_inaccessible_matter_is_never_adopted(self, load, locate, create):
        load.return_value = None
        locate.return_value = ("another-users-workspace", MagicMock())
        self.assertIsNone(get_or_create_context("guessed-id", "attacker"))
        create.assert_not_called()

    def test_profile_array_fields_reject_scalar_values(self):
        with self.assertRaises(ValidationError):
            update_profile("user-1", {"jurisdictions": "New York"})

    @patch("services.matters._workspace_ref")
    @patch("services.matters.membership")
    @patch("services.matters.locate_matter")
    def test_admin_can_open_unassigned_team_matter(self, locate, member, workspace_ref):
        matter_ref, workspace = self._refs(assigned=[])
        locate.return_value = ("team-1", matter_ref)
        member.return_value = {"role": "admin", "status": "active"}
        workspace_ref.return_value = workspace
        wid, _, _ = require_matter("matter-1", "admin-1")
        self.assertEqual(wid, "team-1")


if __name__ == "__main__":
    unittest.main()
