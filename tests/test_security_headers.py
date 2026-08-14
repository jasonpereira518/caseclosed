import unittest

from app import app


class SecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_baseline_headers_on_every_response(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            response.headers["Referrer-Policy"], "strict-origin-when-cross-origin"
        )
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn(
            "frame-ancestors 'self'", response.headers["Content-Security-Policy"]
        )

    def test_csp_is_report_only_so_a_wrong_policy_cannot_break_sign_in(self):
        """The enforcing policy must never constrain script loading.

        Clerk's SDK host is derived at runtime from the publishable key; an
        enforcing script-src that is wrong locks every user out of sign-in with
        no recovery short of a redeploy.
        """
        response = self.client.get("/auth/login")
        self.assertNotIn("script-src", response.headers["Content-Security-Policy"])
        self.assertIn(
            "script-src", response.headers["Content-Security-Policy-Report-Only"]
        )

    def test_demo_route_headers_are_neither_clobbered_nor_duplicated(self):
        response = self.client.get("/demo")
        self.assertEqual(
            response.headers.getlist("Content-Security-Policy"),
            ["frame-ancestors 'self'"],
        )
        self.assertEqual(response.headers.getlist("X-Frame-Options"), ["SAMEORIGIN"])
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")

    def test_hsts_is_sent_only_over_https(self):
        self.assertNotIn("Strict-Transport-Security", self.client.get("/").headers)
        secure = self.client.get("/", headers={"X-Forwarded-Proto": "https"})
        self.assertIn("max-age=", secure.headers["Strict-Transport-Security"])
        self.assertIn("includeSubDomains", secure.headers["Strict-Transport-Security"])

    def test_session_cookie_is_hardened(self):
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")


if __name__ == "__main__":
    unittest.main()
