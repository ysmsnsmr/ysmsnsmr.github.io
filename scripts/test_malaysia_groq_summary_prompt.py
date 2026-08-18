#!/usr/bin/env python3
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_malaysia_news_with_groq import (
    SYSTEM_PROMPT,
    SUMMARY_ONLY_CONTRACT_INSTRUCTION,
    USER_MESSAGE_JSON_CONTRACT,
    groq_payload_for_item,
    request_groq_summary,
    summary_request_messages,
)
from malaysia_groq_output_contract import SUMMARY_ONLY_SCHEMA, summary_only_schema_error
from malaysia_groq_transport import ChatCompletion


class SummaryPromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.item = {
            "title": "Agency says a transit plan will begin next month",
            "description": "The agency said the plan is expected to begin in September.",
            "selected_summary": {
                "conclusion": "既存要約",
                "what_happened": ["既存の事実"],
                "life_impact": "既存の背景",
                "next_action": "",
            },
        }

    def test_production_layout_preserves_existing_system_and_user_messages(self) -> None:
        self.assertEqual(
            summary_request_messages(self.item),
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(groq_payload_for_item(self.item), ensure_ascii=False),
                },
            ],
        )

    def test_user_only_layout_moves_existing_instruction_without_changing_its_text(self) -> None:
        messages = summary_request_messages(self.item, "user_only")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertTrue(messages[0]["content"].startswith(SYSTEM_PROMPT))
        self.assertIn("入力記事JSON:", messages[0]["content"])
        self.assertIn(self.item["title"], messages[0]["content"])

    def test_explicit_contract_layout_adds_json_shape_to_the_user_message(self) -> None:
        messages = summary_request_messages(self.item, "user_only_explicit_contract")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn(USER_MESSAGE_JSON_CONTRACT, messages[0]["content"])
        self.assertIn('"selected_summary"', messages[0]["content"])
        self.assertIn('"attribution"', messages[0]["content"])
        self.assertIn(self.item["title"], messages[0]["content"])

    def test_unknown_layout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported summary prompt layout"):
            summary_request_messages(self.item, "not-a-layout")

    def test_summary_only_layout_explicitly_removes_entry_from_the_candidate_contract(self) -> None:
        messages = summary_request_messages(self.item, "user_only", "summary_only")

        self.assertEqual([message["role"] for message in messages], ["user"])
        self.assertIn(SUMMARY_ONLY_CONTRACT_INSTRUCTION, messages[0]["content"])
        self.assertIn("空文字列", messages[0]["content"])
        self.assertIn('"selected_summary"', messages[0]["content"])
        self.assertIn('"entry"', SYSTEM_PROMPT)

    def test_summary_only_request_uses_only_summary_schema_and_does_not_request_entry(self) -> None:
        parsed = {
            "selected_summary": {
                "conclusion": "交通計画を検討",
                "what_happened": ["当局が計画を検討すると述べた"],
                "life_impact": "今後の運行情報を確認する必要があります。",
                "next_action": "詳細は出典本文を確認してください。",
            }
        }
        diagnostic = {"transport_status": "success", "json_contract_status": "valid"}
        with patch(
            "render_malaysia_news_with_groq.request_chat_completion",
            return_value=ChatCompletion("{}", parsed, diagnostic),
        ) as request_mock, patch(
            "render_malaysia_news_with_groq.validate_summary_against_source"
        ):
            result = request_groq_summary(
                self.item,
                "test-key",
                "openai/gpt-oss-120b",
                model_profile=None,
                summary_prompt_layout="user_only",
                summary_max_tokens=800,
                summary_contract="summary_only",
            )

        request = request_mock.call_args.kwargs
        self.assertEqual(request["json_schema"], SUMMARY_ONLY_SCHEMA)
        self.assertEqual(request["max_tokens"], 800)
        self.assertEqual(result.entry_contract_status, "not_requested")
        self.assertIsNone(result.entry)
        self.assertEqual(summary_only_schema_error(parsed), "")
        self.assertEqual(summary_only_schema_error({"selected_summary": parsed["selected_summary"], "entry": {}}), "root_shape")


if __name__ == "__main__":
    unittest.main()
