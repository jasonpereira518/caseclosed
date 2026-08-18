"""Regression pins for the post-refresh integration pass: cross-cycle seams
found broken and fixed."""
import datetime
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


class IntakeBackslashTests(unittest.TestCase):
    """re.sub replacement templates: user text with backslashes must not 500."""

    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("models.user.load_user")
    def test_resubmission_with_backslashes_replaces_cleanly(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "", "messages": []}

        def submit(description):
            with patch("routes.intake.get_or_create_context", return_value=ctx), \
                    patch("routes.intake.create_job",
                          return_value=({"job_id": "j1", "status": "queued"}, True)), \
                    patch("routes.intake.enqueue_job"):
                return self.client.post("/intake", json={
                    "context_id": "m1", "case_title": "Smith",
                    "description": description,
                })

        submit(r"Evidence at C:\Users\jason\evidence.pdf")
        response = submit(r"Paid \30 per hour, files in C:\Users\jason")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(ctx["description"].count("===== CASE INTAKE ====="), 1)
        self.assertIn(r"C:\Users\jason", ctx["description"])


class DocumentRetryTransportTests(unittest.TestCase):
    """Cloud Tasks tombstones consumed task names; retries need a fresh suffix."""

    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("routes.upload.enqueue_job")
    @patch("routes.upload.update_job")
    @patch("routes.upload.patch_document")
    @patch("routes.upload.get_job", return_value={"status": "failed"})
    @patch("routes.upload.require_matter")
    @patch("models.user.load_user")
    def test_document_retry_uses_a_fresh_task_suffix(
        self, load_user, require, get_job, patch_doc, update_job, enqueue
    ):
        load_user.return_value = _user()
        _sign_in(self.client)
        snap = MagicMock(exists=True)
        snap.to_dict.return_value = {"filename": "b.pdf", "storage_path": "w/m/d"}
        matter_ref = MagicMock()
        matter_ref.collection.return_value.document.return_value.get.return_value = snap
        require.return_value = ("w1", matter_ref, {})

        response = self.client.post("/api/matters/m1/documents/d1/retry")

        self.assertEqual(response.status_code, 202)
        suffix = enqueue.call_args.kwargs.get("task_suffix", "")
        self.assertTrue(suffix.startswith("manual-"), f"missing task_suffix: {suffix!r}")


class JobExpiryConsistencyTests(unittest.TestCase):
    """Every terminal writer stamps expires_at; requeues clear it."""

    def test_claim_time_cancellation_stamps_expiry(self):
        from services import jobs

        captured = {}

        class FakeTxn:
            def set(self, ref, patch, merge=False):
                captured.update(patch)

        snap = MagicMock()
        snap.to_dict.return_value = {"status": "queued", "cancel_requested": True}
        ref = MagicMock()
        ref.get.return_value = snap

        moment = datetime.datetime(2026, 8, 18, tzinfo=datetime.timezone.utc)
        db = MagicMock()
        db.transaction.return_value = FakeTxn()
        with patch.object(jobs, "get_firestore_client", return_value=db), \
                patch.object(jobs, "now", return_value=moment), \
                patch.object(jobs.gc_firestore, "transactional", lambda fn: fn):
            jobs._claim(ref, lambda data: data)

        self.assertEqual(captured["status"], "cancelled")
        self.assertEqual(captured["expires_at"],
                         moment + datetime.timedelta(days=jobs.JOB_TTL_DAYS))

    def test_attempts_exhausted_stamps_expiry(self):
        from services import jobs

        captured = {}

        class FakeTxn:
            def set(self, ref, patch, merge=False):
                captured.update(patch)

        snap = MagicMock()
        snap.to_dict.return_value = {"status": "queued", "attempts": 99}
        ref = MagicMock()
        ref.get.return_value = snap
        db = MagicMock()
        db.transaction.return_value = FakeTxn()
        with patch.object(jobs, "get_firestore_client", return_value=db), \
                patch.object(jobs.gc_firestore, "transactional", lambda fn: fn):
            jobs._claim(ref, lambda data: data)

        self.assertEqual(captured["status"], "failed")
        self.assertIn("expires_at", captured)

    def test_requeue_clears_the_stale_expiry(self):
        from services import jobs
        from google.cloud import firestore as gc_firestore

        ref = MagicMock()
        data = jobs._update(ref, {"expires_at": "old"}, {"status": "queued", "attempts": 0})
        written = ref.set.call_args.args[0]
        self.assertIs(written["expires_at"], gc_firestore.DELETE_FIELD)


class BatchGradingSchemaTests(unittest.TestCase):
    """The batch grader must request the same dimension keys grade_case
    returns — the UI tooltip only knows those five."""

    def test_prompt_requests_the_ui_dimension_keys(self):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text='[{"index": 0, "score": 50}]')
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            llm.grade_cases_batch("s", [{"title": "A", "snippet": "x"}], {})

        prompt = chat.send_message.call_args[0][0]
        for key in ("factual_similarity", "legal_issues_match",
                    "causes_of_action_overlap", "jurisdictional_relevance",
                    "practical_utility"):
            self.assertIn(key, prompt)


if __name__ == "__main__":
    unittest.main()
