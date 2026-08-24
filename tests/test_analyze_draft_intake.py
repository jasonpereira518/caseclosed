"""Coverage for routes/intake.py, routes/draft.py, routes/notes.py,
routes/search.py, and services/chat_orchestrator.py's research/answer paths.

Intake and draft originally ran their LLM chains synchronously; Phase 4b
converted both to queue a job (matter_analysis / matter_draft) and return
202, matching /chat and /upload's contract. The route-level tests below
assert that contract; services/analysis_orchestrator.py's own job-body
behavior is covered separately in tests/test_analysis_job.py.
"""
import unittest
from unittest.mock import patch

from app import app
from models.user import User
from services.tenancy import AuthorizationError


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(id="test-user", email="lawyer@example.com", name="Jordan")
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True


class IntakeRouteTests(RouteTestCase):
    @patch("routes.intake.enqueue_job")
    @patch("routes.intake.create_job")
    @patch("routes.intake.get_or_create_context")
    @patch("models.user.load_user")
    def test_intake_persists_synchronously_then_queues_analysis_job(
            self, load_user, get_context, create_job, enqueue_job):
        load_user.return_value = self.user
        ctx = {"title": "New Session", "description": "", "cases": [], "messages": []}
        get_context.return_value = ctx
        create_job.return_value = ({"job_id": "job-1", "matter_id": "matter-1",
                                    "status": "queued"}, True)
        response = self.client.post("/intake", json={
            "context_id": "matter-1", "case_title": "Smith v. Jones",
            "description": "Breach of contract.",
        })
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], "/api/matters/matter-1/jobs/job-1")
        self.assertEqual(body["title"], "Smith v. Jones")
        # The description/title/messages fields are written synchronously,
        # before the job (which reads the matter's stored description) is queued.
        self.assertIn("CASE INTAKE", ctx["description"])
        self.assertEqual(ctx["title"], "Smith v. Jones")
        create_job.assert_called_once_with("matter-1", "test-user", "matter_analysis", {})
        enqueue_job.assert_called_once_with("matter-1", "job-1")

    @patch("models.user.load_user")
    def test_intake_requires_context_id(self, load_user):
        load_user.return_value = self.user
        response = self.client.post("/intake", json={"description": "No matter id"})
        self.assertEqual(response.status_code, 400)

    @patch("routes.intake.get_or_create_context", return_value=None)
    @patch("models.user.load_user")
    def test_intake_rejects_inaccessible_matter(self, load_user, get_context):
        load_user.return_value = self.user
        response = self.client.post("/intake", json={
            "context_id": "someone-elses-matter", "description": "x",
        })
        self.assertEqual(response.status_code, 403)


class DraftRouteTests(RouteTestCase):
    @patch("routes.draft.enqueue_job")
    @patch("routes.draft.create_job")
    @patch("models.user.load_user")
    def test_draft_queues_a_matter_draft_job(self, load_user, create_job, enqueue_job):
        load_user.return_value = self.user
        create_job.return_value = ({"job_id": "job-1", "matter_id": "matter-1",
                                    "status": "queued"}, True)
        response = self.client.post("/draft", json={"matter_id": "matter-1", "doc_type": "memo"})
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], "/api/matters/matter-1/jobs/job-1")
        create_job.assert_called_once_with(
            "matter-1", "test-user", "matter_draft", {"doc_type": "memo"})
        enqueue_job.assert_called_once_with("matter-1", "job-1")

    @patch("routes.draft.create_job", side_effect=AuthorizationError("matter access denied"))
    @patch("models.user.load_user")
    def test_draft_rejects_inaccessible_matter(self, load_user, create_job):
        load_user.return_value = self.user
        response = self.client.post("/draft", json={"matter_id": "someone-elses-matter"})
        self.assertEqual(response.status_code, 403)


class NotesRouteTests(RouteTestCase):
    @patch("routes.notes.get_context")
    @patch("routes.notes.context_belongs_to_user", return_value=True)
    @patch("models.user.load_user")
    def test_save_note_upserts_note_on_case(self, load_user, belongs, get_context):
        load_user.return_value = self.user
        ctx = {"cases": [{"title": "Case A"}]}
        get_context.return_value = ctx
        response = self.client.post("/case/notes", json={
            "matter_id": "matter-1", "case_index": 0, "content": "Follow up next week.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ctx["cases"][0]["notes"], "Follow up next week.")

    @patch("routes.notes.context_belongs_to_user", return_value=False)
    @patch("models.user.load_user")
    def test_save_note_rejects_matter_not_owned_by_user(self, load_user, belongs):
        load_user.return_value = self.user
        response = self.client.post("/case/notes", json={
            "matter_id": "someone-elses-matter", "case_index": 0, "content": "x",
        })
        self.assertEqual(response.status_code, 403)


class SearchRouteTests(RouteTestCase):
    @patch("models.user.load_user")
    def test_search_returns_empty_results_for_blank_query(self, load_user):
        load_user.return_value = self.user
        response = self.client.post("/search", json={"query": "  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"results": [], "total": 0, "query": ""})

    @patch("routes.search.search_user_contexts")
    @patch("models.user.load_user")
    def test_search_delegates_to_cross_matter_search(self, load_user, search_contexts):
        load_user.return_value = self.user
        search_contexts.return_value = [{"type": "case", "title": "Smith v. Jones"}]
        response = self.client.post("/search", json={"query": "Smith"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["total"], 1)
        search_contexts.assert_called_once_with("test-user", "Smith", {})


class ChatOrchestratorResearchAnswerTests(unittest.TestCase):
    @patch("services.chat_orchestrator.replace_matter_records")
    @patch("services.chat_orchestrator.patch_matter")
    @patch("services.chat_orchestrator.retrieve", return_value=[])
    @patch("services.chat_orchestrator.extract_case_strength", return_value={"score": 2})
    @patch("services.chat_orchestrator.extract_timeline", return_value=[])
    @patch("services.chat_orchestrator.rerank_cases")
    # _grade_round grades in one batched call and only falls back to grade_case
    # when that raises. Patch both, or the batch path reaches Gemini for real.
    @patch("services.chat_orchestrator.grade_cases_batch",
           return_value=[{"score": 20, "reason": "on point"}])
    @patch("services.chat_orchestrator.grade_case", return_value={"score": 20, "reason": "on point"})
    @patch("services.chat_orchestrator.query_courtlistener",
           return_value=[{"title": "Doe v. Roe", "citation": "1 F.3d 1", "pdf_link": "x"}])
    @patch("services.chat_orchestrator.generate_query", return_value="breach of contract")
    @patch("services.chat_orchestrator.summarize_case", return_value="A contract dispute.")
    @patch("services.chat_orchestrator.extract_structured_analysis", return_value={})
    @patch("services.chat_orchestrator.check_if_more_info_needed", return_value=(False, []))
    @patch("services.chat_orchestrator.update_job")
    @patch("services.chat_orchestrator.cancellation_requested", return_value=False)
    def test_research_returns_graded_case_results(
            self, cancellation, update_job, needs_more, analysis, summary, query,
            courtlistener, grade, grade_batch, rerank, timeline, strength, retrieve,
            patch_matter, replace_records):
        from services.chat_orchestrator import _research
        matter = {"description": "Original facts.", "clarify_attempts": 0}
        result = _research("matter-1", "job-1", "user-1", "more facts", matter)
        self.assertEqual(result["status"], "results")
        self.assertEqual(len(result["cases"]), 1)
        self.assertEqual(result["cases"][0]["relevance_score"], 20)
        replace_records.assert_any_call("matter-1", "user-1", "cases", result["cases"])

    @patch("services.chat_orchestrator.cancellation_requested", return_value=False)
    @patch("services.chat_orchestrator.answer_from_sources")
    @patch("services.chat_orchestrator.retrieve", return_value=[])
    @patch("services.chat_orchestrator.update_job")
    def test_answer_grounds_response_in_matter_narrative(
            self, update_job, retrieve, answer_from_sources, cancellation):
        from services.chat_orchestrator import _answer
        answer_from_sources.return_value = {
            "answer": "The filing deadline is 30 days.", "citations": [], "grounded": True,
        }
        matter = {"description": "The contract requires filing within 30 days.", "title": "Matter"}
        result = _answer("matter-1", "job-1", "user-1", "When is the deadline?", matter, "grounded_question")
        self.assertEqual(result["status"], "answer")
        self.assertTrue(result["grounded"])
        sources_arg = answer_from_sources.call_args.args[1]
        self.assertEqual(sources_arg[0]["source_id"], "matter-narrative")


if __name__ == "__main__":
    unittest.main()
