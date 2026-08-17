"""Cycle 7: annotation-preserving re-research, batched grading over a wider
net, retryable treatment checks, and citation normalization."""
import unittest
from unittest.mock import MagicMock, patch


def _case(title, *, link=None, score=50, bookmarked=False, notes="", follow_ups=None):
    return {
        "title": title, "citation": f"{title} Cite", "pdf_link": link or f"https://cl/{title}",
        "snippet": f"snippet {title}", "relevance_score": score,
        "bookmarked": bookmarked, "notes": notes, "follow_ups": follow_ups or [],
    }


class MergeResearchResultsTests(unittest.TestCase):
    def _merge(self, existing, fresh, cap=20):
        from services.chat_orchestrator import merge_research_results

        return merge_research_results(existing, fresh, cap=cap)

    def test_annotated_cases_survive_when_absent_from_fresh_results(self):
        existing = [
            _case("Kept", bookmarked=True),
            _case("Noted", notes="lead authority"),
            _case("Asked", follow_ups=[{"question": "q", "answer": "a"}]),
            _case("Dropped"),
        ]
        fresh = [_case("Brand New", score=80)]

        merged = self._merge(existing, fresh)
        titles = [c["title"] for c in merged]

        for kept in ("Kept", "Noted", "Asked", "Brand New"):
            self.assertIn(kept, titles)
        self.assertNotIn("Dropped", titles)

    def test_refound_annotated_case_refreshes_relevance_but_keeps_annotations(self):
        existing = [_case("Alvarado", link="https://cl/alvarado", score=40,
                          bookmarked=True, notes="pull the concurrence")]
        existing[0]["treatment"] = {"status": "good", "checked": True}
        fresh = [{**_case("Alvarado", link="https://cl/alvarado", score=91),
                  "relevance_reason": "directly on point"}]

        merged = self._merge(existing, fresh)

        self.assertEqual(len(merged), 1)
        case = merged[0]
        self.assertEqual(case["relevance_score"], 91)
        self.assertEqual(case["relevance_reason"], "directly on point")
        self.assertTrue(case["bookmarked"])
        self.assertEqual(case["notes"], "pull the concurrence")
        self.assertEqual(case["treatment"], {"status": "good", "checked": True})

    def test_cap_applies_to_unannotated_results_only(self):
        existing = [_case(f"Pinned {i}", bookmarked=True) for i in range(5)]
        fresh = [_case(f"Fresh {i}", score=100 - i) for i in range(30)]

        merged = self._merge(existing, fresh, cap=20)

        pinned = [c for c in merged if c["title"].startswith("Pinned")]
        unpinned = [c for c in merged if c["title"].startswith("Fresh")]
        self.assertEqual(len(pinned), 5)
        self.assertEqual(len(unpinned), 20)

    def test_sorted_by_relevance_descending(self):
        merged = self._merge([_case("Low", score=20, bookmarked=True)],
                             [_case("High", score=90)])
        self.assertEqual([c["title"] for c in merged], ["High", "Low"])


class BatchGradingTests(unittest.TestCase):
    def test_batch_scores_map_back_to_cases(self):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(
            text='[{"index": 0, "score": 80, "reason": "on point", "dimensions": {}},'
                 ' {"index": 1, "score": 5, "reason": "off topic", "dimensions": {}}]')
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            grades = llm.grade_cases_batch("summary", [
                {"title": "A", "snippet": "sa"}, {"title": "B", "snippet": "sb"},
            ], {})

        self.assertEqual(grades[0]["score"], 80)
        self.assertEqual(grades[1]["score"], 5)

    def test_unusable_output_raises_for_fallback(self):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text="no json here")
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            with self.assertRaises(ValueError):
                llm.grade_cases_batch("summary", [{"title": "A", "snippet": "s"}], {})

    def test_orchestrator_falls_back_to_per_case_grading(self):
        from services.chat_orchestrator import _grade_round

        cases = [{"title": "A", "snippet": "sa"}, {"title": "B", "snippet": "sb"}]
        with patch("services.chat_orchestrator.grade_cases_batch",
                   side_effect=RuntimeError("model down")), \
                patch("services.chat_orchestrator.grade_case",
                      return_value={"score": 42, "reason": "r", "dimensions": {}}) as single:
            grades = _grade_round("summary", cases, {})

        self.assertEqual(single.call_count, 2)
        self.assertEqual([g["score"] for g in grades], [42, 42])


class CourtListenerTests(unittest.TestCase):
    def _response(self, results):
        response = MagicMock()
        response.json.return_value = {"results": results}
        return response

    @patch("services.courtlistener.requests.get")
    def test_returns_up_to_ten_results(self, get):
        get.return_value = self._response([
            {"caseName": f"Case {i}", "citation": "", "absolute_url": f"/opinion/{i}/x/"}
            for i in range(15)
        ])
        from services.courtlistener import query_courtlistener

        self.assertEqual(len(query_courtlistener("q")), 10)

    @patch("services.courtlistener.requests.get")
    def test_list_citations_are_normalized(self, get):
        get.return_value = self._response([
            {"caseName": "A", "citation": ["1 U.S. 1", "2 X. 2", "3 Y. 3"],
             "absolute_url": "/opinion/1/a/"},
        ])
        from services.courtlistener import query_courtlistener

        citation = query_courtlistener("q")[0]["citation"]
        self.assertEqual(citation, "1 U.S. 1, 2 X. 2")

    @patch("services.courtlistener.requests.get", side_effect=RuntimeError("rate limited"))
    def test_failed_treatment_check_is_not_cached(self, get):
        from services.courtlistener import check_case_treatment

        treatment = check_case_treatment("12345")
        self.assertEqual(treatment["status"], "unknown")
        self.assertFalse(treatment["checked"])

    def test_missing_cluster_id_is_not_cached_either(self):
        from services.courtlistener import check_case_treatment

        self.assertFalse(check_case_treatment(None)["checked"])

    @patch("services.courtlistener.requests.get")
    def test_clean_result_is_cached(self, get):
        get.return_value = self._response([])
        from services.courtlistener import check_case_treatment

        treatment = check_case_treatment("12345")
        self.assertEqual(treatment["status"], "good")
        self.assertTrue(treatment["checked"])


class ResearchIntegrationTests(unittest.TestCase):
    def test_merged_list_reaches_the_cases_collection(self):
        from services import chat_orchestrator as chat

        matter = {
            "description": "facts", "analysis": {}, "clarify_attempts": 0,
            "messages": [], "intake": {"jurisdiction": "Ohio"},
            "cases": [_case("Pinned", bookmarked=True, score=70)],
        }
        fresh = [_case("Fresh Authority", score=88)]

        with patch.object(chat, "update_job"), \
                patch.object(chat, "cancellation_requested", return_value=False), \
                patch.object(chat, "check_if_more_info_needed", return_value=(False, [])), \
                patch.object(chat, "patch_matter"), \
                patch.object(chat, "extract_structured_analysis", return_value={}), \
                patch.object(chat, "summarize_case", return_value="summary"), \
                patch.object(chat, "generate_query", return_value="query one"), \
                patch.object(chat, "query_courtlistener", return_value=fresh), \
                patch.object(chat, "_grade_round",
                             return_value=[{"score": 88, "reason": "r", "dimensions": {}}]), \
                patch.object(chat, "rerank_cases", side_effect=lambda s, a, r: r), \
                patch.object(chat, "extract_timeline", return_value=[]), \
                patch.object(chat, "retrieve", return_value=[]), \
                patch.object(chat, "extract_case_strength", return_value={}), \
                patch.object(chat, "replace_matter_records") as replace:
            chat._research("m1", "j1", "u1", "find cases", matter)

        cases_written = [call for call in replace.call_args_list
                         if call.args[2] == "cases"][0].args[3]
        titles = [c["title"] for c in cases_written]
        self.assertIn("Pinned", titles)
        self.assertIn("Fresh Authority", titles)


if __name__ == "__main__":
    unittest.main()
