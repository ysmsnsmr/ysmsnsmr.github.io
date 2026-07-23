#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_term_normalization import normalize_malaysia_terms_in_text


class TermNormalizationTest(unittest.TestCase):
    def test_does_not_expand_oil_price_substrings(self) -> None:
        item = {"title": "Fuel market update", "description": ""}

        normalized = normalize_malaysia_terms_in_text(
            "原油価格と油価は市場の文脈によって異なります。", item
        )

        self.assertEqual(normalized, "原油価格と油価は市場の文脈によって異なります。")

    def test_keeps_source_gated_ecoss_normalization(self) -> None:
        item = {
            "title": "eCOSS cooking oil price stabilisation scheme continues",
            "description": "",
        }

        normalized = normalize_malaysia_terms_in_text(
            "食用油価格格安定化制度(eCOSS)の対象店舗を確認する。", item
        )

        self.assertEqual(normalized, "eCOSS（食用油価格安定化制度）の対象店舗を確認する。")


if __name__ == "__main__":
    unittest.main()
