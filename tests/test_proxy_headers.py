import unittest

from app import app


class ProxyHeaderTests(unittest.TestCase):
    """Cloud Run terminates TLS and speaks plain HTTP to the container.

    Without ProxyFix, url_for(..., _external=True) in templates/landing_base.html
    advertises http:// for og:url and rel=canonical on an https-only domain.
    """

    def setUp(self):
        # tests/test_landing_routes.py sets SERVER_NAME on the shared module-level
        # app object and it leaks across test modules. SERVER_NAME overrides the
        # request Host in url_for(_external=True), which is exactly what these
        # tests assert on, so neutralize it here and restore it afterwards.
        self._server_name = app.config.get("SERVER_NAME")
        app.config.update(TESTING=True, SERVER_NAME=None)
        self.client = app.test_client()

    def tearDown(self):
        app.config["SERVER_NAME"] = self._server_name

    def test_external_urls_use_https_behind_the_cloud_run_front_end(self):
        response = self.client.get(
            "/",
            headers={
                "X-Forwarded-Proto": "https",
                "Host": "caseclosed.jasonpereira.live",
            },
        )
        body = response.get_data(as_text=True)
        self.assertIn('href="https://caseclosed.jasonpereira.live/"', body)
        self.assertNotIn("http://caseclosed.jasonpereira.live", body)

    def test_forwarded_host_is_not_trusted(self):
        """Cloud Run does not set X-Forwarded-Host; it passes the real Host
        through. Honoring the header would let any client forge our hostname."""
        response = self.client.get(
            "/",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "evil.example",
                "Host": "caseclosed.jasonpereira.live",
            },
        )
        self.assertNotIn("evil.example", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
