"""Cycle 13: TTL-ready terminal jobs."""
import datetime
import unittest
from unittest.mock import MagicMock, patch


class TerminalStampTests(unittest.TestCase):
    def _update(self, changes):
        from services import jobs

        ref = MagicMock()
        moment = datetime.datetime(2026, 8, 18, tzinfo=datetime.timezone.utc)
        with patch.object(jobs, "now", return_value=moment):
            data = jobs._update(ref, {}, changes)
        return data, moment

    def test_succeeded_jobs_get_an_expiry(self):
        data, moment = self._update({"status": "succeeded"})
        self.assertEqual(data["expires_at"], moment + datetime.timedelta(days=30))
        self.assertEqual(data["finished_at"], moment)

    def test_failed_and_cancelled_get_one_too(self):
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                data, moment = self._update({"status": status})
                self.assertEqual(data["expires_at"],
                                 moment + datetime.timedelta(days=30))

    def test_running_jobs_do_not_expire(self):
        data, _ = self._update({"status": "running", "progress": 40})
        self.assertNotIn("expires_at", data)

    def test_expiry_never_leaks_into_the_public_payload(self):
        from services import jobs

        data = {"status": "succeeded", "expires_at": "2026-09-17", "progress": 100}
        public = jobs._public(data, "j1", "m1")
        self.assertNotIn("expires_at", public)


if __name__ == "__main__":
    unittest.main()
