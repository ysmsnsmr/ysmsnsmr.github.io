#!/usr/bin/env python3
import json
import unittest
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "malaysia_editorial_entry_semantic_fidelity.json"
)


class EditorialEntrySemanticFidelityFixtureTest(unittest.TestCase):
    def test_fixture_has_five_distinct_meaning_preservation_cases(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["schema_version"],
            "malaysia-editorial-entry-semantic-fidelity/v1",
        )
        cases = payload["cases"]
        self.assertEqual(len(cases), 5)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual(len({case["source"]["link"] for case in cases}), len(cases))

        required_expected_keys = {
            "subject",
            "target",
            "direction",
            "scope",
            "certainty",
            "forbidden_meanings",
        }
        for case in cases:
            self.assertTrue(case["source"]["title"])
            self.assertTrue(case["source"]["description"])
            self.assertTrue(case["source"]["link"])
            self.assertEqual(set(case["expected"]), required_expected_keys)
            self.assertTrue(case["expected"]["subject"])
            self.assertTrue(case["expected"]["target"])
            self.assertTrue(case["expected"]["scope"])
            self.assertTrue(case["expected"]["forbidden_meanings"])

    def test_fixture_covers_observed_entity_scope_direction_and_certainty_failures(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cases = {case["id"]: case for case in payload["cases"]}

        self.assertIn("米伊", cases["us_iran_entity_fidelity"]["expected"]["forbidden_meanings"])
        self.assertIn("全面通行止め", cases["penang_lane_closure_scope"]["expected"]["forbidden_meanings"])
        self.assertEqual(
            cases["ringgit_mixed_direction"]["expected"]["direction"]["against_us_dollar"],
            "下落",
        )
        self.assertIn("運休", cases["rapid_kl_incident_service_normal"]["expected"]["forbidden_meanings"])
        self.assertEqual(cases["ringgit_forecast_certainty"]["expected"]["certainty"], "forecast")


if __name__ == "__main__":
    unittest.main()
