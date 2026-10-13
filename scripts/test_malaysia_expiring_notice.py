#!/usr/bin/env python3
from datetime import datetime
import unittest
from unittest.mock import patch

import malaysia_rss_summary as summary
from malaysia_expiring_notice import notice_deadline, stale_relative_date
from render_malaysia_news_with_groq import validate_editorial_entry_against_source


TITLE = "Heavy rain, gusty winds expected across nine states, Putrajaya and Labuan until 6pm"
PUBLISHED = datetime.fromisoformat("2026-10-12T16:11:45+08:00")


class ExpiringNoticeTests(unittest.TestCase):
    def test_deadline_is_anchored_to_article_date_not_publication_date(self) -> None:
        deadline = notice_deadline(TITLE, "MetMalaysia issued a thunderstorm warning.", PUBLISHED)
        self.assertEqual(deadline, datetime.fromisoformat("2026-10-12T18:00:00+08:00"))

    def test_expired_notice_removed_from_legacy_and_jev_pool(self) -> None:
        now = datetime.fromisoformat("2026-10-13T09:37:57+08:00")
        item = summary.Item(
            "Malay Mail", "feed", TITLE,
            "KUALA LUMPUR, Oct 12 - MetMalaysia issued a thunderstorm warning.",
            PUBLISHED, "fixture", "https://example.test/warning", score=3,
        )
        with (
            patch.object(summary, "evaluate_item", lambda candidate: None),
            patch.object(summary, "should_exclude_item", lambda candidate: False),
        ):
            selected = summary.select_items([item], now)
        self.assertEqual(selected, [])
        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [])
        self.assertEqual(item.expires_at, datetime.fromisoformat("2026-10-12T18:00:00+08:00"))
        observation = summary.build_selection_observation_json([item], [], 1, [], now)
        self.assertEqual(observation["items"][0]["decision_stage"], "expired_time_bound_notice")
        self.assertTrue(summary.build_editorial_candidate_pool_json(1, [], now)["candidate_policy"]["expired_time_bound_notices_removed"])

    def test_notice_remains_candidate_before_deadline(self) -> None:
        now = datetime.fromisoformat("2026-10-12T17:00:00+08:00")
        item = summary.Item("Malay Mail", "feed", TITLE, "warning", PUBLISHED, "fixture", "https://example.test/warning")
        with patch.object(summary, "evaluate_item", lambda candidate: None):
            summary.select_items([item], now)
        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [item])

    def test_uncertain_deadlines_are_not_excluded(self) -> None:
        for title in (
            "Heavy rain expected tomorrow until 6pm",
            "Heavy rain expected on Oct 14 until 6pm",
            "Heavy rain expected on 2026-10-14 until 6pm",
            "Heavy rain expected until late evening",
            "Museum opening hours extended until 6pm",
        ):
            with self.subTest(title=title):
                self.assertIsNone(notice_deadline(title, "", PUBLISHED))

    def test_previous_day_relative_date_is_rejected_but_absolute_date_is_allowed(self) -> None:
        item = {
            "title": TITLE,
            "description": "MetMalaysia issued a warning.",
            "published_at": PUBLISHED.isoformat(),
            "publication_as_of": "2026-10-13T09:37:57+08:00",
        }
        entry = {
            "headline_ja": "マレーシアで本日午後6時まで激しい雨を予報",
            "short_headline_ja": "激しい雨の警報",
            "entry_ja": "MetMalaysiaが警報を発表しました。",
        }
        with self.assertRaisesRegex(ValueError, "stale relative date"):
            validate_editorial_entry_against_source(item, entry)
        entry["headline_ja"] = "マレーシアで10月12日午後6時まで激しい雨を予報"
        validate_editorial_entry_against_source(item, entry)
        self.assertFalse(stale_relative_date(PUBLISHED.isoformat(), PUBLISHED.isoformat(), "本日", TITLE))
        self.assertTrue(stale_relative_date(
            PUBLISHED.isoformat(), item["publication_as_of"], "本日の警報", "Thunderstorm warning today"
        ))


if __name__ == "__main__":
    unittest.main()
