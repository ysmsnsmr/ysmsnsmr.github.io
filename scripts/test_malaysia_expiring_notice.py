#!/usr/bin/env python3
from datetime import datetime
import sys
import types
import unittest
from unittest.mock import patch

import malaysia_rss_summary as summary
from malaysia_expiring_notice import (
    klang_valley_area_in_body, notice_deadline, publication_rejection_reason, stale_relative_date,
)
from render_malaysia_news_with_groq import validate_editorial_entry_against_source


TITLE = "Heavy rain, gusty winds expected across nine states, Putrajaya and Labuan until 6pm"
PUBLISHED = datetime.fromisoformat("2026-10-12T16:11:45+08:00")


class ExpiringNoticeTests(unittest.TestCase):
    def test_deadline_is_anchored_to_article_date_not_publication_date(self) -> None:
        deadline = notice_deadline(TITLE, "MetMalaysia issued a thunderstorm warning.", PUBLISHED)
        self.assertEqual(deadline, datetime.fromisoformat("2026-10-12T18:00:00+08:00"))
        self.assertEqual(notice_deadline(TITLE, "The warning remains in effect until 6pm.", PUBLISHED), deadline)

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

    def test_next_day_deadline_is_resolved_and_rechecked_on_publication_day(self) -> None:
        title = "Heavy rain expected tomorrow until 6pm"
        self.assertEqual(notice_deadline(title, "", PUBLISHED), datetime.fromisoformat("2026-10-13T18:00:00+08:00"))
        self.assertIsNone(publication_rejection_reason(
            title, "", PUBLISHED, datetime.fromisoformat("2026-10-13T09:00:00+08:00")
        ))
        self.assertEqual(publication_rejection_reason(
            title, "", PUBLISHED, datetime.fromisoformat("2026-10-14T09:00:00+08:00")
        ), "expired_time_bound_notice")

    def test_uncertain_deadlines_are_not_resolved(self) -> None:
        for title in (
            "Heavy rain expected on Oct 14 until 6pm",
            "Heavy rain expected on 2026-10-14 until 6pm",
            "Heavy rain expected until late evening",
            "Museum opening hours extended until 6pm",
        ):
            with self.subTest(title=title):
                self.assertIsNone(notice_deadline(title, "", PUBLISHED))

    def test_weather_requires_verified_current_day_deadline(self) -> None:
        morning = datetime.fromisoformat("2026-10-14T07:26:00+08:00")
        self.assertEqual(publication_rejection_reason(
            "MetMalaysia warns of severe storms across peninsula and East Malaysia",
            "KUALA LUMPUR, Oct 13 — A thunderstorm warning was issued.",
            datetime.fromisoformat("2026-10-13T16:50:14+08:00"), morning,
        ), "weather_not_for_publication_day")
        self.assertEqual(publication_rejection_reason(
            "Thunderstorm warning for Klang Valley today", "No end time stated.", morning, morning,
        ), "unverified_weather_validity")
        self.assertIsNone(publication_rejection_reason(
            "Heavy rain expected across KL until 6pm", "MetMalaysia warning", morning, morning,
        ))
        self.assertIsNone(publication_rejection_reason(
            "Damansara storm: car damaged at toll plaza", "A thunderstorm hit the area yesterday.",
            datetime.fromisoformat("2026-10-13T20:00:00+08:00"), morning,
        ))

    def test_previous_day_haze_action_needs_target_day_and_klang_valley_evidence(self) -> None:
        published = datetime.fromisoformat("2026-10-13T19:38:57+08:00")
        morning = datetime.fromisoformat("2026-10-14T07:26:00+08:00")
        self.assertEqual(publication_rejection_reason(
            "Haze: Kedah schools to operate as usual tomorrow as API readings remain moderate",
            "ALOR SETAR, Oct 13 — All schools in Kedah will operate as usual tomorrow.", published, morning,
        ), "haze_action_area_unverified")
        self.assertEqual(publication_rejection_reason(
            "Fadhlina: Schools in Johor, Melaka, Negeri Sembilan and nine districts to close tomorrow as haze lingers",
            "KUALA LUMPUR, Oct 13 — Schools in Johor, Melaka and Negeri Sembilan will stay closed tomorrow.",
            published, morning,
        ), "haze_action_area_unverified")
        self.assertIsNone(publication_rejection_reason(
            "Haze: schools in Hulu Langat and Sepang to close tomorrow",
            "KUALA LUMPUR, Oct 13 — The closure affects two districts.", published, morning,
        ))
        self.assertEqual(publication_rejection_reason(
            "Haze: schools in Hulu Langat and Sepang to close tomorrow", "", published,
            datetime.fromisoformat("2026-10-15T07:26:00+08:00"),
        ), "haze_action_not_for_publication_day")

    def test_haze_action_is_filtered_from_legacy_and_jev_pools(self) -> None:
        morning = datetime.fromisoformat("2026-10-14T07:26:00+08:00")
        item = summary.Item(
            "Malay Mail", "feed", "Haze: Kedah schools to operate as usual tomorrow",
            "ALOR SETAR, Oct 13 — Schools remain open tomorrow.",
            datetime.fromisoformat("2026-10-13T19:38:57+08:00"), "fixture", "https://example.test/kedah",
        )
        with patch.object(summary, "evaluate_item", lambda candidate: None):
            self.assertEqual(summary.select_items([item], morning), [])
        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [])
        observation = summary.build_selection_observation_json([item], [], 1, [], morning)
        self.assertEqual(observation["items"][0]["decision_stage"], "haze_action_area_unverified")

    def test_multiregion_haze_action_is_kept_when_body_names_klang_valley(self) -> None:
        morning = datetime.fromisoformat("2026-10-14T07:26:00+08:00")
        item = summary.Item(
            "Malay Mail", "feed",
            "Schools in Johor, Melaka, Negeri Sembilan and nine districts to close tomorrow as haze lingers",
            "KUALA LUMPUR, Oct 13 — Schools in three states and nine districts will close tomorrow.",
            datetime.fromisoformat("2026-10-13T15:24:07+08:00"), "fixture",
            "https://www.malaymail.com/news/malaysia/fixture",
        )
        self.assertFalse(klang_valley_area_in_body("KUALA LUMPUR, Oct 13 — Schools in Kedah close."))
        self.assertTrue(klang_valley_area_in_body("Schools under Hulu Langat and Sepang district offices will close."))
        with (
            patch.object(summary, "evaluate_item", lambda candidate: None),
            patch.object(summary, "verify_haze_area_from_body", return_value=True) as verify,
        ):
            summary.select_items([item], morning)
        verify.assert_called_once_with(item)
        self.assertEqual(summary.LAST_EDITORIAL_CANDIDATE_POOL, [item])
        self.assertTrue(summary.item_json(item)["haze_area_verified_from_body"])

    def test_ambiguous_haze_fetch_is_limited_to_known_source_host(self) -> None:
        item = summary.Item(
            "Malay Mail", "feed", "Haze: schools close tomorrow", "Schools will close tomorrow.",
            PUBLISHED, "fixture", "https://www.malaymail.com/news/malaysia/fixture",
        )
        fake_newspaper = types.SimpleNamespace(Article=object(), Config=object())
        with (
            patch.dict(sys.modules, {"newspaper": fake_newspaper}),
            patch("enrich_malaysia_selected_items_with_body.fetch_article_body", return_value={
                "body_excerpt": "Schools under Hulu Langat and Sepang offices will close."
            }) as fetch,
        ):
            self.assertTrue(summary.verify_haze_area_from_body(item))
        fetch.assert_called_once()
        item.link = "https://example.test/news"
        self.assertFalse(summary.verify_haze_area_from_body(item))

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
        self.assertFalse(stale_relative_date(
            PUBLISHED.isoformat(), item["publication_as_of"], "昨日の被害", "A thunderstorm hit yesterday"
        ))

    def test_previous_day_haze_summary_needs_absolute_target_date(self) -> None:
        item = {
            "title": "Haze: schools in Hulu Langat to close tomorrow",
            "description": "KUALA LUMPUR, Oct 13 — Schools will close tomorrow due to haze.",
            "published_at": "2026-10-13T19:38:57+08:00",
            "publication_as_of": "2026-10-14T07:26:00+08:00",
        }
        entry = {
            "headline_ja": "Hulu Langatの学校がhazeで休校",
            "short_headline_ja": "hazeで休校",
            "entry_ja": "Hulu Langatの学校は休校します。",
        }
        with self.assertRaisesRegex(ValueError, "missing absolute target date"):
            validate_editorial_entry_against_source(item, entry)
        entry["entry_ja"] = "Hulu Langatの学校は10月14日に休校します。"
        validate_editorial_entry_against_source(item, entry)
        entry["entry_ja"] = "Hulu Langatの学校は明日休校します。"
        with self.assertRaisesRegex(ValueError, "stale relative date"):
            validate_editorial_entry_against_source(item, entry)
        item["haze_area_verified_from_body"] = True
        entry["entry_ja"] = "Hulu Langatの学校は10月14日に休校します。"
        with self.assertRaisesRegex(ValueError, "missing Klang Valley body evidence"):
            validate_editorial_entry_against_source(item, entry)
        item["body_evidence_excerpt"] = "Schools under Hulu Langat and Sepang offices will close."
        validate_editorial_entry_against_source(item, entry)
        entry["entry_ja"] = "Hulu Langatの学校は2026-10-14に休校します。"
        validate_editorial_entry_against_source(item, entry)


if __name__ == "__main__":
    unittest.main()
