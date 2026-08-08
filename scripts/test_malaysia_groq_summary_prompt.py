#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_malaysia_news_with_groq import (
    SYSTEM_PROMPT,
    USER_MESSAGE_JSON_CONTRACT,
    groq_payload_for_item,
    summary_request_messages,
)


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


if __name__ == "__main__":
    unittest.main()
