import unittest

from app import app
from routes.auth import _safe_next


class SafeNextTests(unittest.TestCase):
    """Regression guard for the open redirect in _safe_next.

    urlparse reports '/\\evil.com' as a relative path with no netloc, but
    browsers normalize the backslash and land on https://evil.com. The value
    reaches window.location.assign() via static/firebase_auth.js.
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


if __name__ == "__main__":
    unittest.main()
