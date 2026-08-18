"""Cycle 10: light-loading search, document filename results, archived
labels."""
import unittest
from unittest.mock import MagicMock, patch


class LightLoadTests(unittest.TestCase):
    def test_document_text_is_skipped_when_not_requested(self):
        from services.matters import _load_documents

        doc_snap = MagicMock()
        doc_snap.to_dict.return_value = {"record_id": "doc-1", "position": 0,
                                         "filename": "brief.pdf", "text_chunked": True}
        ref = MagicMock()
        ref.collection.return_value.stream.return_value = [doc_snap]

        result = _load_documents(ref, include_text=False)

        self.assertEqual(result[0]["filename"], "brief.pdf")
        self.assertNotIn("text", result[0])
        # The text_chunks subcollection must never be touched.
        ref.collection.return_value.document.assert_not_called()

    def test_search_requests_the_light_load(self):
        from models import search as search_model

        with patch.object(search_model, "list_workspaces",
                          return_value=[{"workspace_id": "w1"}]), \
                patch.object(search_model, "list_matters",
                             return_value=[{"matter_id": "m1", "status": "active"}]), \
                patch.object(search_model, "load_matter", return_value={}) as load:
            search_model.search_user_contexts("u1", "anything")

        self.assertFalse(load.call_args.kwargs.get("include_document_text", True))


class FilenameSearchTests(unittest.TestCase):
    def _run(self, query, filters=None):
        from models import search as search_model

        matter = {
            "title": "Rivera v. Northline",
            "updated_at": "2026-08-01T00:00:00Z",
            "uploaded_documents": [
                {"record_id": "doc-1", "filename": "Dispatch_Log.txt", "included": True},
            ],
            "messages": [], "cases": [],
        }
        with patch.object(search_model, "list_workspaces",
                          return_value=[{"workspace_id": "w1"}]), \
                patch.object(search_model, "list_matters",
                             return_value=[{"matter_id": "m1", "status": "active"}]), \
                patch.object(search_model, "load_matter", return_value=matter):
            return search_model.search_user_contexts("u1", query, filters)

    def test_filenames_match(self):
        results = self._run("dispatch")
        documents = [r for r in results if r["type"] == "document"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["title"], "Dispatch_Log.txt")
        self.assertEqual(documents[0]["context_id"], "m1")

    def test_documents_filter_isolates_them(self):
        results = self._run("dispatch", {"content_types": ["documents"]})
        self.assertTrue(results)
        self.assertTrue(all(r["type"] == "document" for r in results))

    def test_excluding_documents_hides_them(self):
        results = self._run("dispatch", {"content_types": ["sessions"]})
        self.assertFalse([r for r in results if r["type"] == "document"])


class ArchivedLabelTests(unittest.TestCase):
    def test_results_from_archived_matters_are_flagged(self):
        from models import search as search_model

        with patch.object(search_model, "list_workspaces",
                          return_value=[{"workspace_id": "w1"}]), \
                patch.object(search_model, "list_matters", return_value=[
                    {"matter_id": "m1", "status": "archived"},
                    {"matter_id": "m2", "status": "active"},
                ]), \
                patch.object(search_model, "load_matter", side_effect=[
                    {"title": "Closed matter about negligence"},
                    {"title": "Open matter about negligence"},
                ]):
            results = search_model.search_user_contexts("u1", "negligence")

        by_title = {r["title"]: r for r in results}
        self.assertTrue(by_title["Closed matter about negligence"]["archived"])
        self.assertFalse(by_title["Open matter about negligence"]["archived"])


if __name__ == "__main__":
    unittest.main()
