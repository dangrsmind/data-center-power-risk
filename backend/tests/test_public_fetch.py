from __future__ import annotations

import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.public_fetch import PublicFetchClient  # noqa: E402


class FakeHeaders:
    def __init__(self, content_type: str):
        self.content_type = content_type

    def get(self, name: str, default=None):
        return self.content_type if name == "Content-Type" else default


class FakeResponse:
    status = 200
    headers = FakeHeaders("text/html; charset=utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return 200

    def geturl(self):
        return "https://example.test/final"

    def read(self, _max_bytes: int):
        return b"<html><title>OK</title><body>hello</body></html>"


class PublicFetchClientTest(unittest.TestCase):
    def test_successful_text_response_has_content_hash(self) -> None:
        with patch("app.services.public_fetch.request.urlopen", return_value=FakeResponse()):
            result = PublicFetchClient(max_retries=0).fetch("https://example.test/")

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content_type, "text/html; charset=utf-8")
        self.assertIsNotNone(result.content_hash)
        self.assertIn("hello", result.text or "")

    def test_ssl_failure_returns_structured_result(self) -> None:
        ssl_error = ssl.SSLError("certificate verify failed")
        with patch("app.services.public_fetch.request.urlopen", side_effect=URLError(ssl_error)):
            result = PublicFetchClient(max_retries=0).fetch("https://bad-cert.example.test/")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "ssl_certificate_error")
        self.assertIn("certificate verify failed", result.error_message or "")

    def test_insecure_fetch_is_off_by_default(self) -> None:
        self.assertFalse(PublicFetchClient().allow_insecure_fetch)
        self.assertTrue(PublicFetchClient(allow_insecure_fetch=True).allow_insecure_fetch)


if __name__ == "__main__":
    unittest.main()
