import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from models.user import User
from services.chat_orchestrator import classify_intent
from services.jobs import deterministic_job_id
from services.legal_corpus import JURISDICTIONS
from services.retrieval import chunk_text, validate_citations
from services.runtime_config import validate_runtime_config


class AsyncChatTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(id="test-user", email="lawyer@example.com", name="Jordan")
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True

    @patch("routes.chat.enqueue_job")
    @patch("routes.chat.append_message")
    @patch("routes.chat.create_job")
    @patch("routes.chat.get_or_create_context")
    @patch("models.user.load_user")
    def test_chat_acknowledges_a_persisted_job(self, load_user, get_context,
                                               create_job, append_message, enqueue_job):
        load_user.return_value = self.user
        get_context.return_value = {"title": "Matter"}
        create_job.return_value = ({"job_id": "job-1", "matter_id": "matter-1",
                                    "status": "queued", "progress": 0}, True)
        response = self.client.post("/chat", json={
            "context_id": "matter-1", "message": "Find supporting case law",
            "client_message_id": "client-1",
        })
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], "/api/matters/matter-1/jobs/job-1")
        append_message.assert_called_once()
        enqueue_job.assert_called_once_with("matter-1", "job-1")

    def test_chat_requires_nonempty_message(self):
        with patch("models.user.load_user", return_value=self.user):
            response = self.client.post("/chat", json={"context_id": "matter-1", "message": " "})
        self.assertEqual(response.status_code, 400)

    def test_intent_routing(self):
        self.assertEqual(classify_intent("Find precedent for this claim"), "legal_research")
        self.assertEqual(classify_intent("What does the contract say?"), "grounded_question")
        self.assertEqual(classify_intent("I received the notice on March 4"), "matter_update")

    def test_idempotency_key_is_stable_and_matter_scoped(self):
        first = deterministic_job_id("matter-a", "chat", "message-1")
        self.assertEqual(first, deterministic_job_id("matter-a", "chat", "message-1"))
        self.assertNotEqual(first, deterministic_job_id("matter-b", "chat", "message-1"))

    def test_citations_must_map_to_retrieved_source_and_exact_quote(self):
        sources = [{"source_id": "chunk-1", "source_type": "statute", "title": "Section 1",
                    "locator": "§ 1", "text": "A filing is due within thirty days."}]
        citations = validate_citations([
            {"source_id": "made-up", "quote": "not real"},
            {"source_id": "chunk-1", "quote": "within thirty days"},
        ], sources)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["source_id"], "chunk-1")
        self.assertEqual(citations[0]["quote"], "within thirty days")

    def test_chunking_is_bounded_and_overlapping(self):
        chunks = chunk_text("alpha " * 2000, max_chars=500, overlap=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 501 for chunk in chunks))

    def test_registry_covers_all_states_dc_and_federal(self):
        self.assertEqual(len(JURISDICTIONS), 52)
        self.assertIn("federal", JURISDICTIONS)
        self.assertIn("dc", JURISDICTIONS)

    def test_health_probe_is_public(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    @patch("services.runtime_config.config")
    def test_production_preflight_rejects_inline_jobs(self, runtime_config):
        runtime_config.PROJECT_ID = "project"
        runtime_config.SECRET_KEY = "strong-secret"
        runtime_config.AUTH_COOKIE_SECURE = True
        runtime_config.APP_BASE_URL = "https://caseclosed.example"
        runtime_config.TASKS_MODE = "inline"
        runtime_config.VECTOR_SEARCH_ENABLED = False
        runtime_config.DOCUMENT_AI_PROCESSOR_ID = ""
        runtime_config.FIREBASE_STORAGE_BUCKET = "bucket"
        runtime_config.LEGAL_CORPUS_SYNC_TOKEN = ""
        runtime_config.LEGAL_SOURCE_REGISTRY = []
        runtime_config.CHAT_FAST_MODEL = runtime_config.CHAT_REASONING_MODEL = "model"
        runtime_config.CLARIFIER_MODEL = runtime_config.SUMMARIZER_MODEL = "model"
        runtime_config.SCORER_MODEL = runtime_config.ANALYZER_MODEL = "model"
        runtime_config.DRAFT_MODEL = runtime_config.QUERY_MODEL = "model"
        runtime_config.TIMELINE_MODEL = runtime_config.STRENGTH_MODEL = "model"
        report = validate_runtime_config(production=True)
        self.assertFalse(report["valid"])
        self.assertIn("TASKS_MODE must be cloud in production", report["errors"])


if __name__ == "__main__":
    unittest.main()
