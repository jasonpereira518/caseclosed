"""Cycle 9: editable drafts (save endpoint), faithful export, doc_type
validation."""
import io
import unittest
from unittest.mock import patch

from docx import Document

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan Parker",
                profile_pic=None)


class DocTypeValidationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("models.user.load_user")
    def test_unknown_doc_type_is_rejected(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self.client.post("/draft", json={
            "context_id": "m1", "doc_type": "ransom note",
        })

        self.assertEqual(response.status_code, 400)

    @patch("routes.draft.enqueue_job")
    @patch("routes.draft.create_job",
           return_value=({"job_id": "j1", "status": "queued"}, True))
    @patch("models.user.load_user")
    def test_brief_is_accepted(self, load_user, create, enqueue):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self.client.post("/draft", json={
            "context_id": "m1", "doc_type": "brief",
        })

        self.assertEqual(response.status_code, 202)


class DraftSaveTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_unauthenticated_is_401_json(self):
        response = self.client.post("/draft/save",
                                    json={"context_id": "m1", "draft_text": "x"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "unauthorized"})

    @patch("routes.draft.get_stored_context", return_value={})
    @patch("models.user.load_user")
    def test_inaccessible_matter_is_404(self, load_user, get_ctx):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self.client.post("/draft/save",
                                    json={"context_id": "m1", "draft_text": "x"})

        self.assertEqual(response.status_code, 404)

    @patch("routes.draft.get_stored_context")
    @patch("models.user.load_user")
    def test_empty_text_is_400(self, load_user, get_ctx):
        load_user.return_value = _user()
        _sign_in(self.client)
        get_ctx.return_value = {"draft": "old"}

        response = self.client.post("/draft/save",
                                    json={"context_id": "m1", "draft_text": "   "})

        self.assertEqual(response.status_code, 400)

    @patch("routes.draft.get_stored_context")
    @patch("models.user.load_user")
    def test_save_persists_the_edited_draft(self, load_user, get_ctx):
        load_user.return_value = _user()
        _sign_in(self.client)
        context = {"draft": "old text"}
        get_ctx.return_value = context

        response = self.client.post("/draft/save", json={
            "context_id": "m1", "draft_text": "MEMORANDUM\n\nEdited by hand.",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(context["draft"], "MEMORANDUM\n\nEdited by hand.")


class ExportFidelityTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _export(self, context):
        with patch("routes.draft.get_stored_context", return_value=context):
            return self.client.post("/draft/export", json={"context_id": "m1"})

    def _paragraphs(self, response):
        document = Document(io.BytesIO(response.data))
        return [p.text for p in document.paragraphs]

    @patch("models.user.load_user")
    def test_brief_exports_with_a_brief_title(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._export({"title": "Rivera v. Northline",
                                 "draft": "ARGUMENT\nBody text.",
                                 "draft_type": "brief"})

        self.assertEqual(response.status_code, 200)
        paragraphs = self._paragraphs(response)
        self.assertIn("BRIEF", paragraphs)
        self.assertNotIn("MEMORANDUM", paragraphs)

    @patch("models.user.load_user")
    def test_from_line_carries_the_user_name(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._export({"title": "Rivera", "draft": "FACTS\nBody.",
                                 "draft_type": "memo"})

        joined = "\n".join(self._paragraphs(response))
        self.assertIn("Jordan Parker", joined)
        self.assertIn("MEMORANDUM", joined)

    @patch("models.user.load_user")
    def test_filename_comes_from_the_matter_title(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self._export({"title": "Rivera v. Northline",
                                 "draft": "FACTS\nBody.", "draft_type": "memo"})

        disposition = response.headers.get("Content-Disposition", "")
        self.assertIn("Rivera_v._Northline.docx", disposition)


if __name__ == "__main__":
    unittest.main()
