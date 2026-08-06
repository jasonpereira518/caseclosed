import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from services.worker import process_job


class WorkerTests(unittest.TestCase):
    @patch("services.worker.update_job")
    @patch("services.worker.process_chat_job")
    @patch("services.worker.get_job_internal")
    @patch("services.worker.claim_job")
    def test_chat_job_dispatches_and_succeeds(self, claim, get_internal, process_chat, update):
        claim.return_value = {"status": "running"}
        data = {"kind": "chat", "attempts": 1, "payload": {}, "requested_by": "user"}
        get_internal.return_value = (object(), data)
        process_chat.return_value = {"status": "answer", "message": "Supported answer"}
        update.return_value = {"status": "succeeded"}
        result = process_job("matter", "job")
        self.assertEqual(result["status"], "succeeded")
        process_chat.assert_called_once_with("matter", "job", data)
        self.assertEqual(update.call_args.kwargs["stage"], "complete")

    @patch("services.worker.update_job")
    @patch("services.worker.process_chat_job", side_effect=RuntimeError("temporary"))
    @patch("services.worker.get_job_internal")
    @patch("services.worker.claim_job")
    def test_transient_chat_failure_returns_to_queue(self, claim, get_internal, process_chat, update):
        claim.return_value = {"status": "running"}
        get_internal.return_value = (object(), {
            "kind": "chat", "attempts": 1, "payload": {}, "requested_by": "user"})
        update.return_value = {"status": "queued", "stage": "retrying"}
        result = process_job("matter", "job")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(update.call_args.kwargs["stage"], "retrying")


class InternalOidcRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    @patch("routes.jobs.process_job", return_value={"status": "succeeded"})
    @patch("routes.jobs.verify_worker_request", return_value=True)
    @patch("routes.jobs.config")
    def test_worker_accepts_verified_service_account_oidc(self, job_config, verify, process):
        job_config.TASKS_MODE = "cloud"
        response = self.client.post("/internal/jobs/run", json={
            "matter_id": "matter", "job_id": "job"},
            headers={"Authorization": "Bearer signed-token"})
        self.assertEqual(response.status_code, 200)
        process.assert_called_once_with("matter", "job")

    @patch("routes.jobs.process_account_job", return_value={"status": "succeeded"})
    @patch("routes.jobs.verify_worker_request", return_value=True)
    @patch("routes.jobs.config")
    def test_worker_dispatches_account_scope_by_uid(self, job_config, verify, process_account):
        job_config.TASKS_MODE = "cloud"
        response = self.client.post("/internal/jobs/run", json={
            "uid": "user-1", "job_id": "job", "scope": "account"},
            headers={"Authorization": "Bearer signed-token"})
        self.assertEqual(response.status_code, 200)
        process_account.assert_called_once_with("user-1", "job")

    @patch("routes.jobs.config")
    def test_worker_rejects_unverified_request(self, job_config):
        job_config.TASKS_MODE = "cloud"
        job_config.INTERNAL_WORKER_TOKEN = ""
        job_config.TASKS_SERVICE_ACCOUNT = "tasks@example.com"
        job_config.TASKS_WORKER_AUDIENCE = "https://service/internal/jobs/run"
        response = self.client.post("/internal/jobs/run", json={
            "matter_id": "matter", "job_id": "job"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
