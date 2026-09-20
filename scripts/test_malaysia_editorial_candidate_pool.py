#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

import malaysia_rss_summary as summary


class MalaysiaEditorialCandidatePoolTests(unittest.TestCase):
    def test_candidate_pool_keeps_category_cap_exclusions_for_editorial_routing(self) -> None:
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
        self.assertFalse(payload["candidate_policy"]["fixed_category_caps_applied"])
        self.assertFalse(payload["candidate_policy"]["overall_selector_cap_applied"])
        self.assertEqual(payload["counts"]["candidates"], 9)


if __name__ == "__main__":
    unittest.main()
