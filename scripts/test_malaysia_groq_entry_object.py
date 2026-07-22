#!/usr/bin/env python3
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_markdown_merge import normalize_entry_candidate_summaries_for_observation
import render_malaysia_news_with_groq as groq_renderer
from render_malaysia_news_with_groq import (
    GroqSummaryRejected,
    entry_candidate_observation,
    entry_contract_for_item,
    render_with_groq,
)


def fixture_item() -> dict:
    return {
        "title": "Higher Education Minister Zambry Abd Kadir says AI integration is important",
        "description": "Zambry said universities should prepare students for AI adoption.",
        "link": "https://example.test/zambry-ai",
        "source": "Example News",
        "category": "Education",
        "published_date": "2026-07-22",
        "selected_summary": {
            "conclusion": "RSS fallback conclusion.",
            "what_happened": ["RSS fallback detail."],
            "life_impact": "RSS fallback impact.",
            "next_action": "",
        },
    }


def attributed_entry() -> dict:
    return {
        "text_ja": "ザンブリー高等教育相は、AI導入が重要だと述べました。",
        "subject": {
            "source_text": "Higher Education Minister Zambry Abd Kadir",
            "text_ja": "ザンブリー高等教育相",
        },
        "attribution": {"source_text": "said", "text_ja": "述べました"},
        "state": {
            "kind": "attributed_statement",
            "source_text": "said",
            "text_ja": "述べました",
        },
        "certainty": {"kind": "reported", "source_text": "said", "text_ja": "述べました"},
    }


class EntryObjectObservationTest(unittest.TestCase):
    def test_attributed_entry_is_contract_complete(self) -> None:
        entry, status, reasons = entry_contract_for_item(attributed_entry(), fixture_item())

        self.assertEqual(status, "complete")
        self.assertEqual(reasons, [])
        self.assertEqual(entry["text_ja"], "ザンブリー高等教育相は、AI導入が重要だと述べました。")

    def test_direct_event_can_omit_attribution(self) -> None:
        item = fixture_item()
        item["title"] = "Strong winds damage homes in Sibu Jaya"
        item["description"] = "Residents reported damage after strong winds hit the area."
        entry = {
            "text_ja": "シブジャヤで強風による住宅被害が報じられました。",
            "subject": {"source_text": "Sibu Jaya", "text_ja": "シブジャヤ"},
            "attribution": None,
            "state": {"kind": "reported_event", "source_text": "damage", "text_ja": "被害"},
            "certainty": {"kind": "reported", "source_text": "reported", "text_ja": "報じられました"},
        }

        _, status, reasons = entry_contract_for_item(entry, item)

        self.assertEqual(status, "complete")
        self.assertEqual(reasons, [])

    def test_plan_kind_is_preserved_by_contract(self) -> None:
        item = fixture_item()
        item["title"] = "Council plans drainage repairs before monsoon season"
        item["description"] = "The council expects work to begin next month."
        entry = {
            "text_ja": "市議会は雨季前の排水路修繕を計画しています。",
            "subject": {"source_text": "Council", "text_ja": "市議会"},
            "attribution": None,
            "state": {"kind": "plan_or_proposal", "source_text": "plans", "text_ja": "計画しています"},
            "certainty": {"kind": "planned", "source_text": "plans", "text_ja": "計画しています"},
        }

        _, status, reasons = entry_contract_for_item(entry, item)

        self.assertEqual(status, "complete")
        self.assertEqual(reasons, [])

    def test_warning_forecast_and_denial_kinds_are_preserved_by_contract(self) -> None:
        forecast_item = fixture_item()
        forecast_item["title"] = "MetMalaysia warns of heavy rain in Selangor"
        forecast_item["description"] = "The agency expects thunderstorms through the evening."
        forecast_entry = {
            "text_ja": "気象当局はセランゴール州の大雨と雷雨に警戒を呼びかけました。",
            "subject": {"source_text": "MetMalaysia", "text_ja": "気象当局"},
            "attribution": None,
            "state": {"kind": "warning_or_forecast", "source_text": "warns", "text_ja": "警戒を呼びかけました"},
            "certainty": {"kind": "warning", "source_text": "warns", "text_ja": "警戒"},
        }
        _, forecast_status, forecast_reasons = entry_contract_for_item(forecast_entry, forecast_item)

        denial_item = fixture_item()
        denial_item["title"] = "DBKL denies allegations over park redevelopment"
        denial_item["description"] = "The council said the proposal remains under review."
        denial_entry = {
            "text_ja": "DBKLは公園再開発を巡る疑惑を否定しました。",
            "subject": {"source_text": "DBKL", "text_ja": "DBKL"},
            "attribution": None,
            "state": {"kind": "denial_or_correction", "source_text": "denies", "text_ja": "否定しました"},
            "certainty": {"kind": "denied", "source_text": "denies", "text_ja": "否定しました"},
        }
        _, denial_status, denial_reasons = entry_contract_for_item(denial_entry, denial_item)

        self.assertEqual(forecast_status, "complete")
        self.assertEqual(forecast_reasons, [])
        self.assertEqual(denial_status, "complete")
        self.assertEqual(denial_reasons, [])

    def test_invalid_source_anchor_is_reported_without_dropping_text(self) -> None:
        entry = attributed_entry()
        entry["subject"]["source_text"] = "Kuala Lumpur mayor"

        normalized, status, reasons = entry_contract_for_item(entry, fixture_item())

        self.assertEqual(status, "invalid_anchor")
        self.assertIn("invalid_subject_source_anchor", reasons)
        self.assertEqual(normalized["text_ja"], entry["text_ja"])

    def test_incomplete_entry_is_rendered_for_observation(self) -> None:
        entry = attributed_entry()
        entry.pop("certainty")
        normalized, status, reasons = entry_contract_for_item(entry, fixture_item())
        self.assertEqual(status, "incomplete")
        self.assertIn("missing_certainty", reasons)

        record = {
            "index": 1,
            "link": fixture_item()["link"],
            "entry": normalized,
            "entry_candidate_status": "full_rejected",
            "entry_contract_status": status,
            "entry_contract_reasons": reasons,
        }
        rendered = normalize_entry_candidate_summaries_for_observation(
            {"items": [fixture_item()]}, [], [record]
        )
        item = rendered["items"][0]

        self.assertEqual(item["selected_summary"]["conclusion"], entry["text_ja"])
        self.assertTrue(item["_suppress_topic_next_action"])

    def test_current_records_do_not_reuse_legacy_conclusion_as_entry(self) -> None:
        record = {
            "index": 1,
            "link": fixture_item()["link"],
            "entry": None,
            "entry_candidate": "Legacy conclusion must not become an entry.",
            "entry_candidate_status": "full_rejected",
        }
        rendered = normalize_entry_candidate_summaries_for_observation(
            {"items": [fixture_item()]}, [], [record]
        )

        self.assertNotEqual(
            rendered["items"][0]["selected_summary"]["conclusion"],
            record["entry_candidate"],
        )

    def test_observation_counts_distinguish_contract_statuses(self) -> None:
        records = [
            {
                "requested": True,
                "decision": "fallback",
                "entry": attributed_entry(),
                "entry_contract_status": "complete",
                "entry_contract_reasons": [],
                "full_rejection_reason": "full summary rejected",
            },
            {
                "requested": True,
                "decision": "fallback",
                "entry": {"text_ja": "入口文です。"},
                "entry_contract_status": "incomplete",
                "entry_contract_reasons": ["missing_subject"],
                "full_rejection_reason": "full summary rejected",
            },
            {
                "requested": True,
                "decision": "fallback",
                "entry": None,
                "entry_contract_status": "unavailable",
                "entry_contract_reasons": ["missing_entry_object"],
                "full_rejection_reason": "validation failed",
            },
        ]

        counts = entry_candidate_observation(records)

        self.assertEqual(counts["entry_object_present_count"], 2)
        self.assertEqual(counts["entry_contract_complete_count"], 1)
        self.assertEqual(counts["entry_contract_incomplete_count"], 1)
        self.assertEqual(counts["entry_contract_unavailable_count"], 1)
        self.assertEqual(counts["entry_contract_reason_counts"], {"missing_entry_object": 1, "missing_subject": 1})

    def test_full_summary_rejection_keeps_entry_object(self) -> None:
        entry, status, reasons = entry_contract_for_item(attributed_entry(), fixture_item())
        rejection = GroqSummaryRejected("unsupported life impact", entry, status, reasons)
        with (
            mock.patch.object(groq_renderer, "item_needs_groq", return_value=True),
            mock.patch.object(groq_renderer, "request_groq_summary_with_retry", side_effect=rejection),
        ):
            _, accepted_records, stats, records = render_with_groq(
                {"items": [copy.deepcopy(fixture_item())]}, "test-key", "test-model", False, False
            )

        self.assertEqual(accepted_records, [])
        self.assertEqual(stats, {"requested": 1, "accepted": 0, "fallback": 1})
        self.assertEqual(records[0]["entry"], entry)
        self.assertEqual(records[0]["entry_candidate"], entry["text_ja"])
        self.assertEqual(records[0]["entry_contract_status"], "complete")
        self.assertEqual(records[0]["entry_candidate_status"], "full_rejected")

    def test_missing_api_key_keeps_entry_diagnostics_safe(self) -> None:
        _, _, _, records = render_with_groq(
            {"items": [copy.deepcopy(fixture_item())]}, "", "test-model", False, False
        )

        self.assertEqual(records[0]["entry_contract_status"], "not_requested")
        self.assertEqual(records[0]["entry"], None)


if __name__ == "__main__":
    unittest.main()
