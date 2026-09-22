#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

import malaysia_rss_summary as summary


class MalaysiaEditorialCandidatePoolTests(unittest.TestCase):
    def test_candidate_pool_precedes_legacy_semantic_gates_and_caps(self) -> None:
        now = datetime.fromisoformat("2026-09-20T12:00:00+08:00")
        items = [
            summary.Item(
                source="Fixture Source",
                feed="https://example.test/feed",
                title=f"Fixture item {index}",
                description="Fixture description",
                pub_date=now - timedelta(minutes=index),
                pub_raw="fixture",
                link=f"https://example.test/{index}",
                score=3,
            )
            for index in range(9)
        ]

        with (
            patch.object(summary, "evaluate_item", lambda item: None),
            patch.object(summary, "key_for", lambda item: item.link),
            patch.object(summary, "should_exclude_item", lambda item: False),
            patch.object(summary, "category_for", lambda item: "【知っておくと得】"),
            patch.object(summary, "is_forced_final_noise", lambda item: False),
            patch.object(summary, "financial_topic_bucket", lambda item: ""),
        ):
            selected = summary.select_items(items, now)

        self.assertEqual(len(selected), 8)
        self.assertEqual(len(summary.LAST_EDITORIAL_CANDIDATE_POOL), 9)
        payload = summary.build_editorial_candidate_pool_json(9, [], now)
        self.assertEqual(payload["schema_version"], "malaysia-news-editorial-candidate-pool/v2")
        self.assertFalse(payload["candidate_policy"]["legacy_score_applied"])
        self.assertFalse(payload["candidate_policy"]["legacy_selector_exclusions_applied"])
        self.assertFalse(payload["candidate_policy"]["legacy_final_noise_applied"])
        self.assertFalse(payload["candidate_policy"]["fixed_category_caps_applied"])
        self.assertFalse(payload["candidate_policy"]["overall_selector_cap_applied"])
        self.assertFalse(payload["candidate_policy"]["source_limits_applied"])
        self.assertFalse(payload["candidate_policy"]["financial_limits_applied"])
        self.assertEqual(payload["counts"]["candidates"], 9)

    def test_candidate_pool_keeps_items_rejected_by_legacy_relevance_rules(self) -> None:
        now = datetime.fromisoformat("2026-09-20T12:00:00+08:00")
        low_score = summary.Item(
            source="Fixture Source",
            feed="Fixture Feed",
            title="Eligibility expansion",
            description="Households may qualify for a public voucher.",
            pub_date=now,
            pub_raw="fixture",
            link="https://example.test/eligibility",
            score=0,
        )
        final_noise = summary.Item(
            source="Fixture Source",
            feed="Fixture Feed",
            title="Fee cap",
            description="A public bazaar fee is capped.",
            pub_date=now - timedelta(minutes=1),
            pub_raw="fixture",
            link="https://example.test/fee-cap",
            score=3,
        )

        with (
            patch.object(summary, "evaluate_item", lambda item: None),
            patch.object(summary, "key_for", lambda item: item.link),
            patch.object(summary, "should_exclude_item", lambda item: False),
            patch.object(summary, "category_for", lambda item: "【知っておくと得】"),
            patch.object(summary, "is_forced_final_noise", lambda item: item is final_noise),
            patch.object(summary, "financial_topic_bucket", lambda item: ""),
        ):
            selected = summary.select_items([low_score, final_noise], now)

        self.assertEqual(selected, [])
        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [low_score, final_noise])

    def test_structural_pool_rejects_invalid_urls_and_deduplicates_before_relevance(self) -> None:
        now = datetime.fromisoformat("2026-09-20T12:00:00+08:00")
        newest = summary.Item("Source A", "Feed", "Same event", "Newest", now, "fixture", "https://example.test/event")
        older_url = summary.Item(
            "Source A", "Feed", "Same event", "Older URL copy", now - timedelta(minutes=5), "fixture", "https://example.test/event"
        )
        invalid = summary.Item("Source B", "Feed", "Invalid", "Invalid", now, "fixture", "not-a-url")

        with (
            patch.object(summary, "evaluate_item", lambda item: setattr(item, "score", 3)),
            patch.object(summary, "key_for", lambda item: item.title),
            patch.object(summary, "should_exclude_item", lambda item: False),
            patch.object(summary, "category_for", lambda item: "【知っておくと得】"),
            patch.object(summary, "is_forced_final_noise", lambda item: False),
            patch.object(summary, "financial_topic_bucket", lambda item: ""),
        ):
            summary.select_items([older_url, invalid, newest], now)

        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [newest])
        observation = summary.build_selection_observation_json([older_url, invalid, newest], [newest], 3, [], now)
        stages = {item["title"] + item["description"]: item["decision_stage"] for item in observation["items"]}
        self.assertEqual(stages["Same eventOlder URL copy"], "duplicate_url")
        self.assertEqual(stages["InvalidInvalid"], "invalid_url")


if __name__ == "__main__":
    unittest.main()
