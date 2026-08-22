#!/usr/bin/env python3
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_malaysia_news_from_json as markdown_renderer
import render_malaysia_news_with_groq as groq_renderer
from malaysia_groq_output_contract import EDITORIAL_ENTRY_V2_SCHEMA, editorial_entry_schema_error
from malaysia_groq_force_all_policy import force_all_request_cap
from malaysia_groq_render_decision import (
    annotate_decision_records,
    apply_render_decisions,
    build_render_decisions,
    provenance_observation,
    validated_rss_fallback_editorial_entry,
)
from malaysia_groq_transport import ChatCompletion
from validate_malaysia_groq_merged_candidate import validate_candidate


def item(index: int = 1) -> dict:
    return {
        "category": "【生活インパクト】",
        "source": "Example News",
        "published_date": "2026年8月18日",
        "title": f"Agency says transit plan {index} will begin next month",
        "description": "The agency said the plan is expected to begin in September.",
        "link": f"https://example.test/{index}",
        "selected_summary": {
            "conclusion": f"RSS結論{index}",
            "what_happened": [f"RSS補足{index}"],
            "life_impact": "旧形式の影響",
            "next_action": "旧形式の行動",
        },
        "editorial_entry": {
            "entry_ja": f"RSS概要{index}",
            "supporting_points_ja": [f"RSS補足{index}"],
        },
    }


def accepted_result(index: int) -> groq_renderer.GroqEditorialEntryResult:
    return groq_renderer.GroqEditorialEntryResult(
        {
            "entry_ja": f"当局は計画{index}を来月開始する見通しだと述べました。",
            "supporting_points_ja": [f"開始時期は9月とされています。"],
        },
        {"transport_status": "success", "json_contract_status": "valid"},
    )


class EditorialEntryV2Test(unittest.TestCase):
    def test_strict_contract_accepts_zero_or_two_points_and_rejects_legacy_shape(self) -> None:
        self.assertEqual(
            editorial_entry_schema_error(
                {"editorial_entry": {"entry_ja": "概要です。", "supporting_points_ja": []}}
            ),
            "",
        )
        self.assertEqual(
            editorial_entry_schema_error(
                {
                    "editorial_entry": {
                        "entry_ja": "概要です。",
                        "supporting_points_ja": ["補足1", "補足2"],
                    }
                }
            ),
            "",
        )
        self.assertEqual(
            editorial_entry_schema_error(
                {"selected_summary": {"conclusion": "旧形式"}}
            ),
            "root_shape",
        )
        self.assertEqual(
            editorial_entry_schema_error(
                {"editorial_entry": {"entry_ja": "", "supporting_points_ja": [], "extra": "x"}}
            ),
            "editorial_entry_shape",
        )
        self.assertEqual(EDITORIAL_ENTRY_V2_SCHEMA["required"], ["editorial_entry"])

    def test_article_fallback_is_a_valid_v2_object(self) -> None:
        self.assertEqual(
            editorial_entry_schema_error({"editorial_entry": validated_rss_fallback_editorial_entry()}),
            "",
        )

    def test_v2_markdown_has_only_overview_and_supporting_points(self) -> None:
        data = {"counts": {"processed": 1, "selected": 1}, "failed_sources": [], "items": [item()]}
        markdown = markdown_renderer.render_editorial_entries(data)
        self.assertIn("- 概要：RSS概要1", markdown)
        self.assertIn("- 補足：RSS補足1", markdown)
        self.assertNotIn("- 結論：", markdown)
        self.assertNotIn("- 生活への影響：", markdown)
        self.assertNotIn("- 次アクション：", markdown)

    def test_legacy_summary_conversion_drops_generic_supporting_point(self) -> None:
        legacy = item()
        legacy.pop("editorial_entry")
        legacy["selected_summary"]["what_happened"] = [
            "記事本文にある補足です。",
            "RSS内のタイトルと説明をもとに整理しました。",
        ]
        entry = markdown_renderer.normalize_editorial_entry(legacy)
        self.assertEqual(entry["supporting_points_ja"], ["記事本文にある補足です。"])

    def test_request_uses_v2_schema_and_user_only_contract(self) -> None:
        parsed = {
            "editorial_entry": {
                "entry_ja": "当局は来月の交通計画開始を見込むと述べました。",
                "supporting_points_ja": ["開始時期は9月です。"],
            }
        }
        with patch(
            "render_malaysia_news_with_groq.request_chat_completion",
            return_value=ChatCompletion("{}", parsed, {"transport_status": "success", "json_contract_status": "valid"}),
        ) as request:
            result = groq_renderer.request_groq_summary(
                item(), "key", "openai/gpt-oss-120b",
                summary_prompt_layout="user_only",
                summary_max_tokens=800,
                summary_contract="editorial_entry_v2",
            )
        self.assertEqual(result.editorial_entry["entry_ja"], parsed["editorial_entry"]["entry_ja"])
        self.assertEqual(request.call_args.kwargs["json_schema"], EDITORIAL_ENTRY_V2_SCHEMA)
        self.assertEqual(request.call_args.kwargs["json_schema_name"], "malaysia_news_editorial_entry_v2")
        messages = groq_renderer.summary_request_messages(item(), "user_only")
        self.assertEqual([message["role"] for message in messages], ["user"])
        self.assertIn('"editorial_entry"', messages[0]["content"])
        self.assertNotIn('"selected_summary"', messages[0]["content"])

    def test_request_cap_is_first_twelve_in_selected_order_without_lexical_exclusions(self) -> None:
        data = {"items": [item(index) for index in range(1, 14)]}
        data["items"][0]["title"] = "Financial market article"
        data["items"][1]["title"] = "Paul Tan transport article"
        data["items"][2]["title"] = "Incident report article"
        with patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry",
            side_effect=[accepted_result(index) for index in range(1, 13)],
        ) as request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(
                data, "key", "test-model"
            )
        self.assertEqual(request.call_count, 12)
        self.assertEqual(stats, {"requested": 12, "accepted": 12, "fallback": 0})
        self.assertEqual(len(accepted), 12)
        self.assertEqual(
            [call.args[0]["link"] for call in request.call_args_list],
            [f"https://example.test/{index}" for index in range(1, 13)],
        )
        self.assertEqual(records[-1]["reason"], "request_cap")
        self.assertEqual(rendered["items"][12]["editorial_entry"]["entry_ja"], "RSS概要13")

    def test_request_cap_keeps_the_existing_environment_override_name(self) -> None:
        with patch.dict(os.environ, {"MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP": "7"}, clear=False):
            self.assertEqual(force_all_request_cap(), 7)

    def test_hard_safety_rejection_uses_validated_v2_fallback_and_records_reason(self) -> None:
        data = {"items": [item()]}
        rejection = groq_renderer.GroqEditorialEntryRejected(
            "unsupported accident claim",
            {"transport_status": "success", "json_contract_status": "valid"},
        )
        with patch("render_malaysia_news_with_groq.request_groq_summary_with_retry", side_effect=rejection):
            rendered, _, stats, records = groq_renderer.render_with_groq(data, "key", "test-model")
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        annotate_decision_records(data, final, records, decisions)
        self.assertEqual(stats["fallback"], 1)
        self.assertEqual(
            final["items"][0]["editorial_entry"],
            validated_rss_fallback_editorial_entry(),
        )
        self.assertEqual(records[0]["render_source_kind"], "rss_fallback")
        self.assertEqual(records[0]["rss_fallback_entry_kind"], "source_link_only")
        self.assertEqual(records[0]["rss_fallback_entry_contract_status"], "valid")
        self.assertEqual(records[0]["hard_safety_rejection_reason"], "unsupported accident claim")
        self.assertEqual(
            records[0]["editorial_entry_line_provenance"][0]["origin"],
            "fallback_source_only",
        )

    def test_legacy_english_rss_entry_cannot_invalidate_other_accepted_entries(self) -> None:
        data = {
            "counts": {"processed": 2, "selected": 2},
            "failed_sources": [],
            "items": [item(1), item(2)],
        }
        data["items"][1]["editorial_entry"] = {
            "entry_ja": "Dengue cases surge 56pc as MOH warns of nationwide spread",
            "supporting_points_ja": [
                "KUALA LUMPUR, Aug 21 — The Ministry of Health issued a warning.",
            ],
        }
        rejection = groq_renderer.GroqEditorialEntryRejected(
            "unsupported death claim",
            {"transport_status": "success", "json_contract_status": "valid"},
        )
        with patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry",
            side_effect=[accepted_result(1), rejection],
        ):
            rendered, accepted, stats, records = groq_renderer.render_with_groq(data, "key", "test-model")
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        annotate_decision_records(data, final, records, decisions)
        improved = groq_renderer.build_improved_items_payload(
            accepted, "test-model", stats, groq_renderer.datetime.now(), records
        )
        markdown = markdown_renderer.render_editorial_entries(final)
        self.assertNotIn("KUALA LUMPUR,", markdown)
        self.assertNotIn("Dengue cases surge", markdown)
        self.assertIn("この記事の詳細は出典リンクで確認できます。", markdown)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected_path = root / "selected.json"
            candidate_path = root / "candidate.md"
            improved_path = root / "improved.json"
            fallback_path = root / "fallback.md"
            selected_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            candidate_path.write_text(markdown, encoding="utf-8")
            improved_path.write_text(json.dumps(improved, ensure_ascii=False), encoding="utf-8")
            fallback_path.write_text(markdown_renderer.render(data), encoding="utf-8")
            result = validate_candidate(selected_path, candidate_path, improved_path, fallback_path)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(
            result["observation"]["rss_fallback_source_link_only_count"],
            1,
        )

    def test_hard_safety_checks_apply_to_the_complete_editorial_entry(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe numeric unit conversion"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "Fund worth RM 1 billion announced", "description": ""},
                {"entry_ja": "1億リンギットの基金が発表されました。", "supporting_points_ja": []},
            )
        with self.assertRaisesRegex(ValueError, "unsafe RM1 date/currency conversion"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "RM 1 payment support", "description": ""},
                {"entry_ja": "1月7日リンギット支援が始まります。", "supporting_points_ja": []},
            )
        with self.assertRaisesRegex(ValueError, "unsupported death claim"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "Student enrolment declined", "description": ""},
                {"entry_ja": "学生の死亡が報じられました。", "supporting_points_ja": []},
            )
        with self.assertRaisesRegex(ValueError, "english lead leakage"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "Agency update", "description": ""},
                {"entry_ja": "KUALA LUMPUR, May 1 — The agency issued an update.", "supporting_points_ja": []},
            )
        with self.assertRaisesRegex(ValueError, "forbidden display leakage"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "Agency update", "description": ""},
                {"entry_ja": "KUALA LUMPUR, Aug 1に当局が更新を発表しました。", "supporting_points_ja": []},
            )
        groq_renderer.validate_editorial_entry_against_source(
            {"title": "Road accident delayed traffic", "description": ""},
            {"entry_ja": "道路事故により交通の遅れが出ています。", "supporting_points_ja": []},
        )

    def test_missing_api_key_preserves_every_url_as_rss_entry(self) -> None:
        data = {"counts": {"processed": 2, "selected": 2}, "failed_sources": [], "items": [item(1), item(2)]}
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "selected.json"
            output_path = Path(directory) / "candidate.md"
            improved_path = Path(directory) / "improved.json"
            input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False), patch.object(
                sys,
                "argv",
                [
                    "render_malaysia_news_with_groq.py",
                    "--json-input", str(input_path),
                    "--output", str(output_path),
                    "--improved-items-output", str(improved_path),
                ],
            ):
                self.assertEqual(groq_renderer.main(), 0)
            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("https://example.test/1", markdown)
            self.assertIn("https://example.test/2", markdown)
            payload = json.loads(improved_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["diagnostics"]["editorial_entry_counts"]["rss_fallback_count"], 2)

    def test_provenance_is_per_entry_field(self) -> None:
        original = {"items": [item()]}
        final = copy.deepcopy(original)
        final["items"][0]["editorial_entry"] = {
            "entry_ja": "Groq概要",
            "supporting_points_ja": ["RSS補足1", "Groq補足"],
        }
        records = [{"index": 1, "link": item()["link"], "accepted": True}]
        decisions = build_render_decisions(final["items"], records)
        annotate_decision_records(original, final, records, decisions)
        counts = provenance_observation(records)["line_counts"]
        self.assertEqual(counts["groq_replaced"], 2)
        self.assertEqual(counts["groq_inherited"], 1)

    def test_v2_validator_accepts_overview_and_supporting_points(self) -> None:
        data = {
            "counts": {"processed": 3, "selected": 3},
            "failed_sources": [],
            "items": [
                item(1),
                {**item(2), "category": "【速報】"},
                {**item(3), "category": "【知っておくと得】"},
            ],
        }
        final = copy.deepcopy(data)
        final["items"][0]["editorial_entry"] = {
            "entry_ja": "当局は交通計画を来月開始する見通しだと述べました。",
            "supporting_points_ja": ["開始時期は9月とされています。"],
        }
        improved = {
            "counts": {"requested": 3, "accepted": 1, "fallback": 2},
            "diagnostics": {
                "editorial_entry_counts": {
                    "selected_count": 3,
                    "groq_accepted_count": 1,
                    "rss_fallback_count": 2,
                    "rss_fallback_source_link_only_count": 2,
                    "request_cap_skipped_count": 0,
                },
                "hard_safety_rejection_reason_counts": {},
                "transport_status_counts": {"success": 3},
                "json_contract_status_counts": {"valid": 3},
                "editorial_entry_provenance": {"line_counts": {"rss_derived": 5, "groq_replaced": 1}},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected_path = root / "selected.json"
            candidate_path = root / "candidate.md"
            improved_path = root / "improved.json"
            fallback_path = root / "fallback.md"
            selected_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            candidate_path.write_text(markdown_renderer.render_editorial_entries(final), encoding="utf-8")
            improved_path.write_text(json.dumps(improved, ensure_ascii=False), encoding="utf-8")
            fallback_path.write_text(markdown_renderer.render(data), encoding="utf-8")
            result = validate_candidate(selected_path, candidate_path, improved_path, fallback_path)
        self.assertTrue(result["passed"], result["failures"])


if __name__ == "__main__":
    unittest.main()
