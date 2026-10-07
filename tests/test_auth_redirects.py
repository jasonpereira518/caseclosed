import unittest

from app import app
from routes.auth import _safe_next


class SafeNextTests(unittest.TestCase):
    """Regression guard for the open redirect in _safe_next.

    urlparse reports '/\\evil.com' as a relative path with no netloc, but
    browsers normalize the backslash and land on https://evil.com. The value
    is reflected into data-next and can reach window.location.assign().
    """

    CROSS_ORIGIN_PROBES = [
        "//evil.example",
        "/\\evil.example",
        "/\\\\evil.example",
        "/\t\\evil.example",
        "/\t/evil.example",
        " //evil.example",
        "https://evil.example",
        "javascript:alert(1)",
        "http:/evil.example",
    ]

    def test_cross_origin_destinations_fall_back_to_the_workspace(self):
        with app.test_request_context("/auth/login"):
            for probe in self.CROSS_ORIGIN_PROBES:
                with self.subTest(probe=probe):
                    self.assertEqual(
                        _safe_next(probe), "/app", f"{probe!r} escaped the origin"
                    )

    def test_same_origin_paths_are_preserved(self):
        with app.test_request_context("/auth/login"):
            for value in ("/app", "/account", "/app?matter=abc#tab", "/%5Cevil.example"):
                with self.subTest(value=value):
                    self.assertEqual(_safe_next(value), value)

    def test_missing_values_fall_back(self):
        with app.test_request_context("/auth/login"):
            self.assertEqual(_safe_next(None), "/app")
            self.assertEqual(_safe_next(""), "/app")



class LoginErrorTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_rejected_session_at_complete_reports_instead_of_looping(self):
        response = self.client.get("/auth/complete?next=/account&invite=tok")

        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertIn("/auth/login?", location)
        self.assertIn("error=session", location)
        self.assertIn("next=/account", location)
        self.assertIn("invite=tok", location)

    def test_error_param_selects_fixed_copy_never_raw_text(self):
        body = self.client.get("/auth/login?error=Call+555-0100+for+support").get_data(as_text=True)

        self.assertNotIn("555-0100", body)
        self.assertIn("Sign-in didn&#39;t complete", body)


if __name__ == "__main__":
    unittest.main()
