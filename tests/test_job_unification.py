"""Coverage for the unified job kernel introduced in Phase 3a: account jobs
now share services/jobs.py's status machine and vocabulary with matter jobs,
dispatch through services/worker.py:process_account_job, and are exposed via
routes/account.py's /api/account/export and /api/account/jobs/<id>.
"""
import unittest
from unittest.mock import Mock, patch

from app import app
from models.user import User
from services.worker import process_account_job


class ProcessAccountJobTests(unittest.TestCase):
    @patch("services.worker.update_account_job")
    @patch("services.worker.run_account_export", return_value={"storage_path": "users/u1/exports/j1.zip"})
    @patch("services.worker.get_account_job_internal")
    @patch("services.worker.claim_account_job")
    def test_account_export_job_dispatches_and_succeeds(
            self, claim, get_internal, run_export, update):
        claim.return_value = {"status": "running"}
        get_internal.return_value = (object(), {"kind": "account_export", "attempts": 1})
        update.return_value = {"status": "succeeded", "result": {"storage_path": "users/u1/exports/j1.zip"}}

        result = process_account_job("user-1", "job-1")

        self.assertEqual(result["status"], "succeeded")
        run_export.assert_called_once_with("user-1", "job-1", get_internal.return_value[1])
        self.assertEqual(update.call_args.kwargs["stage"], "complete")

    @patch("services.worker.update_account_job")
    @patch("services.worker.run_account_export", side_effect=RuntimeError("storage unavailable"))
    @patch("services.worker.get_account_job_internal")
    @patch("services.worker.claim_account_job")
    def test_account_export_job_failure_is_terminal_not_retried(
            self, claim, get_internal, run_export, update):
        claim.return_value = {"status": "running"}
        get_internal.return_value = (object(), {"kind": "account_export", "attempts": 1})
        update.return_value = {"status": "failed"}

        result = process_account_job("user-1", "job-1")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(update.call_args.kwargs["status"], "failed")

    @patch("services.worker.claim_account_job", return_value=None)
    def test_unclaimable_account_job_returns_none(self, claim):
        self.assertIsNone(process_account_job("user-1", "job-1"))


class AccountExportRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SERVER_NAME="localhost")
        self.client = app.test_client()
        self.user = User(id="test-user", email="lawyer@example.com", name="Jordan")
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True

    @patch("routes.account.enqueue_account_job")
    @patch("routes.account.create_account_job")
    @patch("models.user.load_user")
    def test_create_export_queues_a_unified_job(self, load_user, create_job, enqueue):
        load_user.return_value = self.user
        create_job.return_value = ({"job_id": "job-1", "uid": "test-user", "status": "queued"}, True)
        response = self.client.post("/api/account/export")
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], "/api/account/jobs/job-1")
        create_job.assert_called_once_with("test-user", "account_export", {})
        enqueue.assert_called_once_with("test-user", "job-1")

    @patch("routes.account.signed_download_url", return_value="https://signed.example/export.zip")
    @patch("routes.account.get_account_job")
    @patch("models.user.load_user")
    def test_account_job_status_includes_download_url_when_succeeded(
            self, load_user, get_job, signed_url):
        load_user.return_value = self.user
        get_job.return_value = {"job_id": "job-1", "uid": "test-user", "status": "succeeded",
                                "result": {"storage_path": "users/test-user/exports/job-1.zip"}}
        response = self.client.get("/api/account/jobs/job-1")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["download_url"], "https://signed.example/export.zip")
        signed_url.assert_called_once_with("users/test-user/exports/job-1.zip")

    @patch("routes.account.get_account_job", return_value=None)
    @patch("models.user.load_user")
    def test_account_job_status_404s_for_unknown_job(self, load_user, get_job):
        load_user.return_value = self.user
        response = self.client.get("/api/account/jobs/missing-job")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
