#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_malaysia_news_from_json as renderer


def fixture_data() -> dict:
    return {
        "counts": {"processed": 1, "selected": 1},
        "failed_sources": [],
        "items": [
            {
                "category": "【生活インパクト】",
                "source": "Example News",
                "published_date": "2026年8月2日",
                "title": "LRT service update affects commuter routes",
                "description": "Rapid KL announced service changes for commuters.",
                "link": "https://example.test/lrt-service",
                "selected_summary": {
                    "conclusion": "正規化済みの結論です。",
                    "what_happened": ["正規化済みの詳細です。"],
                    "life_impact": "正規化済みの影響です。",
                    "next_action": "",
                },
            }
        ],
    }


class PreparedSummaryRendererTest(unittest.TestCase):
    def test_prepared_render_does_not_apply_topic_defaults(self) -> None:
        markdown = renderer.render_prepared(fixture_data())

        self.assertIn("- 結論：正規化済みの結論です。", markdown)
        self.assertIn("- 何が起きた：正規化済みの詳細です。", markdown)
        self.assertNotIn("- 次アクション：", markdown)

    def test_rss_render_keeps_existing_topic_defaults(self) -> None:
        markdown = renderer.render(fixture_data())

        self.assertIn("- 次アクション：", markdown)

    def test_prepared_render_preserves_explicit_next_action(self) -> None:
        data = fixture_data()
        data["items"][0]["selected_summary"]["next_action"] = "公式案内を確認してください。"

        markdown = renderer.render_prepared(data)

        self.assertIn("- 次アクション：公式案内を確認してください。", markdown)


if __name__ == "__main__":
    unittest.main()
