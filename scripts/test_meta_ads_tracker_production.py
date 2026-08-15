from __future__ import annotations

import unittest
from datetime import datetime, timezone

from meta_ads_tracker_collect import collect
from meta_ads_tracker_contract import load_and_validate_source_config
from meta_ads_tracker_publication import ContractError, build_public_report, validate_candidate, validate_public_report


def candidate_item(change_type: str = "new_url") -> dict:
    return {
        "id": "meta-product-news-rss-1234567890abcdef",
        "changeType": change_type,
        "sourceId": "meta-product-news-rss",
        "title": "Official product update",
        "officialUrl": "https://about.fb.com/news/official-update/",
        "priority": "standard",
        "announcementDate": {"status": "stated", "value": "2026-08-15"},
        "effectiveDate": {"status": "not_stated", "value": None},
        "rollout": {"status": "not_stated", "value": None},
        "targets": {"status": "not_stated", "value": None},
        "businessImpact": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "action": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "reviewStatus": "pending",
        "sourceContext": "The official announcement says the feature is updated.",
    }


class MetaAdsProductionTest(unittest.TestCase):
    def test_approved_decision_is_required_and_public_report_is_valid(self) -> None:
        candidate = {
            "schemaVersion": "meta-ads-tracker-candidates/v1",
            "generatedAt": "2026-08-15T00:00:00Z",
            "week": {"startDate": "2026-08-10", "endDate": "2026-08-16", "label": "2026-08-10〜2026-08-16"},
            "items": [candidate_item()],
        }
        validate_candidate(candidate)
        with self.assertRaises(ContractError):
            build_public_report(candidate, {}, "2026-08-15T00:00:00Z")
        decision = {
            "meta-product-news-rss-1234567890abcdef": {
                "reviewStatus": "approved",
                "reviewer": "human@example.test",
                "reviewedAt": "2026-08-15T01:00:00Z",
                "priority": "high",
                "businessImpact": {"status": "human_assessed", "summary": "確認が必要です。", "assessmentSource": "human_review"},
                "action": {"status": "review_required", "summary": "対象設定を確認します。", "assessmentSource": "human_review"},
            }
        }
        report = build_public_report(candidate, decision, "2026-08-15T00:00:00Z")
        self.assertEqual(report["items"][0]["priority"], "high")
        validate_public_report(report)

    def test_collector_classifies_new_and_content_changes_without_raw_state(self) -> None:
        config = load_and_validate_source_config()
        rss = """<rss><channel><item><title>Update</title><link>https://about.fb.com/news/update/</link><pubDate>Sat, 15 Aug 2026 00:00:00 GMT</pubDate><description>First text</description></item></channel></rss>"""
        sdk = "[]"
        bodies = {config["sources"][0]["fetchUrl"]: rss, config["sources"][3]["fetchUrl"]: sdk}
        def fetch(url: str, _timeout: float) -> tuple[str, str]:
            return bodies[url], "application/xml"
        now = datetime(2026, 8, 15, tzinfo=timezone.utc)
        candidate, state = collect(config, {"sources": {}}, 1, now, fetch)
        self.assertEqual(candidate["items"][0]["changeType"], "new_url")
        self.assertNotIn("raw", state)
        bodies[config["sources"][0]["fetchUrl"]] = rss.replace("First text", "Changed text")
        next_candidate, _ = collect(config, state, 1, now, fetch)
        self.assertEqual(next_candidate["items"][0]["changeType"], "content_changed")


if __name__ == "__main__":
    unittest.main()
