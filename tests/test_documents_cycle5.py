"""Cycle 5: retrieval-only include (description splice retired), auto-include
on ready, and per-document retry with a durability check."""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User
from services.jobs import deterministic_job_id


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


LEGACY_BLOCK = "\n\n[Document: brief.pdf]\nExtracted body text."


class ToggleWithoutSpliceTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.context = {
            "description": "Client narrative." + LEGACY_BLOCK,
            "uploaded_documents": [
                {"record_id": "doc-1", "filename": "brief.pdf",
                 "text": "Extracted body text.", "included": True},
            ],
        }

    def _toggle(self, included):
        with patch("routes.upload.get_context", return_value=self.context), \
                patch("routes.upload.patch_document") as patch_doc, \
                patch("routes.upload.patch_matter") as patch_matter, \
                patch("routes.upload.set_matter_document_included") as set_included:
            response = self.client.post("/documents/toggle", json={
                "context_id": "matter-1", "doc_index": 0, "included": included,
            })
        return response, patch_doc, patch_matter, set_included

    @patch("models.user.load_user")
    def test_including_no_longer_splices_text_into_the_description(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        self.context["description"] = "Client narrative."

        response, patch_doc, patch_matter, set_included = self._toggle(True)

        self.assertEqual(response.status_code, 200)
        patch_doc.assert_called_once_with("matter-1", "test-user", "doc-1", {"included": True})
        set_included.assert_called_once_with("matter-1", "test-user", "doc-1", True)
        patch_matter.assert_not_called()  # description untouched

    @patch("models.user.load_user")
    def test_toggling_heals_a_legacy_spliced_block(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response, _, patch_matter, _ = self._toggle(True)

        self.assertEqual(response.status_code, 200)
        patch_matter.assert_called_once_with(
            "matter-1", "test-user", root={"description": "Client narrative."})

    @patch("models.user.load_user")
    def test_excluding_also_heals(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response, patch_doc, patch_matter, set_included = self._toggle(False)

        self.assertEqual(response.status_code, 200)
        patch_doc.assert_called_once_with("matter-1", "test-user", "doc-1", {"included": False})
        set_included.assert_called_once_with("matter-1", "test-user", "doc-1", False)
        patch_matter.assert_called_once_with(
            "matter-1", "test-user", root={"description": "Client narrative."})


class DeleteCleanupTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("routes.upload.delete_path")
    @patch("routes.upload.delete_document_record")
    @patch("routes.upload.delete_matter_document_index")
    @patch("routes.upload.patch_matter")
    @patch("routes.upload.get_context")
    @patch("models.user.load_user")
    def test_delete_heals_even_when_document_was_excluded(
        self, load_user, get_context, patch_matter, *_mocks
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        get_context.return_value = {
            "description": "Narrative." + LEGACY_BLOCK,
            "uploaded_documents": [
                {"record_id": "doc-1", "filename": "brief.pdf",
                 "text": "Extracted body text.", "included": False,
                 "storage_path": "workspaces/w/matters/m/documents/doc-1/brief.pdf"},
            ],
        }

        response = self.client.post("/documents/delete",
                                    json={"context_id": "matter-1", "doc_index": 0})

        self.assertEqual(response.status_code, 200)
        patch_matter.assert_called_once_with(
            "matter-1", "test-user", root={"description": "Narrative."})


class AutoIncludeOnReadyTests(unittest.TestCase):
    def test_successful_ingestion_includes_the_document(self):
        import tempfile

        from services import document_ingestion as ingestion

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("Body of the document under test.")
            path = handle.name

        with patch.object(ingestion, "upsert_document") as upsert, \
                patch.object(ingestion, "index_matter_document", return_value=3) as index, \
                patch.object(ingestion, "cancellation_requested", return_value=False):
            result = ingestion.ingest_document_job("m1", "j1", {
                "requested_by": "u1",
                "payload": {"document_id": "doc-1", "filename": "notes.txt",
                            "local_path": path},
            })

        metadata = upsert.call_args[0][3]
        self.assertTrue(metadata["included"])
        self.assertEqual(metadata["status"], "ready")
        self.assertTrue(index.call_args.kwargs.get("included"))
        self.assertTrue(result["document"]["included"])


class DocumentRetryTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.job_id = deterministic_job_id("matter-1", "document_ingest", "doc-1")

    def _matter_ref(self, record):
        snap = MagicMock(exists=record is not None)
        snap.to_dict.return_value = record or {}
        matter_ref = MagicMock()
        matter_ref.collection.return_value.document.return_value.get.return_value = snap
        return matter_ref

    def test_unauthenticated_is_401_json(self):
        response = self.client.post("/api/matters/matter-1/documents/doc-1/retry")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "unauthorized"})

    @patch("routes.upload.require_matter")
    @patch("models.user.load_user")
    def test_unauthorized_is_403(self, load_user, require):
        from services.tenancy import AuthorizationError

        load_user.return_value = _user()
        _sign_in(self.client)
        require.side_effect = AuthorizationError("no")

        response = self.client.post("/api/matters/matter-1/documents/doc-1/retry")

        self.assertEqual(response.status_code, 403)

    @patch("routes.upload.require_matter")
    @patch("models.user.load_user")
    def test_non_durable_original_is_409(self, load_user, require):
        load_user.return_value = _user()
        _sign_in(self.client)
        require.return_value = ("w1", self._matter_ref({"filename": "brief.pdf",
                                                        "storage_path": None}), {})

        response = self.client.post("/api/matters/matter-1/documents/doc-1/retry")

        self.assertEqual(response.status_code, 409)
        self.assertIn("upload it again", response.get_json()["error"])

    @patch("routes.upload.get_job")
    @patch("routes.upload.require_matter")
    @patch("models.user.load_user")
    def test_running_job_is_not_retryable(self, load_user, require, get_job):
        load_user.return_value = _user()
        _sign_in(self.client)
        require.return_value = ("w1", self._matter_ref(
            {"filename": "brief.pdf", "storage_path": "workspaces/w/m/doc"}), {})
        get_job.return_value = {"status": "running"}

        response = self.client.post("/api/matters/matter-1/documents/doc-1/retry")

        self.assertEqual(response.status_code, 409)

    @patch("routes.upload.enqueue_job")
    @patch("routes.upload.update_job")
    @patch("routes.upload.patch_document")
    @patch("routes.upload.get_job")
    @patch("routes.upload.require_matter")
    @patch("models.user.load_user")
    def test_failed_durable_document_requeues(
        self, load_user, require, get_job, patch_doc, update_job, enqueue
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        require.return_value = ("w1", self._matter_ref(
            {"filename": "brief.pdf", "storage_path": "workspaces/w/m/doc"}), {})
        get_job.return_value = {"status": "failed"}

        response = self.client.post("/api/matters/matter-1/documents/doc-1/retry")

        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["job_id"], self.job_id)
        self.assertEqual(body["status_url"],
                         f"/api/matters/matter-1/jobs/{self.job_id}")
        update_job.assert_called_once()
        self.assertEqual(update_job.call_args.kwargs.get("status"), "queued")
        self.assertEqual(update_job.call_args.kwargs.get("attempts"), 0)
        enqueue.assert_called_once_with("matter-1", self.job_id)
        patch_doc.assert_called_once_with(
            "matter-1", "test-user", "doc-1", {"status": "processing", "error": None})


class UploadResponseTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("routes.upload.enqueue_job")
    @patch("routes.upload.create_job")
    @patch("routes.upload.upsert_document")
    @patch("routes.upload.secure_save_document", return_value=("brief.pdf", "/tmp/x.pdf"))
    @patch("routes.upload.get_or_create_context")
    @patch("models.user.load_user")
    def test_each_queued_job_carries_its_document_id(
        self, load_user, get_context, save, upsert, create_job, enqueue
    ):
        import io

        load_user.return_value = _user()
        _sign_in(self.client)
        get_context.return_value = {"workspace_id": "w1"}
        create_job.return_value = ({"job_id": "j1", "status": "queued"}, True)

        with patch("routes.upload.config.FIREBASE_STORAGE_BUCKET", None):
            response = self.client.post(
                "/upload",
                data={"context_id": "matter-1",
                      "files": (io.BytesIO(b"%PDF"), "brief.pdf")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 202)
        job = response.get_json()["jobs"][0]
        self.assertTrue(job["document_id"])


if __name__ == "__main__":
    unittest.main()
