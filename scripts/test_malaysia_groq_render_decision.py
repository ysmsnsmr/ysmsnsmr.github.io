#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_render_decision import (
    ENTRY_TIER_ENTRY_CANDIDATE,
    JSON_TIER_ACCEPTED,
    JSON_TIER_GENERIC_FALLBACK,
    JSON_TIER_TOPIC_FALLBACK,
    annotate_decision_records,
    apply_entry_render_decisions,
    apply_json_render_decisions,
    build_render_decisions,
)


def item(link: str, summary: dict | None = None) -> dict:
    return {
        "category": "【生活インパクト】",
        "source": "Example News",
        "published_date": "2026年8月2日",
        "title": "Example item",
        "description": "Example description",
        "link": link,
        "selected_summary": summary or {
            "conclusion": "RSSの結論です。",
            "what_happened": ["RSSの詳細です。"],
            "life_impact": "RSSの影響です。",
            "next_action": "",
        },
    }


class RenderDecisionTest(unittest.TestCase):
    def test_finalizes_json_and_entry_tiers_once(self) -> None:
        items = [
            item("https://example.test/accepted", {
                "conclusion": "Groqの結論です。",
                "what_happened": ["Groqの詳細です。"],
                "life_impact": "Groqの影響です。",
                "next_action": "確認してください。",
            }),
            item("https://example.test/topic"),
            item("https://example.test/entry"),
        ]
        records = [
            {"index": 1, "link": items[0]["link"], "accepted": True},
            {"index": 2, "link": items[1]["link"], "accepted": False},
            {
                "index": 3,
                "link": items[2]["link"],
                "accepted": False,
                "entry_candidate_status": "full_rejected",
                "entry": {"text_ja": "入口文です。"},
            },
        ]
        topic_calls: list[str] = []
        fallback_topics: list[str] = []

        def fallback_topic_for_item(value: dict) -> str:
            topic_calls.append(value["link"])
            return "currency" if value["link"].endswith("topic") else ""

        def fallback_summary_for_item(value: dict, topic: str | None) -> dict:
            fallback_topics.append(topic or "generic")
            return {
                "conclusion": f"{topic or 'generic'}の結論です。",
                "what_happened": [f"{topic or 'generic'}の詳細です。"],
                "life_impact": f"{topic or 'generic'}の影響です。",
                "next_action": "",
            }

        decisions = build_render_decisions(
            items,
            records,
            fallback_summary_for_item,
            fallback_topic_for_item,
        )

        self.assertEqual([decision.json_tier for decision in decisions], [
            JSON_TIER_ACCEPTED,
            JSON_TIER_TOPIC_FALLBACK,
            JSON_TIER_GENERIC_FALLBACK,
        ])
        self.assertEqual([decision.entry_tier for decision in decisions], [
            JSON_TIER_ACCEPTED,
            JSON_TIER_TOPIC_FALLBACK,
            ENTRY_TIER_ENTRY_CANDIDATE,
        ])
        self.assertEqual(topic_calls, [items[1]["link"], items[2]["link"]])
        self.assertEqual(fallback_topics, ["currency", "generic"])

        json_data = apply_json_render_decisions({"items": items}, decisions)
        entry_data = apply_entry_render_decisions({"items": items}, decisions)
        self.assertEqual(json_data["items"][1]["selected_summary"]["conclusion"], "currencyの結論です。")
        self.assertEqual(json_data["items"][2]["selected_summary"]["conclusion"], "genericの結論です。")
        self.assertEqual(entry_data["items"][2]["selected_summary"]["conclusion"], "入口文です。")

        annotate_decision_records(records, decisions)
        self.assertEqual(records[0]["json_render_fallback_kind"], "accepted")
        self.assertEqual(records[1]["json_render_fallback_topic"], "currency")
        self.assertEqual(records[2]["json_render_fallback_kind"], "generic")
        self.assertEqual(records[2]["entry_render_tier"], "entry_candidate")

    def test_ignores_record_with_a_different_link(self) -> None:
        items = [item("https://example.test/item")]
        records = [{"index": 1, "link": "https://example.test/other", "accepted": True}]

        decisions = build_render_decisions(
            items,
            records,
            lambda _item, _topic: {
                "conclusion": "安全な結論です。",
                "what_happened": ["安全な詳細です。"],
                "life_impact": "安全な影響です。",
                "next_action": "",
            },
            lambda _item: "",
        )

        self.assertEqual(decisions[0].json_tier, JSON_TIER_GENERIC_FALLBACK)
        annotate_decision_records(records, decisions)
        self.assertNotIn("json_render_fallback_kind", records[0])


if __name__ == "__main__":
    unittest.main()
