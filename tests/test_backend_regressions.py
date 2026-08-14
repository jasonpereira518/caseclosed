import json
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import app
import google.cloud
from models.context import FirestoreBackedDict
from models.user import User
from services.pdf import allowed_file
from services.task_queue import enqueue_account_job
from services.retrieval import _vector_search, delete_matter_index, index_matter_document
from services.worker import process_job


class BackendRouteRegressionTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(id="test-user", email="lawyer@example.com", name="Jordan")
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True

    @patch("routes.analyze.enqueue_job")
    @patch("routes.analyze.create_job")
    @patch("models.user.load_user")
    def test_analyze_queues_a_matter_analysis_job(self, load_user, create_job, enqueue_job):
        load_user.return_value = self.user
        create_job.return_value = ({"job_id": "job-1", "matter_id": "matter-1",
                                    "status": "queued"}, True)
        response = self.client.post("/analyze", json={
            "context_id": "matter-1", "text": "Facts supplied directly",
        })
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], "/api/matters/matter-1/jobs/job-1")
        create_job.assert_called_once_with(
            "matter-1", "test-user", "matter_analysis", {"text": "Facts supplied directly"})
        enqueue_job.assert_called_once_with("matter-1", "job-1")

    @patch("models.user.load_user")
    def test_analyze_requires_matter_id(self, load_user):
        load_user.return_value = self.user
        response = self.client.post("/analyze", json={"text": "No matter attached"})
        self.assertEqual(response.status_code, 400)

    @patch("models.user.load_user")
    def test_document_toggle_rejects_missing_payload(self, load_user):
        load_user.return_value = self.user
        response = self.client.post("/documents/toggle", json=None)
        self.assertEqual(response.status_code, 400)

    def test_legacy_doc_is_rejected_before_ingestion(self):
        self.assertFalse(allowed_file("legacy.doc"))
        self.assertTrue(allowed_file("current.docx"))

    def test_upload_limit_stays_under_the_cloud_run_request_cap(self):
        """Cloud Run rejects HTTP/1 requests over 32 MiB at its front end with an
        opaque error, before Flask ever sees them. A higher app-level limit means
        the 32-50 MB band fails with no usable message."""
        self.assertLessEqual(app.config["MAX_CONTENT_LENGTH"], 32 * 1024 * 1024)


class VectorCleanupRegressionTests(unittest.TestCase):
    @patch("services.retrieval.chunk_text", return_value=[])
    @patch("services.retrieval._vector_delete")
    @patch("services.retrieval.require_matter")
    def test_reindex_removes_prior_vector_objects(self, require_matter, vector_delete, chunk_text):
        old = Mock()
        old.id = "document-1-00000"
        collection = Mock()
        collection.stream.return_value = [old]
        matter_ref = Mock()
        matter_ref.collection.return_value = collection
        require_matter.return_value = ("workspace-1", matter_ref, {})

        index_matter_document("matter-1", "user-1", "document-1", "Notice", "new text")

        vector_delete.assert_called_once()
        old.reference.delete.assert_called_once()

    @patch("services.retrieval._vector_delete")
    @patch("services.retrieval.require_matter")
    def test_matter_index_deletion_removes_every_vector(self, require_matter, vector_delete):
        chunks = [Mock(id="document-1-00000"), Mock(id="document-2-00000")]
        collection = Mock()
        collection.stream.return_value = chunks
        matter_ref = Mock()
        matter_ref.collection.return_value = collection
        require_matter.return_value = ("workspace-1", matter_ref, {})

        delete_matter_index("matter-1", "user-1")

        self.assertEqual(vector_delete.call_count, 2)
        for chunk in chunks:
            chunk.reference.delete.assert_called_once()

    @patch("services.retrieval.config")
    def test_vector_search_uses_sdk_output_fields_message(self, retrieval_config):
        retrieval_config.VECTOR_SEARCH_FIELD = "text_embedding"
        retrieval_config.VECTOR_SEARCH_PROJECT_ID = "project"
        retrieval_config.VECTOR_SEARCH_LOCATION = "us-central1"
        output_fields = Mock(return_value="output-fields-message")
        semantic_search = Mock(return_value="semantic-search-message")
        request_type = Mock(return_value="search-request")
        client = Mock()
        client.search_data_objects.return_value = []
        vector_module = SimpleNamespace(
            DataObjectSearchServiceClient=Mock(return_value=client),
            OutputFields=output_fields,
            SemanticSearch=semantic_search,
            SearchDataObjectsRequest=request_type,
        )

        with patch.dict(sys.modules, {"google.cloud.vectorsearch_v1": vector_module}), \
                patch.object(google.cloud, "vectorsearch_v1", vector_module, create=True):
            self.assertEqual(_vector_search("collection", "query", 5, {"matter_id": "m"}), [])

        output_fields.assert_called_once()
        self.assertIn("text", output_fields.call_args.kwargs["data_fields"])
        self.assertEqual(semantic_search.call_args.kwargs["output_fields"],
                         "output-fields-message")


class GranularPersistenceRegressionTests(unittest.TestCase):
    @patch("models.context.save_matter")
    @patch("models.context.patch_matter")
    def test_field_updates_do_not_rewrite_unrelated_collections(self, patch_matter, save_matter):
        context = FirestoreBackedDict("matter-1", "user-1", {
            "title": "Old", "cases": [], "messages": [{"content": "keep me"}],
        })

        context["title"] = "New"

        patch_matter.assert_called_once_with(
            "matter-1", "user-1", root={"title": "New"}, state=None)
        save_matter.assert_not_called()

        context["cases"] = [{"title": "Authority"}]
        save_matter.assert_called_once_with(
            "matter-1", {"cases": [{"title": "Authority"}]})


class DocumentRetryRegressionTests(unittest.TestCase):
    @patch("services.worker.cleanup_document_source")
    @patch("services.worker.patch_document")
    @patch("services.worker.update_job")
    @patch("services.worker.ingest_document_job", side_effect=RuntimeError("temporary"))
    @patch("services.worker.get_job_internal")
    @patch("services.worker.claim_job")
    def test_transient_document_failure_keeps_source_for_retry(
            self, claim, get_internal, ingest, update, patch_document, cleanup):
        claim.return_value = {"status": "running"}
        get_internal.return_value = (object(), {
            "kind": "document_ingest", "attempts": 1,
            "payload": {"document_id": "document-1", "storage_path": "private/original"},
            "requested_by": "user-1",
        })
        update.return_value = {"status": "queued", "stage": "retrying"}

        result = process_job("matter-1", "job-1")

        self.assertEqual(result["status"], "queued")
        self.assertEqual(patch_document.call_args.args[3]["status"], "retrying")
        cleanup.assert_not_called()

    @patch("services.worker.cleanup_document_source")
    @patch("services.worker.patch_document")
    @patch("services.worker.update_job")
    @patch("services.worker.ingest_document_job", side_effect=RuntimeError("permanent"))
    @patch("services.worker.get_job_internal")
    @patch("services.worker.claim_job")
    def test_final_document_failure_releases_retry_source(
            self, claim, get_internal, ingest, update, patch_document, cleanup):
        claim.return_value = {"status": "running"}
        get_internal.return_value = (object(), {
            "kind": "document_ingest", "attempts": 3,
            "payload": {"document_id": "document-1", "local_path": "/tmp/source"},
            "requested_by": "user-1",
        })
        update.return_value = {"status": "failed", "stage": "failed"}

        result = process_job("matter-1", "job-1")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(patch_document.call_args.args[3]["status"], "failed")
        cleanup.assert_called_once()


class AccountJobRegressionTests(unittest.TestCase):
    @patch("services.task_queue.config")
    def test_account_export_uses_shared_worker_entrypoint(self, task_queue_config):
        task_queue_config.TASKS_MODE = "cloud"
        task_queue_config.TASKS_PROJECT_ID = "project"
        task_queue_config.TASKS_LOCATION = "us-central1"
        task_queue_config.TASKS_QUEUE = "caseclosed-jobs"
        task_queue_config.TASKS_WORKER_URL = "https://caseclosed.example/internal/jobs/run"
        task_queue_config.TASKS_SERVICE_ACCOUNT = "tasks@example.iam.gserviceaccount.com"
        task_queue_config.TASKS_WORKER_AUDIENCE = "https://caseclosed.example"
        task_queue_config.INTERNAL_WORKER_TOKEN = ""
        client = Mock()
        client.queue_path.return_value = "queue-path"
        client.task_path.return_value = "task-path"
        tasks_module = SimpleNamespace(
            CloudTasksClient=Mock(return_value=client),
            HttpMethod=SimpleNamespace(POST="POST"),
        )

        with patch.dict(sys.modules, {"google.cloud.tasks_v2": tasks_module}), \
                patch.object(google.cloud, "tasks_v2", tasks_module, create=True):
            result = enqueue_account_job("user-1", "export-1")

        self.assertEqual(result["transport"], "cloud")
        task = client.create_task.call_args.kwargs["task"]
        self.assertEqual(task["http_request"]["url"], "https://caseclosed.example/internal/jobs/run")
        self.assertEqual(task["http_request"]["oidc_token"]["service_account_email"],
                         "tasks@example.iam.gserviceaccount.com")
        body = json.loads(task["http_request"]["body"])
        self.assertEqual(body, {"uid": "user-1", "job_id": "export-1", "scope": "account"})
        self.assertNotIn("X-Worker-Token", task["http_request"]["headers"])


if __name__ == "__main__":
    unittest.main()
