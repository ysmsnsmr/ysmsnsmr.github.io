from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from meta_ads_groq_schema_probe import request_schema_probe


class _Response:
    def __init__(self, content: dict[str, str]) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return json.dumps({"choices": [{"message": {"content": json.dumps(self.content)}}]}).encode("utf-8")


class GroqSchemaProbeTest(unittest.TestCase):
    @patch("meta_ads_groq_schema_probe.urllib.request.urlopen")
    def test_one_field_probe_sends_exact_strict_contract(self, urlopen) -> None:
        urlopen.return_value = _Response({"shortHeadlineEn": "Schema probe passed"})
        result = request_schema_probe(api_key="test-key", model="test-model", field_count=1)
        self.assertEqual(result, {"fieldCount": 1, "fields": ["shortHeadlineEn"]})
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        schema = payload["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertEqual(schema["schema"]["required"], ["shortHeadlineEn"])
        self.assertEqual(set(schema["schema"]["properties"]), {"shortHeadlineEn"})
        self.assertEqual(schema["schema"]["properties"]["shortHeadlineEn"], {"type": "string"})

    @patch("meta_ads_groq_schema_probe.urllib.request.urlopen")
    def test_two_field_probe_accepts_bounded_python_validation(self, urlopen) -> None:
        urlopen.return_value = _Response({"shortHeadlineEn": "Headline", "summaryEn": "Summary"})
        result = request_schema_probe(api_key="test-key", model="test-model", field_count=2)
        self.assertEqual(result["fields"], ["shortHeadlineEn", "summaryEn"])

    @patch("meta_ads_groq_schema_probe.urllib.request.urlopen")
    def test_probe_exposes_only_safe_provider_labels_on_failure(self, urlopen) -> None:
        body = json.dumps(
            {
                "error": {
                    "message": "do not print this body",
                    "type": "invalid_request_error",
                    "code": "json_validate_failed",
                }
            }
        ).encode("utf-8")
        urlopen.side_effect = HTTPError("https://api.groq.com/openai/v1/chat/completions", 400, "bad request", {}, io.BytesIO(body))
        with self.assertRaisesRegex(Exception, "http_400") as raised:
            request_schema_probe(api_key="test-key", model="test-model", field_count=1)
        error = raised.exception
        self.assertEqual(getattr(error, "provider_error_type"), "invalid_request_error")
        self.assertEqual(getattr(error, "provider_error_code"), "json_validate_failed")
        self.assertNotIn("do not print", str(error))


if __name__ == "__main__":
    unittest.main()
