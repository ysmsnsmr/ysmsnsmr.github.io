#!/usr/bin/env python3
import sys
import unittest
import json
from unittest.mock import patch
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import load_model_profile_registry, resolve_model_profile
from malaysia_openai_transport import (
    OpenAITransportValueError,
    build_profile_chat_request_body,
    request_chat_completion,
)


class OpenAIRequestSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.luna = resolve_model_profile("gpt-6-luna", load_model_profile_registry())

    def test_luna_profile_builds_openai_supported_request(self) -> None:
        body = build_profile_chat_request_body(
            profile=self.luna,
            messages=[{"role": "user", "content": "test"}],
            json_schema_name="malaysia_news_editorial_entry_v4",
            json_schema={"type": "object", "properties": {}, "additionalProperties": False},
        )

        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["reasoning_effort"], "medium")
        self.assertEqual(body["max_completion_tokens"], 800)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertNotIn("temperature", body)
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("reasoning_format", body)
        self.assertNotIn("include_reasoning", body)

    def test_repair_can_use_smaller_completion_budget(self) -> None:
        body = build_profile_chat_request_body(
            profile=self.luna,
            messages=[{"role": "user", "content": "repair"}],
            max_completion_tokens=320,
            json_schema_name="malaysia_news_editorial_entry_v4",
            json_schema={"type": "object"},
        )
        self.assertEqual(body["max_completion_tokens"], 320)
        self.assertEqual(body["reasoning_effort"], "medium")

    def test_groq_profile_is_rejected_by_openai_transport(self) -> None:
        groq = resolve_model_profile("gpt-oss-120b", load_model_profile_registry())
        with self.assertRaisesRegex(ValueError, "OpenAI model profile"):
            build_profile_chat_request_body(
                profile=groq,
                messages=[],
                json_schema_name="contract",
                json_schema={"type": "object"},
            )

    def test_empty_truncated_response_records_effective_profile_and_failure_class(self) -> None:
        payload = {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55},
        }

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size=-1):
                return json.dumps(payload).encode()

            def getcode(self):
                return 200

        with patch("malaysia_openai_transport.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(OpenAITransportValueError) as caught:
                request_chat_completion(
                    profile=self.luna,
                    messages=[{"role": "user", "content": "test"}],
                    api_key="test-key",
                    json_schema_name="malaysia_news_editorial_entry_v4",
                    json_schema={"type": "object"},
                    schema_error=lambda _value: "",
                )

        diagnostic = caught.exception.openai_diagnostic
        self.assertEqual(diagnostic["provider"], "openai")
        self.assertEqual(diagnostic["model"], "gpt-6-luna")
        self.assertEqual(diagnostic["reasoning_effort"], "medium")
        self.assertEqual(diagnostic["finish_reason"], "length")
        self.assertEqual(diagnostic["json_contract_status"], "truncated")
        self.assertEqual(diagnostic["failure_class"], "truncated_output")
        self.assertEqual(diagnostic["usage"]["total_tokens"], 55)


if __name__ == "__main__":
    unittest.main()
