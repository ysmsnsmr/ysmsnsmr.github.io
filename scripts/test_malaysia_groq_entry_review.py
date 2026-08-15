#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_entry_review import entry_review_payload, parse_entry_review_content
from render_malaysia_news_with_groq import (
    GroqSummaryRejected,
    GroqSummaryResult,
    inspect_entry_candidate,
    render_with_groq,
)


ENTRY = {
    "text_ja": "政府が計画を発表したと報じられました。",
    "subject": {"source_text": "Government", "text_ja": "政府"},
    "attribution": {"source_text": "announced", "text_ja": "発表した"},
    "state": {
        "kind": "plan_or_proposal",
        "source_text": "plan",
        "text_ja": "計画",
    },
    "certainty": {
        "kind": "planned",
        "source_text": "plan",
        "text_ja": "計画",
    },
}


class EntryReviewTest(unittest.TestCase):
    def test_rejected_full_summary_keeps_reviewed_entry_for_observation(self) -> None:
        item = {
            "category": "【生活インパクト】",
            "source": "Example News",
            "published_date": "2026年8月2日",
            "title": "Government plan",
            "description": "The government announced a plan.",
            "link": "https://example.test/government-plan",
            "selected_summary": {
                "conclusion": "RSSの結論です。",
                "what_happened": ["RSSの詳細です。"],
                "life_impact": "RSSの影響です。",
                "next_action": "",
            },
        }
        with patch("render_malaysia_news_with_groq.item_needs_groq", return_value=True), patch(
            "render_malaysia_news_with_groq.groq_exclusion_reason", return_value=""
        ), patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry",
            side_effect=GroqSummaryRejected("invalid summary", ENTRY, "incomplete", ["missing_attribution"]),
        ), patch(
            "render_malaysia_news_with_groq.request_entry_review",
            return_value={"verdict": "revise", "issues": ["attribution"], "reviewed_entry": ENTRY},
        ):
            _, _, stats, records = render_with_groq(
                {"items": [item]},
                "key",
                "model",
                False,
                False,
            )

        self.assertEqual(stats, {"requested": 1, "accepted": 0, "fallback": 1})
        self.assertEqual(records[0]["entry_review_verdict"], "revise")
        self.assertEqual(records[0]["entry_review_status"], "complete")
        self.assertEqual(records[0]["entry_review_candidate"], ENTRY["text_ja"])

    def test_inspection_accepts_a_contract_complete_revised_entry(self) -> None:
        item = {
            "title": "Government plan",
            "description": "The government announced a plan.",
        }
        revised_entry = {
            "text_ja": "政府が計画を発表したと報じられました。",
            "subject": {"source_text": "Government", "text_ja": "政府"},
            "attribution": {"source_text": "announced", "text_ja": "発表した"},
            "state": {
                "kind": "plan_or_proposal",
                "source_text": "plan",
                "text_ja": "計画",
            },
            "certainty": {
                "kind": "planned",
                "source_text": "plan",
                "text_ja": "計画",
            },
        }
        with patch(
            "render_malaysia_news_with_groq.request_entry_review",
            return_value={"verdict": "revise", "issues": ["certainty"], "reviewed_entry": revised_entry},
        ):
            result = inspect_entry_candidate(item, revised_entry, "key", "model", 0)

        self.assertEqual(result["entry_review_status"], "complete")
        self.assertEqual(result["entry_review_verdict"], "revise")
        self.assertEqual(result["entry_review_candidate"], revised_entry["text_ja"])

    def test_inspection_failure_is_observation_only(self) -> None:
        item = {"title": "Government plan", "description": "The government announced a plan."}
        with patch(
            "render_malaysia_news_with_groq.request_entry_review",
            side_effect=TimeoutError(),
        ):
            result = inspect_entry_candidate(item, ENTRY, "key", "model", 0)

        self.assertEqual(result["entry_review_status"], "unavailable")
        self.assertEqual(result["entry_review_reasons"], ["TimeoutError"])

    def test_payload_uses_source_and_entry_without_raw_tags(self) -> None:
        payload = entry_review_payload(
            {
                "title": "Government plan",
                "description": "The government announced a plan.",
                "tags": ["irrelevant"],
                "body_excerpt_policy": "use_body",
                "body_evidence_excerpt": "The government announced a plan.",
                "body_evidence_focus": ["procedure_or_public_service"],
                "body_evidence_forbidden": ["dateline"],
            },
            ENTRY,
        )

        self.assertNotIn("tags", payload)
        self.assertIn("body_evidence", payload)
        self.assertEqual(payload["entry"], ENTRY)

    def test_comparison_allowlist_skips_entry_review_and_excluded_items(self) -> None:
        first = {
            "title": "Government plan",
            "description": "The government announced a plan.",
            "link": "https://example.test/one",
            "selected_summary": {},
        }
        second = {
            "title": "Other plan",
            "description": "Another plan was announced.",
            "link": "https://example.test/two",
            "selected_summary": {},
        }
        rejection = GroqSummaryRejected("invalid summary", ENTRY, "incomplete", ["missing_attribution"])
        with patch("render_malaysia_news_with_groq.item_needs_groq", return_value=True), patch(
            "render_malaysia_news_with_groq.groq_exclusion_reason", return_value=""
        ), patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry", side_effect=rejection
        ), patch("render_malaysia_news_with_groq.request_entry_review") as review:
            _, _, stats, records = render_with_groq(
                {"items": [first, second]},
                "key",
                "model",
                False,
                False,
                request_link_allowlist={first["link"]},
                enable_entry_review=False,
            )

        self.assertEqual(stats, {"requested": 1, "accepted": 0, "fallback": 1})
        self.assertEqual(records[0]["entry_review_policy"], "disabled_for_model_comparison")
        self.assertEqual(records[1]["reason"], "comparison_cohort_excluded")
        review.assert_not_called()

    def test_summary_only_contract_marks_entry_review_not_applicable_without_calling_it(self) -> None:
        item = {
            "title": "Government plan",
            "description": "The government announced a plan.",
            "link": "https://example.test/summary-only",
            "selected_summary": {},
        }
        result = GroqSummaryResult(
            {
                "conclusion": "計画が発表されました。",
                "what_happened": ["政府が計画を発表しました。"],
                "life_impact": "手続きに関わる可能性があります。",
                "next_action": "公式情報を確認してください。",
            },
            None,
            "not_requested",
            [],
            {"transport_status": "success", "http_status": 200, "json_contract_status": "valid"},
        )
        with patch("render_malaysia_news_with_groq.item_needs_groq", return_value=True), patch(
            "render_malaysia_news_with_groq.groq_exclusion_reason", return_value=""
        ), patch(
            "render_malaysia_news_with_groq.request_groq_summary_with_retry", return_value=result
        ), patch("render_malaysia_news_with_groq.request_entry_review") as review:
            _, _, stats, records = render_with_groq(
                {"items": [item]},
                "key",
                "openai/gpt-oss-120b",
                False,
                False,
                summary_contract="summary_only",
            )

        self.assertEqual(stats, {"requested": 1, "accepted": 1, "fallback": 0})
        self.assertEqual(records[0]["entry_review_policy"], "not_applicable_summary_only")
        self.assertEqual(records[0]["entry_contract_status"], "not_requested")
        review.assert_not_called()

    def test_parse_pass_and_revise(self) -> None:
        parsed = parse_entry_review_content(
            '{"verdict":"pass","issues":[],"reviewed_entry":' + json.dumps(ENTRY) + "}"
        )
        self.assertEqual(parsed["verdict"], "pass")
        self.assertEqual(parsed["reviewed_entry"], ENTRY)

        revised = parse_entry_review_content(
            '{"verdict":"revise","issues":["certainty"],"reviewed_entry":'
            + json.dumps(ENTRY)
            + "}"
        )
        self.assertEqual(revised["verdict"], "revise")
        self.assertEqual(revised["issues"], ["certainty"])

    def test_parse_reject_and_invalid_contract(self) -> None:
        rejected = parse_entry_review_content('{"verdict":"reject","issues":["attribution"],"reviewed_entry":{}}')
        self.assertEqual(rejected["verdict"], "reject")
        self.assertIsNone(rejected["reviewed_entry"])

        with self.assertRaises(ValueError):
            parse_entry_review_content('{"verdict":"pass","issues":[]}')


if __name__ == "__main__":
    unittest.main()
