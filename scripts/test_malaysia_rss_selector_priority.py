#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import malaysia_rss_summary as summary


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "malaysia_selector_priority_bands.json"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=summary.MYT)


def make_item(case: dict[str, object]) -> summary.Item:
    case_id = str(case["id"])
    return summary.Item(
        "Test",
        "Test Feed",
        str(case["title"]),
        str(case.get("description") or ""),
        NOW,
        "raw",
        f"https://example.test/{case_id}",
    )


class MalaysiaSelectorPriorityBandsTest(unittest.TestCase):
    def test_golden_cases_select_expected_items_and_tiers(self) -> None:
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]
        items = [make_item(case) for case in cases]
        selected = summary.select_items(items, NOW)
        selected_by_link = {item.link: item for item in selected}

        for case in cases:
            with self.subTest(case=case["id"]):
                item = next(item for item in items if item.link.endswith(str(case["id"])))
                is_selected = item.link in selected_by_link
                self.assertEqual(is_selected, bool(case["expect_selected"]))
                if is_selected:
                    self.assertEqual(
                        selected_by_link[item.link].selection_priority_tier,
                        case["expect_tier"],
                    )

    def test_urgent_item_is_not_displaced_by_direct_items_at_total_cap(self) -> None:
        direct_items = [
            summary.Item(
                "Test",
                "Test Feed",
                f"Rapid KL commuter update {number}",
                "Public transport information for commuters.",
                NOW,
                "raw",
                f"https://example.test/direct-{number}",
            )
            for number in range(15)
        ]
        urgent_item = summary.Item(
            "Test",
            "Test Feed",
            "Haze reaches hazardous level",
            "Haze air quality is hazardous and schools may close.",
            NOW,
            "raw",
            "https://example.test/urgent-haze",
        )

        selected = summary.select_items(direct_items + [urgent_item], NOW)

        self.assertIn(urgent_item, selected)
        self.assertEqual(summary.LAST_SELECTION_STATS["cap_excluded_count"], 1)
        self.assertEqual(
            summary.LAST_SELECTION_STATS["highest_cap_excluded"]["tier"],
            "direct_life_impact",
        )


if __name__ == "__main__":
    unittest.main()
