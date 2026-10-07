import json
import socket
import unittest
import urllib.error

from src.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
    canonical_sha256_digest,
    sha256_digest_audit,
)


class FakeResponse:
    def __init__(self, document=None, raw=None):
        self.raw = raw if raw is not None else json.dumps(document).encode("utf-8")

    def read(self):
        return self.raw


class OllamaClientTests(unittest.TestCase):
    def test_sha256_prefixed_unprefixed_case_and_whitespace(self):
        digest = "a2" * 32
        self.assertEqual(canonical_sha256_digest(" sha256:" + digest + " "), digest)
        self.assertEqual(canonical_sha256_digest(digest.upper()), digest)
        audit = sha256_digest_audit(digest, "SHA256:" + digest.upper())
        self.assertTrue(audit["digest_match"])

    def test_different_valid_sha256_digest_does_not_match(self):
        audit = sha256_digest_audit("a2" * 32, "b3" * 32)
        self.assertFalse(audit["digest_match"])

    def test_invalid_sha256_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly 64"):
            canonical_sha256_digest("abc")
        with self.assertRaisesRegex(ValueError, "non-hexadecimal"):
            canonical_sha256_digest("g" * 64)
        with self.assertRaisesRegex(ValueError, "Unknown digest algorithm"):
            canonical_sha256_digest("md5:" + "a" * 64)

    def test_success_and_utf8_request(self):
        captured = {}

        def urlopen(request, timeout):
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return FakeResponse({"response": '{"answer":"မြန်မာစာ"}'})

        client = OllamaClient(timeout_seconds=321, urlopen=urlopen)
        schema = {"type": "object", "properties": {"page": {"type": "integer"}}}
        response = client.generate("မြန်မာ MIX question", {"temperature": 0}, schema)
        payload = json.loads(captured["body"])
        self.assertEqual(payload["prompt"], "မြန်မာ MIX question")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"], schema)
        self.assertEqual(captured["timeout"], 321)
        self.assertIn("မြန်မာစာ", response["response"])

    def test_timeout(self):
        def urlopen(request, timeout):
            raise socket.timeout()

        with self.assertRaises(OllamaTimeoutError):
            OllamaClient(urlopen=urlopen).version()

    def test_connection_failure(self):
        def urlopen(request, timeout):
            raise urllib.error.URLError("offline")

        with self.assertRaises(OllamaConnectionError):
            OllamaClient(urlopen=urlopen).version()

    def test_malformed_response(self):
        def urlopen(request, timeout):
            return FakeResponse(raw=b"not-json")

        with self.assertRaises(OllamaResponseError):
            OllamaClient(urlopen=urlopen).version()


if __name__ == "__main__":
    unittest.main()
