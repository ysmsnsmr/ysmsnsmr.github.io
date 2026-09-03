#!/usr/bin/env python3
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import load_model_profile_registry, resolve_model_profile
from malaysia_groq_output_contract import EDITORIAL_ENTRY_V3_SCHEMA, editorial_entry_schema_error
from malaysia_groq_transport import build_chat_request_body, error_diagnostic, request_chat_completion


class FakeResponse:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload

    def getcode(self) -> int:
        return 200


VALID = {
    "editorial_entry": {
        "headline_ja": "窓口を来月開設",
        "short_headline_ja": "窓口を来月開設",
        "entry_ja": "省庁は来月の窓口開設を計画していると発表しました。",
        "supporting_points_ja": ["開始時期は来月とされています。"],
    }
}


class GroqTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_model_profile_registry()

    def request(self, profile_name: str):
        return request_chat_completion(
            profile=resolve_model_profile(profile_name, self.registry),
            messages=[{"role": "user", "content": "fixture"}],
            temperature=0.0,
            max_tokens=500,
            timeout_seconds=1,
            max_response_chars=4000,
            json_schema_name="editorial_entry_v3",
            json_schema=EDITORIAL_ENTRY_V3_SCHEMA,
            schema_error=editorial_entry_schema_error,
            api_key="test-key",
        )

    def test_profiles_build_expected_transport_payloads(self) -> None:
        messages = [{"role": "user", "content": "fixture"}]
        llama = build_chat_request_body(resolve_model_profile("llama", self.registry), messages, 0.2, 500)
        gpt = build_chat_request_body(
            resolve_model_profile("gpt-oss", self.registry),
            messages,
            0.2,
            500,
            "editorial_entry_v3",
            EDITORIAL_ENTRY_V3_SCHEMA,
        )
        qwen = build_chat_request_body(resolve_model_profile("qwen36", self.registry), messages, 0.2, 500)

        self.assertEqual(llama["response_format"], {"type": "json_object"})
        self.assertNotIn("reasoning_format", llama)
        self.assertEqual(gpt["response_format"]["type"], "json_schema")
        self.assertTrue(gpt["response_format"]["json_schema"]["strict"])
        self.assertEqual(gpt["reasoning_effort"], "low")
        self.assertEqual(qwen["response_format"], {"type": "json_object"})
        self.assertEqual(qwen["reasoning_format"], "hidden")

    def test_success_and_contract_states_are_recorded(self) -> None:
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(VALID)}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}
        with patch("malaysia_groq_transport.urllib.request.urlopen", return_value=FakeResponse(payload, {"x-ratelimit-reset-tokens": "2s"})):
            completion = self.request("gpt-oss")

        self.assertEqual(completion.diagnostic["transport_status"], "success")
        self.assertEqual(completion.diagnostic["json_contract_status"], "valid")
        self.assertEqual(completion.diagnostic["usage"]["total_tokens"], 7)

    def test_http_error_is_sanitized_without_failed_generation_content(self) -> None:
        response = io.BytesIO(json.dumps({"error": {"type": "invalid_request_error", "code": "bad_schema", "message": "x" * 700, "failed_generation": "secret generated text"}}).encode("utf-8"))
        error = urllib.error.HTTPError("https://example.test", 400, "Bad Request", {"x-ratelimit-reset-tokens": "2s"}, response)
        with patch("malaysia_groq_transport.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request("qwen36")

        diagnostic = error_diagnostic(raised.exception)
        self.assertEqual(diagnostic["transport_status"], "http_error")
        self.assertEqual(diagnostic["error"]["code"], "bad_schema")
        self.assertEqual(len(diagnostic["error"]["message"]), 500)
        self.assertTrue(diagnostic["error"]["failed_generation_present"])
        self.assertNotIn("secret generated text", json.dumps(diagnostic))

    def test_empty_truncated_and_invalid_json_are_separate(self) -> None:
        cases = [
            ({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}, "empty"),
            ({"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}, "truncated"),
            ({"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]}, "invalid_json"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected), patch(
                "malaysia_groq_transport.urllib.request.urlopen", return_value=FakeResponse(payload)
            ):
                with self.assertRaises(ValueError) as raised:
                    self.request("qwen36")
                diagnostic = error_diagnostic(raised.exception)
                self.assertEqual(diagnostic["transport_status"], "success")
                self.assertEqual(diagnostic["json_contract_status"], expected)

    def test_strict_schema_rejects_shape_mismatch(self) -> None:
        payload = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"editorial_entry": {}})}}]
        }
        with patch("malaysia_groq_transport.urllib.request.urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(ValueError) as raised:
                self.request("gpt-oss")

        diagnostic = error_diagnostic(raised.exception)
        self.assertEqual(diagnostic["transport_status"], "success")
        self.assertEqual(diagnostic["json_contract_status"], "schema_invalid")
        self.assertEqual(diagnostic["json_contract_reason"], "editorial_entry_shape")

    def test_strict_schema_records_empty_headline_reason(self) -> None:
        payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "editorial_entry": {
                                "headline_ja": "",
                                "short_headline_ja": "短見出し",
                                    "entry_ja": "概要",
                                    "supporting_points_ja": [],
                                }
                            }
                        )
                    },
                }
            ]
        }
        with patch("malaysia_groq_transport.urllib.request.urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(ValueError) as raised:
                self.request("gpt-oss")

        diagnostic = error_diagnostic(raised.exception)
        self.assertEqual(diagnostic["transport_status"], "success")
        self.assertEqual(diagnostic["json_contract_status"], "schema_invalid")
        self.assertEqual(diagnostic["json_contract_reason"], "editorial_headline_empty")


if __name__ == "__main__":
    unittest.main()
