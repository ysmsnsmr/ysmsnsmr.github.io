#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

import enrich_malaysia_selected_items_with_body as body


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures/malaysia_jev_candidate_evidence.json"


class MalaysiaCandidateEvidenceFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_is_observation_only_and_has_expected_comparison_sections(self) -> None:
        self.assertEqual(self.fixture["schema_version"], "malaysia-jev-candidate-evidence/v1")
        self.assertFalse(self.fixture["source_artifact"]["production_effect"])
        self.assertFalse(self.fixture["comparison_contract"]["production_effect"])
        self.assertEqual(len(self.fixture["candidate_pool_cases"]), 2)
        self.assertEqual(len(self.fixture["body_evidence_cases"]), 2)
        self.assertEqual(len(self.fixture["translation_meaning_cases"]), 3)
        self.assertEqual(len(self.fixture["cross_source_event_cases"]), 1)

    def test_same_topic_key_case_has_an_added_jev_candidate(self) -> None:
        case = self.fixture["candidate_pool_cases"][0]
        self.assertEqual(case["input_items"][0]["canonical_key"], case["input_items"][1]["canonical_key"])
        self.assertEqual(case["expected"]["dropped_by_topic_key"], [])
        self.assertEqual(
            case["expected"]["added_to_jev_candidate_links"],
            ["https://example.test/weather/johor"],
        )

    def test_exact_url_drop_identifies_the_article_and_reason(self) -> None:
        case = self.fixture["candidate_pool_cases"][1]
        self.assertEqual(
            case["expected"]["dropped_by_exact_url"],
            [{
                "title": "Same article, older feed entry",
                "link": "https://example.test/article/1",
                "reason": "exact_url_duplicate_older_entry",
            }],
        )

    def test_body_evidence_policy_uses_clean_text_not_topic_words(self) -> None:
        case = self.fixture["body_evidence_cases"][0]
        actual_policy, actual_reason = body.classify_body_excerpt_policy(case["input"])
        self.assertEqual(actual_policy, case["expected"]["body_excerpt_policy"])
        self.assertEqual(actual_reason, case["expected"]["body_excerpt_reason"])
        self.assertEqual(case["expected"]["selected_context_source"], "article_body")
        for phrase in case["expected"]["summary_evidence_contains"]:
            self.assertIn(phrase, case["input"]["body_evidence_excerpt"])

    def test_empty_body_evidence_keeps_rss_context(self) -> None:
        case = self.fixture["body_evidence_cases"][1]
        actual_policy, actual_reason = body.classify_body_excerpt_policy(case["input"])
        self.assertEqual(actual_policy, case["expected"]["body_excerpt_policy"])
        self.assertEqual(actual_reason, case["expected"]["body_excerpt_reason"])

    def test_translation_cases_keep_observed_error_and_expected_meaning(self) -> None:
        cases = {case["case_id"]: case for case in self.fixture["translation_meaning_cases"]}

        telecom = cases["telecom_outage_is_not_power_outage"]
        self.assertIn("停電", telecom["observed_output"]["headline_ja"])
        self.assertIn("telecommunications", telecom["expected_meaning"]["topic"])
        self.assertIn("electrical power outage", telecom["expected_meaning"]["must_not_imply"])

        haze = cases["haze_is_not_fog"]
        self.assertIn("濃霧", haze["observed_output"]["headline_ja"])
        self.assertIn("ヘイズ", haze["expected_meaning"]["preferred_japanese_terms"])
        self.assertEqual(haze["expected_meaning"]["locations"]["Kanowit"], "remained very unhealthy at noon")

        mortar = cases["uxo_mortar_is_not_mortar_belt"]
        self.assertIn("モーターベルト弾", mortar["observed_output"]["entry_ja"])
        self.assertIn("迫撃砲弾", mortar["expected_meaning"]["preferred_japanese_terms"])
        self.assertEqual(mortar["expected_meaning"]["approximate_diameter_mm"], 60)

    def test_cross_source_duplicate_fixture_preserves_both_citations_for_one_event(self) -> None:
        case = self.fixture["cross_source_event_cases"][0]
        reports = case["reports"]
        self.assertEqual({report["source"] for report in reports}, {"Malay Mail", "Astro Awani"})
        self.assertTrue(all(report["candidate_pool_selected"] for report in reports))
        self.assertEqual(len({report["link"] for report in reports}), 2)
        self.assertEqual(case["shared_event"]["event_date"], "2026-09-21")
        self.assertEqual(case["expected"]["event_group_count"], 1)
        self.assertEqual(case["expected"]["display_entry_count"], 1)
        self.assertCountEqual(
            case["expected"]["preserve_source_links"],
            [report["link"] for report in reports],
        )


if __name__ == "__main__":
    unittest.main()
