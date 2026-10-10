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
from malaysia_groq_output_contract import (
    EDITORIAL_ENTRY_V3_REPAIR_SCHEMA,
    EDITORIAL_ENTRY_V3_SCHEMA,
    EDITORIAL_ENTRY_V4_SCHEMA,
    editorial_entry_repair_schema_error,
    editorial_entry_schema_error,
    editorial_entry_v4_schema_error,
)
from malaysia_groq_force_all_policy import force_all_request_cap
from malaysia_groq_render_decision import (
    annotate_decision_records,
    apply_render_decisions,
    build_render_decisions,
    provenance_observation,
    validated_source_display_editorial_entry,
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
            "headline_ja": f"交通計画{index} 来月開始",
            "short_headline_ja": f"交通計画{index}開始",
            "entry_ja": f"RSS概要{index}",
            "supporting_points_ja": [f"RSS補足{index}"],
        },
    }


def accepted_result(index: int) -> groq_renderer.GroqEditorialEntryResult:
    return groq_renderer.GroqEditorialEntryResult(
        {
            "headline_ja": f"交通計画{index} 来月開始",
            "short_headline_ja": f"交通計画{index}開始",
            "entry_ja": f"当局は計画{index}を来月開始する見通しだと述べました。",
            "supporting_points_ja": [f"開始時期は9月とされています。"],
        },
        {"transport_status": "success", "json_contract_status": "valid"},
    )


class EditorialEntryV3Test(unittest.TestCase):
    def test_publication_time_reaches_prompt_and_markdown_without_changing_contract(self) -> None:
        article = item()
        article["published_at"] = "2026-09-27T15:43:00+08:00"
        data = {"generated_at": "2026-09-27T17:08:00+08:00", "counts": {"processed": 1, "selected": 1}, "items": [article]}
        with patch("render_malaysia_news_with_groq.request_groq_summary_with_retry", return_value=accepted_result(1)) as request:
            groq_renderer.render_with_groq(data, "key", "test-model")
        payload = groq_renderer.groq_payload_for_item(request.call_args.args[0])
        self.assertEqual(payload["published_at"], article["published_at"])
        self.assertEqual(payload["publication_as_of"], data["generated_at"])
        self.assertIn("終了時刻がpublication_as_ofより前なら", groq_renderer.SYSTEM_PROMPT)
        self.assertIn("publication_as_of", groq_renderer.REPAIR_SYSTEM_PROMPT)
        self.assertTrue(markdown_renderer.render_editorial_entries(data).startswith("更新時点：2026-09-27T17:08:00+08:00\n"))

    def test_strict_contract_accepts_zero_or_two_points_and_rejects_legacy_shape(self) -> None:
        self.assertEqual(
            editorial_entry_schema_error(
                {"editorial_entry": {"headline_ja": "概要", "short_headline_ja": "概要", "entry_ja": "概要です。", "supporting_points_ja": []}}
            ),
            "",
        )
        self.assertEqual(
            editorial_entry_schema_error(
                {
                    "editorial_entry": {
                        "headline_ja": "概要",
                        "short_headline_ja": "概要",
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
                {"editorial_entry": {"headline_ja": "概要", "short_headline_ja": "概要", "entry_ja": "", "supporting_points_ja": [], "extra": "x"}}
            ),
            "editorial_entry_shape",
        )
        self.assertEqual(EDITORIAL_ENTRY_V3_SCHEMA["required"], ["editorial_entry"])
        self.assertEqual(
            editorial_entry_repair_schema_error(
                {"editorial_entry": {"headline_ja": "概要", "short_headline_ja": "概要", "entry_ja": "概要です。"}}
            ),
            "",
        )
        self.assertEqual(
            editorial_entry_repair_schema_error(
                {"editorial_entry": {"headline_ja": "概要", "short_headline_ja": "概要", "entry_ja": "概要です。", "supporting_points_ja": []}}
            ),
            "editorial_entry_shape",
        )
        self.assertEqual(EDITORIAL_ENTRY_V3_REPAIR_SCHEMA["required"], ["editorial_entry"])

    def test_both_headlines_are_required_and_limited(self) -> None:
        properties = EDITORIAL_ENTRY_V3_SCHEMA["properties"]["editorial_entry"]["properties"]
        repair_properties = EDITORIAL_ENTRY_V3_REPAIR_SCHEMA["properties"]["editorial_entry"]["properties"]
        self.assertEqual(properties["headline_ja"]["maxLength"], 60)
        self.assertEqual(repair_properties["headline_ja"]["maxLength"], 60)
        self.assertEqual(properties["short_headline_ja"]["maxLength"], 26)
        invalid = {
            "headline_ja": "あ" * 61,
            "short_headline_ja": "雷雨に注意",
            "entry_ja": "気象当局は複数地域に雷雨と大雨への注意を呼びかけました。",
            "supporting_points_ja": [],
        }
        self.assertEqual(editorial_entry_schema_error({"editorial_entry": invalid}), "editorial_headline_too_long")
        with self.assertRaisesRegex(ValueError, "editorial_headline_too_long"):
            groq_renderer.validate_groq_editorial_entry({"editorial_entry": {key: value for key, value in invalid.items() if key != "supporting_points_ja"}})

    def test_value_failure_reasons_identify_the_invalid_field(self) -> None:
        valid = {"headline_ja": "通常見出し", "short_headline_ja": "短見出し", "entry_ja": "概要です。", "supporting_points_ja": []}
        cases = (
            ({**valid, "headline_ja": None}, "editorial_headline_type"),
            ({**valid, "headline_ja": " "}, "editorial_headline_empty"),
            ({**valid, "headline_ja": "あ" * 61}, "editorial_headline_too_long"),
            ({**valid, "short_headline_ja": None}, "editorial_short_headline_type"),
            ({**valid, "short_headline_ja": " "}, "editorial_short_headline_empty"),
            ({**valid, "short_headline_ja": "あ" * 27}, "editorial_short_headline_too_long"),
            ({**valid, "entry_ja": None}, "editorial_entry_type"),
            ({**valid, "entry_ja": " "}, "editorial_entry_empty"),
            ({**valid, "supporting_points_ja": "補足"}, "editorial_supporting_points_type"),
            ({**valid, "supporting_points_ja": ["1", "2", "3"]}, "editorial_supporting_points_count"),
            ({**valid, "supporting_points_ja": ["補足", 1]}, "editorial_supporting_point_type"),
        )
        for entry, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(editorial_entry_schema_error({"editorial_entry": entry}), expected)

    def test_article_fallback_is_a_valid_v4_object(self) -> None:
        self.assertEqual(
            editorial_entry_v4_schema_error({"editorial_entry": validated_rss_fallback_editorial_entry()}),
            "",
        )

    def test_v4_uses_overview_without_supporting_points_or_character_ceiling(self) -> None:
        long_overview = "当局は対象地域と終了時刻を示して警報を発表しました。" * 12
        entry = {"headline_ja": "警報を発表", "short_headline_ja": "警報を発表", "entry_ja": long_overview}
        self.assertEqual(editorial_entry_v4_schema_error({"editorial_entry": entry}), "")
        self.assertEqual(groq_renderer.validate_groq_editorial_entry({"editorial_entry": entry}), entry)
        self.assertEqual(
            editorial_entry_v4_schema_error({"editorial_entry": {**entry, "supporting_points_ja": []}}),
            "editorial_entry_shape",
        )
        self.assertNotIn("maxLength", EDITORIAL_ENTRY_V4_SCHEMA["properties"]["editorial_entry"]["properties"]["entry_ja"])
        article = item()
        article["editorial_entry"] = entry
        markdown = markdown_renderer.render_editorial_entries({"counts": {"processed": 1, "selected": 1}, "items": [article]})
        self.assertIn(f"- 概要：{long_overview}", markdown)
        self.assertNotIn("- 補足：", markdown)

    def test_v4_markdown_has_both_headlines_and_overview_only(self) -> None:
        data = {"counts": {"processed": 1, "selected": 1}, "failed_sources": [], "items": [item()]}
        markdown = markdown_renderer.render_editorial_entries(data)
        self.assertIn("【暮らしに関わる更新】", markdown)
        self.assertIn("【社会・経済の動き】", markdown)
        self.assertIn("- 見出し：交通計画1 来月開始", markdown)
        self.assertIn("- 短見出し：交通計画1開始", markdown)
        self.assertIn("- 概要：RSS概要1", markdown)
        self.assertNotIn("- 補足：", markdown)
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

    def test_request_uses_v4_schema_and_user_only_contract(self) -> None:
        parsed = {
            "editorial_entry": {
                "headline_ja": "交通計画 来月開始",
                "short_headline_ja": "交通計画開始",
                "entry_ja": "当局は来月の交通計画開始を見込むと述べました。",
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
                summary_contract="editorial_entry_v4",
            )
        self.assertEqual(result.editorial_entry["entry_ja"], parsed["editorial_entry"]["entry_ja"])
        self.assertEqual(request.call_args.kwargs["json_schema"], EDITORIAL_ENTRY_V4_SCHEMA)
        self.assertEqual(request.call_args.kwargs["json_schema_name"], "malaysia_news_editorial_entry_v4")
        messages = groq_renderer.summary_request_messages(item(), "user_only")
        self.assertEqual([message["role"] for message in messages], ["user"])
        self.assertIn('"editorial_entry"', messages[0]["content"])
        self.assertNotIn('"selected_summary"', messages[0]["content"])

    def test_request_cap_is_first_twenty_in_selected_order_without_lexical_exclusions(self) -> None:
        data = {"items": [item(index) for index in range(1, 22)]}
        data["items"][0]["title"] = "Financial market article"
        data["items"][1]["title"] = "Paul Tan transport article"
        data["items"][2]["title"] = "Incident report article"
        with patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry",
            side_effect=[accepted_result(index) for index in range(1, 21)],
        ) as request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(
                data, "key", "test-model"
            )
        self.assertEqual(request.call_count, 20)
        self.assertEqual(stats, {"requested": 20, "accepted": 20, "fallback": 0})
        self.assertEqual(len(accepted), 20)
        self.assertEqual(
            [call.args[0]["link"] for call in request.call_args_list],
            [f"https://example.test/{index}" for index in range(1, 21)],
        )
        self.assertEqual(records[-1]["reason"], "request_cap")
        self.assertEqual(rendered["items"][20]["editorial_entry"]["entry_ja"], "RSS概要21")

    def test_request_cap_keeps_the_existing_environment_override_name(self) -> None:
        with patch.dict(os.environ, {"MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP": "7"}, clear=False):
            self.assertEqual(force_all_request_cap(), 7)

    def test_hard_safety_rejection_uses_validated_v3_fallback_and_records_reason(self) -> None:
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

    def test_contract_failure_uses_one_repair_and_keeps_both_diagnostics(self) -> None:
        data = {"items": [item()]}
        primary = groq_renderer.GroqEditorialEntryContractError(
            "headline_ja exceeds 60 characters",
            {"transport_status": "success", "json_contract_status": "schema_invalid"},
        )
        repaired = groq_renderer.GroqEditorialEntryResult(
            {"headline_ja": "交通計画を来月開始へ", "short_headline_ja": "交通計画を開始へ", "entry_ja": "当局は交通計画を来月始める見通しだと述べました。", "supporting_points_ja": []},
            {"transport_status": "success", "json_contract_status": "valid"},
        )
        with patch("render_malaysia_news_with_groq.request_groq_summary_with_retry", side_effect=primary), patch(
            "render_malaysia_news_with_groq.request_groq_repair_entry", return_value=repaired
        ) as repair_request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(data, "key", "test-model")
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        annotate_decision_records(data, final, records, decisions)
        self.assertEqual(repair_request.call_count, 1)
        self.assertEqual(stats, {"requested": 1, "accepted": 1, "fallback": 0})
        self.assertEqual(accepted[0]["generation_kind"], "repair")
        self.assertEqual(records[0]["render_source_kind"], "groq_repaired")
        self.assertTrue(records[0]["repair_attempted"])
        self.assertTrue(records[0]["repair_accepted"])
        self.assertEqual(records[0]["groq_call"]["json_contract_status"], "schema_invalid")
        self.assertEqual(records[0]["groq_repair_call"]["json_contract_status"], "valid")

    def test_api_not_run_uses_source_display_with_title_and_description(self) -> None:
        data = {"items": [item()]}
        rendered, _, stats, records = groq_renderer.render_with_groq(data, "", "test-model")
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        annotate_decision_records(data, final, records, decisions)
        self.assertEqual(stats, {"requested": 0, "accepted": 0, "fallback": 0})
        self.assertEqual(final["items"][0]["editorial_entry"], validated_source_display_editorial_entry(item()))
        self.assertIn(item()["description"], final["items"][0]["editorial_entry"]["entry_ja"])
        self.assertEqual(records[0]["render_source_kind"], "source_display")
        self.assertEqual(records[0]["source_display_entry_kind"], "source_title_and_description")
        self.assertEqual(records[0]["editorial_entry_line_provenance"][0]["origin"], "source_display")

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
        data["items"][1]["title"] = "KUALA LUMPUR, Aug 21 — Dengue cases surge"
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
        self.assertNotIn("The Ministry of Health issued a warning.", markdown)
        self.assertNotIn("この記事の詳細は出典リンクで確認できます。", markdown)
        self.assertIn("【原文のみ】", markdown)
        self.assertIn("- 原題：KUALA LUMPUR, Aug 21 — Dengue cases surge", markdown)
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
        self.assertEqual(result["markdown_validation"]["source_only_links"], [item(2)["link"]])

    def test_validator_allows_forbidden_source_text_only_in_source_display(self) -> None:
        data = {
            "counts": {"processed": 2, "selected": 2},
            "failed_sources": [],
            "items": [item(1), item(2)],
        }
        data["items"][1]["title"] = "Agency update from Kuala Lumpur"
        data["items"][1]["description"] = "KUALA LUMPUR, Aug 28 — The agency issued an update."
        rendered = copy.deepcopy(data)
        rendered["items"][0]["editorial_entry"] = accepted_result(1).editorial_entry
        records = [
            {"index": 1, "link": item(1)["link"], "accepted": True},
            {
                "index": 2,
                "link": item(2)["link"],
                "decision": "skipped",
                "reason": "request_cap",
                "requested": False,
                "accepted": False,
            },
        ]
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        annotate_decision_records(data, final, records, decisions)
        improved = {
            "counts": {"requested": 1, "accepted": 1, "fallback": 0},
            "diagnostics": {"decision_records": records},
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
        self.assertEqual(result["markdown_validation"]["source_display_links"], [item(2)["link"]])

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
        with self.assertRaisesRegex(ValueError, "unsupported death claim"):
            groq_renderer.validate_editorial_entry_against_source(
                {"title": "Student enrolment declined", "description": ""},
                {"headline_ja": "生徒数が減少", "short_headline_ja": "生徒数が減少", "entry_ja": "在籍者数の減少が報告されました。" * 8 + "学生の死亡も報じられました。"},
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

    def test_money_claims_match_source_amount_and_currency(self) -> None:
        cases = [
            ("RM160 a month", "月160円節約", "unsupported yen conversion"),
            ("RM130 juta", "130億リンギット", "monetary amount or currency"),
            ("RM130m", "1億3000万リンギット（約130億円相当）", "unsupported yen conversion"),
            ("RM1.5 bilion", "1.5億リンギット", "monetary amount or currency"),
            ("RM100 juta", "1億リンギット（約2億5千万円）", "unsupported yen conversion"),
            ("No amount stated", "1億リンギットを支給", "monetary amount or currency"),
            ("RM100 juta", "数百万円規模を支援", "monetary amount could not be verified"),
            ("$100 grant", "100米ドルの助成金", "monetary amount or currency"),
        ]
        for source, rendered, reason in cases:
            with self.subTest(source=source, rendered=rendered), self.assertRaisesRegex(ValueError, reason):
                groq_renderer.validate_editorial_entry_against_source(
                    {"title": source, "description": ""}, {"entry_ja": rendered}
                )
        for source, rendered in (
            ("RM130 juta", "1億3000万リンギット"),
            ("RM1.5 bilion", "15億リンギット"),
            ("RM100 juta", "1億リンギット"),
            ("JPY 250 million", "2億5千万円"),
            ("RM1,000", "1千リンギット"),
            ("Form 6 students receive RM2,500", "Form 6生徒にRM2,500を支給"),
            ("US$100 grant", "100米ドルの助成金"),
            ("$100 grant", "100ドルの助成金"),
            ("The agency counted 130 projects", "130件の事業"),
        ):
            with self.subTest(source=source, rendered=rendered):
                groq_renderer.validate_editorial_entry_against_source(
                    {"title": source, "description": ""}, {"entry_ja": rendered}
                )

    def test_money_rejection_keeps_only_the_affected_item_as_source_link(self) -> None:
        data = {"items": [item(1), item(2)]}
        data["items"][0]["title"] = "Monthly savings RM160"
        data["items"][1]["title"] = "Fund of RM130 juta"
        def completion(entry: str) -> ChatCompletion:
            return ChatCompletion(
                "{}",
                {"editorial_entry": {
                    "headline_ja": entry,
                    "short_headline_ja": entry,
                    "entry_ja": entry,
                }},
                {"transport_status": "success", "json_contract_status": "valid"},
            )
        with patch(
            "render_malaysia_news_with_groq.request_chat_completion",
            side_effect=[
                completion("月160円節約"), completion("月160円節約"),
                completion("1億3000万リンギットの基金"),
            ],
        ) as request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(
                data, "test-key", groq_renderer.DEFAULT_MODEL
            )
        decisions = build_render_decisions(rendered["items"], records)
        final = apply_render_decisions(rendered, decisions)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(stats, {"requested": 2, "accepted": 1, "fallback": 1})
        self.assertEqual(records[0]["hard_safety_rejection_reason"], "unsupported yen conversion")
        self.assertTrue(records[0]["repair_attempted"])
        self.assertEqual(records[0]["groq_call"]["transport_status"], "success")
        self.assertEqual(decisions[0].source_kind, "rss_fallback")
        self.assertEqual(decisions[1].source_kind, "groq_accepted")
        self.assertEqual(len(accepted), 1)
        self.assertEqual(final["items"][1]["editorial_entry"]["entry_ja"], "1億3000万リンギットの基金")
        markdown = markdown_renderer.render_editorial_entries(final)
        self.assertIn(data["items"][0]["link"], markdown)
        self.assertIn(data["items"][1]["link"], markdown)
        self.assertNotIn("月160円節約", markdown)

    def test_money_prompt_preserves_original_amount_spelling(self) -> None:
        article = item()
        article["title"] = "Aid of RM1.3 billion and RM130 juta announced"
        article["description"] = "The agency also offered RM160 per month."
        payload = groq_renderer.groq_payload_for_item(article)
        self.assertEqual(payload["source_money_literals"], ["RM1.3 billion", "RM130 juta", "RM160"])
        self.assertIn("RM1.3 billion", groq_renderer.summary_request_messages(article, "user_only")[0]["content"])
        self.assertIn("億・万や円へ換算", groq_renderer.money_repair_request_messages(article)[0]["content"])

    def test_money_rejection_can_recover_with_literal_source_amount(self) -> None:
        article = item()
        article["title"] = "Aid of RM1.3 billion announced"
        data = {"items": [article]}
        primary = groq_renderer.GroqEditorialEntryRejected(
            "unsafe numeric unit conversion: RM1.3 billion",
            {"transport_status": "success", "json_contract_status": "valid"},
        )
        parsed = {"editorial_entry": {
            "headline_ja": "RM1.3 billionの支援を発表",
            "short_headline_ja": "RM1.3 billionの支援",
            "entry_ja": "政府はRM1.3 billionの支援を発表しました。",
        }}
        with patch("render_malaysia_news_with_groq.request_groq_summary_with_retry", side_effect=primary), patch(
            "render_malaysia_news_with_groq.request_chat_completion",
            return_value=ChatCompletion("{}", parsed, {"transport_status": "success", "json_contract_status": "valid"}),
        ) as request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(
                data, "key", groq_renderer.DEFAULT_MODEL, summary_max_tokens=800
            )
        self.assertEqual(stats, {"requested": 1, "accepted": 1, "fallback": 0})
        self.assertEqual(accepted[0]["generation_kind"], "money_repair")
        self.assertTrue(records[0]["repair_accepted"])
        self.assertEqual(records[0]["hard_safety_rejection_reason"], "")
        self.assertEqual(records[0]["money_repair_trigger_reason"], "unsafe numeric unit conversion: RM1.3 billion")
        self.assertEqual(request.call_args.kwargs["max_tokens"], 800)
        self.assertEqual(request.call_args.kwargs["json_schema_name"], "malaysia_news_editorial_entry_v4_money_repair")
        self.assertEqual(build_render_decisions(rendered["items"], records)[0].source_kind, "groq_repaired")

    def test_money_repair_still_rejects_a_wrong_amount(self) -> None:
        article = item()
        article["title"] = "Aid of RM1.3 billion announced"
        primary = groq_renderer.GroqEditorialEntryRejected("unsupported yen conversion")
        parsed = {"editorial_entry": {
            "headline_ja": "1.3億リンギットの支援",
            "short_headline_ja": "1.3億リンギットの支援",
            "entry_ja": "政府は1.3億リンギットの支援を発表しました。",
        }}
        with patch("render_malaysia_news_with_groq.request_groq_summary_with_retry", side_effect=primary), patch(
            "render_malaysia_news_with_groq.request_chat_completion",
            return_value=ChatCompletion("{}", parsed, {"transport_status": "success", "json_contract_status": "valid"}),
        ) as request:
            rendered, accepted, stats, records = groq_renderer.render_with_groq(
                {"items": [article]}, "key", groq_renderer.DEFAULT_MODEL
            )
        self.assertEqual(request.call_count, 1)
        self.assertEqual(stats, {"requested": 1, "accepted": 0, "fallback": 1})
        self.assertEqual(accepted, [])
        self.assertTrue(records[0]["repair_attempted"])
        self.assertEqual(build_render_decisions(rendered["items"], records)[0].source_kind, "rss_fallback")

    def test_missing_api_key_preserves_every_url_as_source_display(self) -> None:
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
            self.assertEqual(payload["diagnostics"]["editorial_entry_counts"]["source_display_count"], 2)
            self.assertEqual(payload["diagnostics"]["editorial_entry_counts"]["rss_fallback_count"], 0)

    def test_schema_invalid_reason_counts_are_kept_separate(self) -> None:
        records = [
            {
                "groq_call": {
                    "transport_status": "success",
                    "json_contract_status": "schema_invalid",
                    "json_contract_reason": "editorial_entry_shape",
                }
            },
            {
                "groq_call": {
                    "transport_status": "success",
                    "json_contract_status": "schema_invalid",
                    "json_contract_reason": "editorial_headline_too_long",
                },
                "groq_repair_call": {
                    "transport_status": "success",
                    "json_contract_status": "schema_invalid",
                    "json_contract_reason": "editorial_entry_empty",
                },
            },
            {"groq_call": {"transport_status": "success", "json_contract_status": "valid"}},
        ]

        observation = groq_renderer.transport_observation(records)

        self.assertEqual(
            observation["json_contract_reason_counts"],
            {"editorial_entry_shape": 1, "editorial_headline_too_long": 1},
        )
        self.assertEqual(
            observation["primary_call_outcome_counts"],
            {"json_contract_failure": 2, "transport_and_contract_valid": 1},
        )
        self.assertEqual(
            observation["repair_json_contract_reason_counts"],
            {"editorial_entry_empty": 1},
        )

    def test_provenance_is_per_entry_field(self) -> None:
        original = {"items": [item()]}
        final = copy.deepcopy(original)
        final["items"][0]["editorial_entry"] = {
            "headline_ja": "交通計画を来月開始へ",
            "short_headline_ja": "交通計画を開始へ",
            "entry_ja": "Groq概要",
            "supporting_points_ja": ["RSS補足1", "Groq補足"],
        }
        records = [{"index": 1, "link": item()["link"], "accepted": True}]
        decisions = build_render_decisions(final["items"], records)
        annotate_decision_records(original, final, records, decisions)
        counts = provenance_observation(records)["line_counts"]
        self.assertEqual(counts["groq_replaced"], 3)
        self.assertEqual(counts["groq_inherited"], 0)

    def test_v3_validator_accepts_overview_and_supporting_points(self) -> None:
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
            "headline_ja": "交通計画を来月開始へ",
            "short_headline_ja": "交通計画を開始へ",
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
