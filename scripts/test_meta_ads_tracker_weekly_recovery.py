from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meta_ads_tracker_collect import collect
from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_publication import canonical_hash
from meta_ads_tracker_weekly_recovery import (
    build_preflight,
    build_recovery,
    validate_preflight,
    validate_recovery,
    validate_recovery_directory,
    write_immutable_recovery,
)


FIXTURES = json.loads(
    (Path(__file__).resolve().parent / "fixtures/meta_ads_tracker_delta_cases.json").read_text(encoding="utf-8")
)
MONDAY = datetime(2026, 8, 24, 0, 15, tzinfo=timezone.utc)
FRIDAY_CUTOFF = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)


def fetcher(config: dict, rss: str, sdk: str):
    bodies = {
        config["sources"][0]["fetchUrl"]: rss,
        config["sources"][3]["fetchUrl"]: sdk,
    }

    def fetch(source: dict, _timeout: float) -> tuple[str, str]:
        return bodies[source["fetchUrl"]], "application/json" if source["kind"] == "sdk_release" else "application/rss+xml"

    return fetch


class MetaAdsWeeklyRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_source_config()

    def candidates(self, *, friday_at: datetime = FRIDAY_CUTOFF - timedelta(hours=1)) -> list[tuple[str, dict]]:
        state: dict = {"sources": {}}
        candidates: list[tuple[str, dict]] = []
        rss_by_day = [
            FIXTURES["initialRss"],
            FIXTURES["bodyAdditionRss"],
            FIXTURES["initialRss"],
            FIXTURES["newRss"],
            FIXTURES["newRss"],
        ]
        for offset, rss in enumerate(rss_by_day):
            collected_at = friday_at if offset == 4 else MONDAY + timedelta(days=offset)
            candidate, state = collect(
                self.config,
                state,
                1,
                collected_at,
                fetcher(self.config, rss, FIXTURES["initialSdk"]),
            )
            candidates.append((f"{collected_at.strftime('%Y%m%dT%H%M%SZ')}-{offset}.json", candidate))
        return candidates

    def test_preflight_recommends_backup_only_for_a_missing_friday_inside_the_window(self) -> None:
        report = build_preflight(
            self.candidates()[:-1],
            datetime(2026, 8, 28, 8, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(report["status"], "backup_recommended")
        self.assertEqual(report["missingDates"], ["2026-08-28"])
        self.assertTrue(report["backup"]["eligible"])
        validate_preflight(report)

    def test_preflight_never_recommends_backup_for_an_earlier_missing_day_or_after_cutoff(self) -> None:
        candidates = self.candidates()
        report = build_preflight(candidates[1:], datetime(2026, 8, 28, 8, 30, tzinfo=timezone.utc))
        self.assertEqual(report["status"], "recovery_required")
        self.assertFalse(report["backup"]["eligible"])

        after_cutoff = build_preflight(candidates, datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(after_cutoff["status"], "ready")
        self.assertFalse(after_cutoff["backup"]["eligible"])

    def test_recovery_records_late_candidate_as_non_public_evidence(self) -> None:
        recovery = build_recovery(
            self.candidates(friday_at=datetime(2026, 8, 28, 11, 25, tzinfo=timezone.utc)),
            FRIDAY_CUTOFF,
            datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(recovery["missingPreCutoffDates"], ["2026-08-28"])
        self.assertFalse(recovery["publicationEligible"])
        self.assertTrue(recovery["requiresHumanDisposition"])
        self.assertEqual(len(recovery["candidateRefs"]), 5)
        self.assertEqual(recovery["candidateRefs"][-1]["timing"], "late")
        self.assertGreater(len(recovery["items"]), 0)
        validate_recovery(recovery)

    def test_recovery_rejects_complete_normal_coverage(self) -> None:
        with self.assertRaisesRegex(ContractError, "not allowed"):
            build_recovery(self.candidates(), FRIDAY_CUTOFF, datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc))

    def test_recovery_is_immutable_and_directory_validation_is_safe_when_empty(self) -> None:
        recovery = build_recovery(
            self.candidates(friday_at=datetime(2026, 8, 28, 11, 25, tzinfo=timezone.utc)),
            FRIDAY_CUTOFF,
            datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(validate_recovery_directory(root / "missing"), 0)
            path = root / "2026-08-28.json"
            write_immutable_recovery(path, recovery)
            self.assertEqual(validate_recovery_directory(root), 1)
            changed = copy.deepcopy(recovery)
            changed["generatedAt"] = "2026-08-28T12:01:00Z"
            changed["recoveryHash"] = canonical_hash(changed, "recoveryHash")
            with self.assertRaisesRegex(ContractError, "immutable"):
                write_immutable_recovery(path, changed)


if __name__ == "__main__":
    unittest.main()
