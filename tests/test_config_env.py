"""Environment handling in config.py."""
import os
import unittest
from unittest.mock import patch

import config


class BlankCredentialsPathTests(unittest.TestCase):
    def test_importing_config_does_not_leave_a_blank_credentials_path(self):
        """`.env` carries `GOOGLE_APPLICATION_CREDENTIALS=` so the variable is
        documented. google-auth reads a present-but-empty value as "an explicit
        credentials file was configured" and fails with `File  was not found.`
        instead of falling back to Application Default Credentials -- which
        breaks every Firestore call, including the user provisioning that
        finishes Google sign-in."""
        value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

        self.assertTrue(
            value is None or value.strip(),
            "a blank GOOGLE_APPLICATION_CREDENTIALS disables Application Default Credentials",
        )

    def test_blank_values_are_removed_from_the_environment(self):
        with patch.dict(os.environ, {"CASECLOSED_TEST_BLANK": "   "}, clear=False):
            config._drop_blank_env("CASECLOSED_TEST_BLANK")

            self.assertNotIn("CASECLOSED_TEST_BLANK", os.environ)

    def test_configured_values_are_left_alone(self):
        with patch.dict(os.environ, {"CASECLOSED_TEST_SET": "/keys/sa.json"}, clear=False):
            config._drop_blank_env("CASECLOSED_TEST_SET")

            self.assertEqual(os.environ["CASECLOSED_TEST_SET"], "/keys/sa.json")


class DevServerEnvironmentTests(unittest.TestCase):
    @patch("werkzeug.serving.run_simple")
    def test_dev_server_does_not_reload_dotenv_over_config(self, run_simple):
        """Flask.run() re-reads .env itself, which puts the blank values config.py
        just removed straight back into the environment -- so `python app.py`
        loses Application Default Credentials even though importing the app does
        not."""
        import app as app_module

        app_module.run_dev_server()

        value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.assertTrue(value is None or value.strip())
        run_simple.assert_called_once()


if __name__ == "__main__":
    unittest.main()
