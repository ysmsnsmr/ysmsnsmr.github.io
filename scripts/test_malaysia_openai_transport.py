#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import load_model_profile_registry, resolve_model_profile
from malaysia_openai_transport import build_profile_chat_request_body


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


if __name__ == "__main__":
    unittest.main()
