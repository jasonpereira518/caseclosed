"""Public legal pages: privacy policy and terms of service."""
import unittest

from app import app


class LegalPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_privacy_policy_is_public(self):
        response = self.client.get("/privacy")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Privacy Policy", response.data)
        self.assertIn(b"Google", response.data)

    def test_terms_of_service_are_public(self):
        response = self.client.get("/terms")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Terms of Service", response.data)
        self.assertIn(b"legal advice", response.data)

    def test_landing_footer_links_both_pages(self):
        response = self.client.get("/")

        self.assertIn(b'href="/privacy"', response.data)
        self.assertIn(b'href="/terms"', response.data)

    def test_legal_pages_do_not_load_the_workspace_script(self):
        for path in ("/privacy", "/terms"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotIn(b"/static/script.js", response.data)


if __name__ == "__main__":
    unittest.main()
