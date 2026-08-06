"""Safety-net coverage for routes/intake.py, routes/draft.py, routes/notes.py,
routes/search.py, and services/chat_orchestrator.py's research/answer paths —
written against today's synchronous contract so Phase 4's async conversion of
analyze/intake/draft has a red/green signal to work against.
"""
import unittest
from unittest.mock import Mock, patch

from app import app
from models.user import User


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(id="test-user", email="lawyer@example.com", name="Jordan")
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True


class IntakeRouteTests(RouteTestCase):
    @patch("routes.intake.save_context")
    @patch("routes.intake.extract_case_strength", return_value={"score": 1})
    @patch("routes.intake.extract_statutes", return_value=[])
    @patch("routes.intake.extract_timeline", return_value=[])
    @patch("routes.intake.extract_structured_analysis", return_value={})
    @patch("routes.intake.get_or_create_context")
    @patch("models.user.load_user")
    def test_intake_runs_analysis_chain_and_returns_success(
            self, load_user, get_context, analysis, timeline, statutes, strength, save_context):
        load_user.return_value = self.user
        ctx = {"title": "New Session", "description": "", "cases": [], "messages": []}
        get_context.return_value = ctx
        response = self.client.post("/intake", json={
            "context_id": "matter-1", "case_title": "Smith v. Jones",
            "description": "Breach of contract.",
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["context_id"], "matter-1")
        analysis.assert_called_once()
        save_context.assert_called_once()

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
    @patch("routes.draft.save_context")
    @patch("routes.draft.draft_legal_document", return_value="MEMORANDUM\n\nBody text.")
    @patch("routes.draft.get_stored_context")
    @patch("models.user.load_user")
    def test_draft_generates_document_from_existing_analysis(
            self, load_user, get_context, draft_doc, save_context):
        load_user.return_value = self.user
        get_context.return_value = {"title": "Matter", "analysis": {"summary": "x"}}
        response = self.client.post("/draft", json={"matter_id": "matter-1", "doc_type": "memo"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertIn("MEMORANDUM", body["document"])
        save_context.assert_called_once()

    @patch("routes.draft.get_stored_context", return_value=None)
    @patch("models.user.load_user")
    def test_draft_requires_existing_context(self, load_user, get_context):
        load_user.return_value = self.user
        response = self.client.post("/draft", json={"matter_id": "missing-matter"})
        self.assertEqual(response.status_code, 404)


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
            courtlistener, grade, rerank, timeline, strength, retrieve, patch_matter, replace_records):
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
