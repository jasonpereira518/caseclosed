"""Cycle 8: manual timeline events survive rebuilds, guarded per-event
deletion, and 404 alignment for the timeline routes."""
import unittest
from unittest.mock import patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


MANUAL = {"date": "2026-04-02", "description": "Notice of claim served",
          "category": "event", "source": "manual"}
AUTO_OLD = {"date": "2026-03-14", "description": "Old extraction",
            "category": "incident", "source": "auto"}
AUTO_NEW = {"date": "2026-03-15", "description": "Fresh extraction",
            "category": "event", "source": "auto"}


class MergeTimelineTests(unittest.TestCase):
    def test_manual_events_survive_and_extracted_are_replaced(self):
        from services.analysis_orchestrator import merge_timeline

        merged = merge_timeline([MANUAL, AUTO_OLD], [AUTO_NEW])
        descriptions = [e["description"] for e in merged]

        self.assertIn("Notice of claim served", descriptions)
        self.assertIn("Fresh extraction", descriptions)
        self.assertNotIn("Old extraction", descriptions)

    def test_result_is_date_sorted(self):
        from services.analysis_orchestrator import merge_timeline

        merged = merge_timeline([MANUAL], [AUTO_NEW])
        self.assertEqual([e["date"] for e in merged], ["2026-03-15", "2026-04-02"])


class RebuildPreservationTests(unittest.TestCase):
    @patch("services.analysis_orchestrator.replace_matter_records")
    @patch("services.analysis_orchestrator.patch_matter")
    @patch("services.analysis_orchestrator.extract_case_strength", return_value={})
    @patch("services.analysis_orchestrator.extract_statutes", return_value=[])
    @patch("services.analysis_orchestrator.extract_timeline", return_value=[AUTO_NEW])
    @patch("services.analysis_orchestrator.extract_structured_analysis", return_value={})
    @patch("services.analysis_orchestrator.update_job")
    @patch("services.analysis_orchestrator.load_matter")
    def test_analysis_job_preserves_manual_events(
        self, load_matter, update, extract, timeline, statutes, strength, patch_m, replace
    ):
        from services.analysis_orchestrator import process_analysis_job

        load_matter.return_value = {"description": "facts",
                                    "timeline": [MANUAL, AUTO_OLD], "cases": []}

        process_analysis_job("m1", "j1", {"requested_by": "u1", "payload": {}})

        written = replace.call_args.args[3]
        descriptions = [e["description"] for e in written]
        self.assertIn("Notice of claim served", descriptions)
        self.assertNotIn("Old extraction", descriptions)

    def test_research_branch_preserves_manual_events(self):
        from services import chat_orchestrator as chat

        matter = {
            "description": "facts", "analysis": {}, "clarify_attempts": 0,
            "messages": [], "intake": {}, "cases": [],
            "timeline": [MANUAL, AUTO_OLD],
        }
        with patch.object(chat, "update_job"), \
                patch.object(chat, "cancellation_requested", return_value=False), \
                patch.object(chat, "check_if_more_info_needed", return_value=(False, [])), \
                patch.object(chat, "patch_matter"), \
                patch.object(chat, "extract_structured_analysis", return_value={}), \
                patch.object(chat, "summarize_case", return_value="summary"), \
                patch.object(chat, "generate_query", return_value="q"), \
                patch.object(chat, "query_courtlistener", return_value=[]), \
                patch.object(chat, "_grade_round", return_value=[]), \
                patch.object(chat, "extract_timeline", return_value=[AUTO_NEW]), \
                patch.object(chat, "retrieve", return_value=[]), \
                patch.object(chat, "extract_case_strength", return_value={}), \
                patch.object(chat, "replace_matter_records") as replace:
            chat._research("m1", "j1", "u1", "find cases", matter)

        written = [call for call in replace.call_args_list
                   if call.args[2] == "timeline_events"][0].args[3]
        descriptions = [e["description"] for e in written]
        self.assertIn("Notice of claim served", descriptions)
        self.assertNotIn("Old extraction", descriptions)


class TimelineDeleteRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.timeline = [dict(AUTO_NEW), dict(MANUAL)]

    def _delete(self, payload, ctx=None):
        context = {"timeline": self.timeline} if ctx is None else ctx
        with patch("routes.analyze.get_stored_context", return_value=context):
            return self.client.post("/timeline/delete",
                                    json={"context_id": "m1", **payload})

    def test_unauthenticated_is_401_json(self):
        response = self.client.post("/timeline/delete", json={"context_id": "m1"})
        self.assertEqual(response.status_code, 401)

    @patch("models.user.load_user")
    def test_inaccessible_matter_is_404(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        response = self._delete({"index": 0, "date": AUTO_NEW["date"],
                                 "description": AUTO_NEW["description"]}, ctx={})
        self.assertEqual(response.status_code, 404)

    @patch("models.user.load_user")
    def test_matching_event_is_removed(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._delete({"index": 1, "date": MANUAL["date"],
                                 "description": MANUAL["description"]})

        self.assertEqual(response.status_code, 200)
        remaining = response.get_json()["timeline"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["description"], "Fresh extraction")

    @patch("models.user.load_user")
    def test_stale_client_gets_409(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._delete({"index": 0, "date": "2020-01-01",
                                 "description": "something else entirely"})

        self.assertEqual(response.status_code, 409)

    @patch("models.user.load_user")
    def test_out_of_range_index_is_400(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._delete({"index": 12, "date": "x", "description": "y"})

        self.assertEqual(response.status_code, 400)


class TimelineAddAlignmentTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("routes.analyze.get_stored_context", return_value={})
    @patch("models.user.load_user")
    def test_inaccessible_matter_is_404_on_add(self, load_user, get_ctx):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self.client.post("/timeline/add", json={
            "context_id": "m1", "date": "2026-01-01", "description": "x",
        })

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
