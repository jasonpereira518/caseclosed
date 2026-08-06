"""Coverage for services/analysis_orchestrator.py's process_analysis_job --
the shared "matter_analysis" job body introduced in Phase 4a, which /analyze
and /intake will queue onto instead of running the same 4-call LLM chain
synchronously inside the request.
"""
import unittest
from unittest.mock import patch

from services.analysis_orchestrator import process_analysis_job


class ProcessAnalysisJobTests(unittest.TestCase):
    @patch("services.analysis_orchestrator.replace_matter_records")
    @patch("services.analysis_orchestrator.patch_matter")
    @patch("services.analysis_orchestrator.extract_case_strength", return_value={"score": 3})
    @patch("services.analysis_orchestrator.extract_statutes", return_value=[{"code": "x"}])
    @patch("services.analysis_orchestrator.extract_timeline", return_value=[{"date": "2024-01-01"}])
    @patch("services.analysis_orchestrator.extract_structured_analysis", return_value={"issue": "breach"})
    @patch("services.analysis_orchestrator.load_matter")
    @patch("services.analysis_orchestrator.update_job")
    def test_analyzes_supplied_text_and_persists_results(
            self, update_job, load_matter, analysis, timeline, statutes, strength,
            patch_matter, replace_records):
        load_matter.return_value = {"description": "Existing facts.", "cases": [{"title": "A"}]}

        result = process_analysis_job("matter-1", "job-1",
                                      {"payload": {"text": "New facts supplied directly."},
                                       "requested_by": "user-1"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["analysis"], {"issue": "breach"})
        self.assertEqual(result["timeline"], [{"date": "2024-01-01"}])
        strength.assert_called_once_with("New facts supplied directly.", {"issue": "breach"},
                                         [{"code": "x"}], [{"title": "A"}])
        patch_matter.assert_called_once_with(
            "matter-1", "user-1", root=None,
            state={"analysis": {"issue": "breach"}, "statutes": [{"code": "x"}], "strength": {"score": 3}})
        replace_records.assert_called_once_with(
            "matter-1", "user-1", "timeline_events", [{"date": "2024-01-01"}])

    @patch("services.analysis_orchestrator.replace_matter_records")
    @patch("services.analysis_orchestrator.patch_matter")
    @patch("services.analysis_orchestrator.extract_case_strength", return_value={})
    @patch("services.analysis_orchestrator.extract_statutes", return_value=[])
    @patch("services.analysis_orchestrator.extract_timeline", return_value=[])
    @patch("services.analysis_orchestrator.extract_structured_analysis", return_value={})
    @patch("services.analysis_orchestrator.load_matter")
    @patch("services.analysis_orchestrator.update_job")
    def test_falls_back_to_stored_description_when_no_text_supplied(
            self, update_job, load_matter, analysis, timeline, statutes, strength,
            patch_matter, replace_records):
        load_matter.return_value = {"description": "Stored intake description.", "cases": []}

        result = process_analysis_job("matter-1", "job-1",
                                      {"payload": {}, "requested_by": "user-1"})

        self.assertEqual(result["status"], "success")
        analysis.assert_called_once_with("Stored intake description.")

    @patch("services.analysis_orchestrator.load_matter", return_value={"description": ""})
    @patch("services.analysis_orchestrator.update_job")
    def test_raises_when_no_text_is_available(self, update_job, load_matter):
        with self.assertRaises(ValueError):
            process_analysis_job("matter-1", "job-1", {"payload": {}, "requested_by": "user-1"})

    @patch("services.analysis_orchestrator.replace_matter_records")
    @patch("services.analysis_orchestrator.patch_matter")
    @patch("services.analysis_orchestrator.extract_case_strength", return_value={})
    @patch("services.analysis_orchestrator.extract_statutes", return_value=[])
    @patch("services.analysis_orchestrator.extract_timeline", return_value=[])
    @patch("services.analysis_orchestrator.extract_structured_analysis", return_value={})
    @patch("services.analysis_orchestrator.load_matter")
    @patch("services.analysis_orchestrator.update_job")
    def test_backfills_description_when_matter_has_none_yet(
            self, update_job, load_matter, analysis, timeline, statutes, strength,
            patch_matter, replace_records):
        load_matter.return_value = {"description": "", "cases": []}

        process_analysis_job("matter-1", "job-1",
                             {"payload": {"text": "First facts for this matter."},
                              "requested_by": "user-1"})

        self.assertEqual(patch_matter.call_args.kwargs["root"],
                         {"description": "First facts for this matter."})


if __name__ == "__main__":
    unittest.main()
