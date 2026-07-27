#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_malaysia_news_with_groq import (
    annotate_json_render_summary_provenance,
    main,
    summary_provenance_observation,
)
from validate_malaysia_groq_merged_candidate import parse_observation_diagnostics


class SummaryProvenanceObservationTest(unittest.TestCase):
    def test_distinguishes_rss_replaced_and_inherited_final_lines(self) -> None:
        original_data = {
            "items": [
                {
                    "selected_summary": {
                        "conclusion": "元の結論です。",
                        "what_happened": ["元の詳細です。", "共通の詳細です。"],
                        "life_impact": "元の影響です。",
                        "next_action": "元の行動です。",
                    }
                },
                {
                    "selected_summary": {
                        "conclusion": "RSSの結論です。",
                        "what_happened": ["RSSの詳細です。"],
                        "life_impact": "RSSの影響です。",
                        "next_action": "",
                    }
                },
            ]
        }
        json_render_data = {
            "items": [
                {
                    "selected_summary": {
                        "conclusion": "元の結論です。",
                        "what_happened": ["Groqの詳細です。", "共通の詳細です。"],
                        "life_impact": "Groqの影響です。",
                        "next_action": "元の行動です。",
                    }
                },
                {
                    "selected_summary": {
                        "conclusion": "安全な汎用結論です。",
                        "what_happened": ["安全な汎用詳細です。"],
                        "life_impact": "安全な汎用影響です。",
                        "next_action": "",
                    }
                },
            ]
        }
        records = [
            {"index": 1, "accepted": True},
            {"index": 2, "accepted": False},
        ]

        annotate_json_render_summary_provenance(original_data, json_render_data, records)

        accepted_origins = [
            line["origin"] for line in records[0]["json_render_summary_line_provenance"]
        ]
        fallback_origins = [
            line["origin"] for line in records[1]["json_render_summary_line_provenance"]
        ]
        self.assertEqual(
            accepted_origins,
            [
                "groq_inherited",
                "groq_replaced",
                "groq_inherited",
                "groq_replaced",
                "groq_inherited",
            ],
        )
        self.assertEqual(fallback_origins, ["rss_derived", "rss_derived", "rss_derived"])

        observation = summary_provenance_observation(records)
        self.assertEqual(
            observation["line_counts"],
            {"rss_derived": 3, "groq_replaced": 2, "groq_inherited": 3},
        )
        self.assertEqual(observation["accepted_item_with_inherited_line_count"], 1)
        self.assertEqual(observation["accepted_item_with_replaced_line_count"], 1)
        self.assertEqual(observation["accepted_item_all_inherited_line_count"], 0)
        self.assertTrue(observation["observation_only"])

    def test_validator_parses_observation_without_creating_a_gate(self) -> None:
        parsed = parse_observation_diagnostics(
            {
                "diagnostics": {
                    "json_render_summary_provenance": {
                        "observation_only": True,
                        "line_counts": {
                            "rss_derived": 3,
                            "groq_replaced": 2,
                            "groq_inherited": 1,
                        },
                        "accepted_item_with_inherited_line_count": 1,
                        "accepted_item_with_replaced_line_count": 1,
                        "accepted_item_all_inherited_line_count": 0,
                    }
                }
            }
        )

        self.assertEqual(parsed["summary_provenance_line_counts"]["groq_replaced"], 2)
        self.assertEqual(parsed["summary_provenance_accepted_item_with_inherited_line_count"], 1)
        self.assertEqual(parsed["summary_provenance_accepted_item_with_replaced_line_count"], 1)
        self.assertEqual(parsed["summary_provenance_accepted_item_all_inherited_line_count"], 0)
        self.assertTrue(parsed["summary_provenance_observation_only"])

    def test_missing_api_key_writes_rss_derived_provenance(self) -> None:
        data = {
            "counts": {"processed": 1, "selected": 1, "failed_sources": []},
            "items": [
                {
                    "category": "【生活インパクト】",
                    "title": "Test item",
                    "description": "Test description",
                    "link": "https://example.test/item",
                    "source": "Example News",
                    "published_date": "2026年7月26日",
                    "selected_summary": {
                        "conclusion": "RSSの結論です。",
                        "what_happened": ["RSSの詳細です。"],
                        "life_impact": "RSSの影響です。",
                        "next_action": "",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "selected.json"
            improved_path = Path(directory) / "improved.json"
            json_render_path = Path(directory) / "candidate.md"
            output_path = Path(directory) / "fallback.md"
            input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            with (
                mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "render_malaysia_news_with_groq.py",
                        "--json-input",
                        str(input_path),
                        "--improved-items-output",
                        str(improved_path),
                        "--json-render-output",
                        str(json_render_path),
                        "--output",
                        str(output_path),
                    ],
                ),
            ):
                self.assertEqual(main(), 0)

            payload = json.loads(improved_path.read_text(encoding="utf-8"))
            provenance = payload["diagnostics"]["json_render_summary_provenance"]
            self.assertGreater(provenance["line_counts"]["rss_derived"], 0)
            self.assertEqual(provenance["line_counts"]["groq_replaced"], 0)
            self.assertEqual(provenance["line_counts"]["groq_inherited"], 0)
            self.assertTrue(provenance["observation_only"])
            self.assertTrue(json_render_path.exists())


if __name__ == "__main__":
    unittest.main()
