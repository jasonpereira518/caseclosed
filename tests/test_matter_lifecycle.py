"""Cycle 3: matter archiving, honest error codes, lightweight authorization,
and the retirement of the lazy legacy-context migration."""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "u1"
        session["_fresh"] = True


def _user():
    return User(id="u1", email="lawyer@example.com", name="Jordan", profile_pic=None)


class ArchiveRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_unauthenticated_archive_gets_401_json(self):
        response = self.client.post("/contexts/archive", json={"context_id": "m1"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "unauthorized"})

    @patch("routes.context.archive_context")
    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_archiving_an_inactive_matter_acknowledges(self, load_user, belongs, archive):
        load_user.return_value = _user()
        _sign_in(self.client)
        with self.client.session_transaction() as session:
            session["context_id"] = "other-matter"
        belongs.return_value = True
        archive.return_value = True

        response = self.client.post("/contexts/archive", json={"context_id": "m1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")
        archive.assert_called_once_with("m1", "u1", True)

    @patch("routes.context.archive_context")
    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_unarchive_reopens(self, load_user, belongs, archive):
        load_user.return_value = _user()
        _sign_in(self.client)
        belongs.return_value = True
        archive.return_value = True

        response = self.client.post("/contexts/unarchive", json={"context_id": "m1"})

        self.assertEqual(response.status_code, 200)
        archive.assert_called_once_with("m1", "u1", False)

    @patch("routes.context.set_active_matter")
    @patch("routes.context.get_stored_context")
    @patch("routes.context.list_user_contexts")
    @patch("routes.context.archive_context")
    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_archiving_the_active_matter_switches_to_the_next(
        self, load_user, belongs, archive, list_contexts, get_stored, set_active
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        with self.client.session_transaction() as session:
            session["context_id"] = "m1"
            session["workspace_id"] = "w1"
        belongs.return_value = True
        archive.return_value = True
        list_contexts.return_value = [
            {"context_id": "m2", "updated_at": "2026-08-01T00:00:00Z"},
        ]
        get_stored.return_value = {"workspace_id": "w1", "title": "Next matter"}

        response = self.client.post("/contexts/archive", json={"context_id": "m1"})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["switched_to"], "m2")
        self.assertEqual(body["context"]["title"], "Next matter")

    @patch("routes.context.set_active_matter")
    @patch("routes.context.get_context_or_default")
    @patch("routes.context.create_new_context")
    @patch("routes.context.list_user_contexts")
    @patch("routes.context.archive_context")
    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_archiving_the_last_matter_auto_creates(
        self, load_user, belongs, archive, list_contexts, create, get_default, set_active
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        with self.client.session_transaction() as session:
            session["context_id"] = "m1"
            session["workspace_id"] = "w1"
        belongs.return_value = True
        archive.return_value = True
        list_contexts.return_value = []
        create.return_value = ("fresh-id", {"title": "New Session"})
        get_default.return_value = {"title": "New Session"}

        response = self.client.post("/contexts/archive", json={"context_id": "m1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["switched_to"], "fresh-id")

    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_inaccessible_matter_archives_as_404(self, load_user, belongs):
        load_user.return_value = _user()
        _sign_in(self.client)
        belongs.return_value = False

        response = self.client.post("/contexts/archive", json={"context_id": "mx"})

        self.assertEqual(response.status_code, 404)


class ContextsListTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _listing(self):
        return [
            {"context_id": "m1", "status": "active", "updated_at": "2026-08-02T00:00:00Z"},
            {"context_id": "m2", "status": "archived", "updated_at": "2026-08-03T00:00:00Z"},
        ]

    @patch("routes.context.list_user_contexts")
    @patch("models.user.load_user")
    def test_archived_matters_are_hidden_by_default(self, load_user, list_contexts):
        load_user.return_value = _user()
        _sign_in(self.client)
        with self.client.session_transaction() as session:
            session["workspace_id"] = "w1"
            session["context_id"] = "m1"
        list_contexts.return_value = self._listing()

        response = self.client.get("/contexts")

        body = response.get_json()
        self.assertEqual([m["context_id"] for m in body["contexts"]], ["m1"])
        self.assertEqual(body["archived_count"], 1)
        self.assertNotIn("archived", body)

    @patch("routes.context.list_user_contexts")
    @patch("models.user.load_user")
    def test_include_archived_returns_them(self, load_user, list_contexts):
        load_user.return_value = _user()
        _sign_in(self.client)
        with self.client.session_transaction() as session:
            session["workspace_id"] = "w1"
            session["context_id"] = "m1"
        list_contexts.return_value = self._listing()

        response = self.client.get("/contexts?include_archived=1")

        body = response.get_json()
        self.assertEqual([m["context_id"] for m in body["archived"]], ["m2"])


class ErrorCodeTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_switch_rename_delete_return_404_for_inaccessible_matters(
        self, load_user, belongs
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        belongs.return_value = False

        for path, payload in (
            ("/contexts/switch", {"context_id": "mx"}),
            ("/contexts/rename", {"context_id": "mx", "title": "T"}),
            ("/contexts/delete", {"context_id": "mx"}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 404)


class LightweightAuthorizationTests(unittest.TestCase):
    def test_ownership_check_never_loads_subcollections(self):
        from models import context as ctx

        with patch.object(ctx, "require_matter", return_value=("w1", MagicMock(), {})), \
                patch.object(ctx, "load_matter",
                             side_effect=AssertionError("full load is too expensive here")):
            self.assertTrue(ctx.context_belongs_to_user("m1", "u1"))

    def test_ownership_check_is_false_when_access_denied(self):
        from models import context as ctx
        from services.tenancy import AuthorizationError

        with patch.object(ctx, "require_matter", side_effect=AuthorizationError("no")):
            self.assertFalse(ctx.context_belongs_to_user("m1", "u1"))

    def test_rename_patches_only_the_title(self):
        from models import context as ctx

        with patch.object(ctx, "patch_matter") as patch_fn, \
                patch.object(ctx, "load_matter",
                             side_effect=AssertionError("full load is too expensive here")):
            self.assertTrue(ctx.rename_context("m1", "u1", "  Rivera appeal  "))

        patch_fn.assert_called_once_with("m1", "u1", root={"title": "Rivera appeal"})

    def test_archive_patches_status(self):
        from models import context as ctx

        with patch.object(ctx, "patch_matter") as patch_fn:
            self.assertTrue(ctx.archive_context("m1", "u1", True))
        patch_fn.assert_called_once_with("m1", "u1", root={"status": "archived"})

        with patch.object(ctx, "patch_matter") as patch_fn:
            self.assertTrue(ctx.archive_context("m1", "u1", False))
        patch_fn.assert_called_once_with("m1", "u1", root={"status": "active"})


class ListFilteringTests(unittest.TestCase):
    def test_archived_matters_are_filtered_unless_requested(self):
        from models import context as ctx

        rows = [
            {"matter_id": "m1", "status": "active"},
            {"matter_id": "m2", "status": "archived"},
            {"matter_id": "m3"},  # pre-status matter reads as active
        ]
        with patch.object(ctx, "list_matters", return_value=rows), \
                patch.object(ctx, "active_workspace", return_value="w1"):
            active_only = ctx.list_user_contexts("u1", "w1")
            everything = ctx.list_user_contexts("u1", "w1", include_archived=True)

        self.assertEqual([m["matter_id"] for m in active_only], ["m1", "m3"])
        self.assertEqual([m["matter_id"] for m in everything], ["m1", "m2", "m3"])


class LegacyMigrationRetirementTests(unittest.TestCase):
    def test_lazy_migration_code_is_gone(self):
        from models import context as ctx

        self.assertFalse(hasattr(ctx, "_migrate_legacy_context"))
        self.assertFalse(hasattr(ctx, "_migrate_legacy_for_user"))

    def test_module_no_longer_reads_the_legacy_collection(self):
        import inspect
        from models import context as ctx

        source = inspect.getsource(ctx)
        self.assertNotIn("FIRESTORE_COLLECTION", source)
        self.assertNotIn("load_legacy_context", source)


if __name__ == "__main__":
    unittest.main()
