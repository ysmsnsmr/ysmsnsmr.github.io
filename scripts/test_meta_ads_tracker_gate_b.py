from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_gate_b import evaluate, load_config, validate_config, validate_record
from meta_ads_tracker_secondary_shadow import load_and_validate_config


ROOT = Path(__file__).resolve().parents[1]


def automatic_sources() -> set[str]:
    return {
        source["id"]
        for source in load_and_validate_config(ROOT / "config/meta_ads_secondary_shadow_sources.json")["sources"]
        if source["enabled"]
    }


def baseline_generation() -> str:
    return load_and_validate_config(ROOT / "config/meta_ads_secondary_shadow_sources.json")["policies"]["baselineGeneration"]


def review(source_id: str, index: int, observed_at: datetime, *, outcome: str = "not_useful", minutes: int = 10) -> dict:
    return {
        "reviewId": f"review-{index}",
        "baselineGeneration": baseline_generation(),
        "sourceId": source_id,
        "signalId": f"{source_id}-signal-{index}",
        "observedAt": observed_at.isoformat().replace("+00:00", "Z"),
        "reviewedAt": (observed_at + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "workflowRunId": str(40000000000 + index),
        "stateBranchCommit": "a" * 40,
        "artifactSha256": "b" * 64,
        "outcome": outcome,
        "officialVerification": "official_source_found" if outcome == "useful" else "not_found",
        "officialReferenceUrl": "https://about.fb.com/news/example/" if outcome == "useful" else None,
        "minutesSpent": minutes,
        "notes": None,
    }


def ready_record() -> dict:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    sources = sorted(automatic_sources())
    reviews = []
    for index in range(10):
        reviews.append(
            review(
                sources[index % len(sources)],
                index + 1,
                start + timedelta(days=index),
                outcome="useful" if index < 3 else "not_useful",
                minutes=5,
            )
        )
    return {
        "schemaVersion": "meta-ads-secondary-shadow-gate-b-record/v2",
        "baselineGeneration": baseline_generation(),
        "baseline": {
            "cutoffAt": (start - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "workflowRunId": "39999999999",
            "stateBranchCommit": "c" * 40,
            "artifactSha256": "d" * 64,
        },
        "observationWindow": {
            "startedAt": start.isoformat().replace("+00:00", "Z"),
            "endedAt": (start + timedelta(days=14)).isoformat().replace("+00:00", "Z"),
        },
        "reviews": reviews,
        "findings": [],
    }


class GateBTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "config/meta_ads_secondary_shadow_gate_b.json")
        self.source_ids = automatic_sources()
        self.baseline_generation = baseline_generation()

    def test_empty_committed_ledger_is_valid_but_not_ready(self) -> None:
        record = json.loads((ROOT / "data/meta_ads_tracker_secondary_shadow_gate_b.json").read_text())
        validated = validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        result = evaluate(self.config, validated, automatic_source_ids=self.source_ids)
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("observation window is not declared", result["reasons"])
        self.assertIn("reviews 0/10", result["reasons"])

    def test_complete_evidence_passes_all_fixed_criteria(self) -> None:
        record = validate_record(ready_record(), automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        result = evaluate(self.config, record, automatic_source_ids=self.source_ids)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence"]["reviewCount"], 10)
        self.assertEqual(result["evidence"]["usefulReviewCount"], 3)
        self.assertEqual(result["evidence"]["reviewsByAutomaticSource"], {
            "jon-loomer-meta-ads": 5,
            "ppc-land-meta-ads": 5,
        })

    def test_duplicate_signal_or_unknown_source_cannot_inflate_evidence(self) -> None:
        duplicate = ready_record()
        duplicate["reviews"][1]["signalId"] = duplicate["reviews"][0]["signalId"]
        duplicate["reviews"][1]["sourceId"] = duplicate["reviews"][0]["sourceId"]
        with self.assertRaisesRegex(ContractError, "only once"):
            validate_record(duplicate, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        unknown = ready_record()
        unknown["reviews"][0]["sourceId"] = "anagrams-meta-ads"
        with self.assertRaisesRegex(ContractError, "not an automatic"):
            validate_record(unknown, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)

    def test_open_fix_or_dlq_and_excess_weekly_time_block_readiness(self) -> None:
        record = ready_record()
        record["findings"] = [{
            "findingId": "parser-fix",
            "category": "fix",
            "status": "open",
            "openedAt": "2026-08-10T00:00:00Z",
            "resolvedAt": None,
            "summary": "The parser needs a source-specific correction.",
        }]
        record["reviews"][0]["minutesSpent"] = 60
        record = validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        result = evaluate(self.config, record, automatic_source_ids=self.source_ids)
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("unresolved findings: parser-fix", result["reasons"])
        self.assertTrue(any("review time" in reason for reason in result["reasons"]))

    def test_config_cannot_relax_the_agreed_gate(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["criteria"]["minimumReviewsTotal"] = 1
        with self.assertRaisesRegex(ContractError, "must remain 10"):
            validate_config(invalid)

    def test_prior_baseline_reviews_cannot_satisfy_the_rss_observation_window(self) -> None:
        record = ready_record()
        record["baselineGeneration"] = "html-baseline-2026-08"
        with self.assertRaisesRegex(ContractError, "active shadow baseline generation"):
            validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        record = ready_record()
        record["reviews"][0]["baselineGeneration"] = "html-baseline-2026-08"
        with self.assertRaisesRegex(ContractError, "active shadow baseline generation"):
            validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)

    def test_rss_window_requires_a_seed_artifact_and_cannot_precede_its_cutoff(self) -> None:
        record = ready_record()
        record["baseline"]["artifactSha256"] = None
        with self.assertRaisesRegex(ContractError, "set all provenance"):
            validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)
        record = ready_record()
        record["baseline"]["cutoffAt"] = "2026-08-02T00:00:00Z"
        with self.assertRaisesRegex(ContractError, "observationWindow.startedAt"):
            validate_record(record, automatic_source_ids=self.source_ids, baseline_generation=self.baseline_generation)


if __name__ == "__main__":
    unittest.main()
