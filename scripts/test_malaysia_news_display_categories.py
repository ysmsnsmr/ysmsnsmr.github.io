#!/usr/bin/env python3
import unittest

from malaysia_news_display_categories import (
    LIVING_UPDATES,
    SOCIETY_ECONOMY,
    display_category_for_item,
    display_category_for_jev,
    display_category_for_legacy,
)


class MalaysiaNewsDisplayCategoriesTests(unittest.TestCase):
    def test_jev_decisions_map_to_the_public_categories(self) -> None:
        self.assertEqual(display_category_for_jev("direct_life_impact"), LIVING_UPDATES)
        self.assertEqual(display_category_for_jev("public_information"), SOCIETY_ECONOMY)

    def test_legacy_categories_remain_readable_in_the_new_display(self) -> None:
        self.assertEqual(display_category_for_legacy("【速報】"), LIVING_UPDATES)
        self.assertEqual(display_category_for_legacy("【生活インパクト】"), LIVING_UPDATES)
        self.assertEqual(display_category_for_legacy("【知っておくと得】"), SOCIETY_ECONOMY)

    def test_explicit_display_category_takes_priority_for_routed_items(self) -> None:
        item = {
            "category": "【知っておくと得】",
            "display_category": LIVING_UPDATES,
        }
        self.assertEqual(display_category_for_item(item), LIVING_UPDATES)


if __name__ == "__main__":
    unittest.main()
