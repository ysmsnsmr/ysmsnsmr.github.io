from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse

from meta_ads_tracker_assemble_weekly import assemble_weekly, write_immutable_weekly
from meta_ads_tracker_collect import collect
from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_groq import _schema_error
from meta_ads_tracker_publication import (
    build_public_report,
    canonical_hash,
    load_decisions,
    validate_candidate,
    validate_public_report,
    validate_weekly_candidate,
)
from publish_meta_ads_tracker import resolve_weekly_path


FIXTURES = json.loads(
    (Path(__file__).resolve().parent / "fixtures/meta_ads_tracker_delta_cases.json").read_text(encoding="utf-8")
)
MONDAY = datetime(2026, 8, 17, 0, 15, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class MetaAdsDemoReportTest(unittest.TestCase):
    def test_demo_report_is_valid_and_explicitly_synthetic(self) -> None:
        report = json.loads((ROOT / "meta-ads-updates/demo-latest.json").read_text(encoding="utf-8"))
        validate_public_report(report, load_and_validate_source_config(ROOT / "config/meta_ads_official_sources.json"))
        self.assertEqual(len(report["items"]), 4)
        self.assertEqual({item["sourceId"] for item in report["items"]}, {"meta-product-news-rss", "meta-business-sdk-releases"})
        self.assertEqual(sum(item["priority"] == "high" for item in report["items"]), 1)
        self.assertTrue(all("デモ" in item["title"] for item in report["items"]))
        self.assertTrue(all("デモ用の架空評価" in item["businessImpact"]["summary"] for item in report["items"]))
        self.assertTrue(all(urlparse(item["officialUrl"]).scheme == "https" for item in report["items"]))


def fetcher(config: dict, rss: str, sdk: str, *, fail: bool = False):
    bodies = {
        config["sources"][0]["fetchUrl"]: rss,
        config["sources"][3]["fetchUrl"]: sdk,
    }

    def fetch(source: dict, _timeout: float) -> tuple[str, str]:
        if fail:
            raise URLError("fixture fetch failure")
        url = source["fetchUrl"]
        return bodies[url], "application/json" if "api.github.com" in url else "application/rss+xml"

    return fetch


def approved_decision(weekly: dict, event: dict, *, reviewed_at: str = "2026-08-21T10:00:00Z") -> dict:
    return {
        "eventId": event["eventId"],
        "revision": event["revision"],
        "sourceFingerprint": event["sourceFingerprint"],
        "originCandidateHash": event["originCandidateHash"],
        "weeklyHash": weekly["weeklyHash"],
        "reviewStatus": "approved",
        "reviewer": "human@example.test",
        "reviewedAt": reviewed_at,
        "priority": "high",
        "businessImpact": {
            "status": "human_assessed",
            "summary": "人間が公式情報を確認した業務影響です。",
            "assessmentSource": "human_review",
        },
        "action": {
            "status": "review_required",
            "summary": "対象設定を人間が確認します。",
            "assessmentSource": "human_review",
        },
    }


class MetaAdsDeltaContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_source_config()

    def baseline(self) -> tuple[dict, dict]:
        return collect(
            self.config,
            {"sources": {}},
            1,
            MONDAY,
            fetcher(self.config, FIXTURES["initialRss"], FIXTURES["initialSdk"]),
        )

    def test_initial_baseline_seeds_everything_and_emits_zero_events(self) -> None:
        candidate, state = self.baseline()
        self.assertEqual(candidate["baseline"]["mode"], "seeded")
        self.assertEqual(candidate["items"], [])
        self.assertEqual(state["baselineCutoffAt"], candidate["generatedAt"])
        self.assertTrue(state["sources"]["meta-product-news-rss"]["items"])
        self.assertTrue(state["sources"]["meta-business-sdk-releases"]["items"])

    def test_no_change_after_baseline_emits_zero_events(self) -> None:
        _, state = self.baseline()
        candidate, _ = collect(
            self.config,
            state,
            1,
            MONDAY + timedelta(days=1),
            fetcher(self.config, FIXTURES["initialRss"], FIXTURES["initialSdk"]),
        )
        self.assertEqual(candidate["baseline"]["mode"], "active")
        self.assertEqual(candidate["items"], [])

    def test_body_addition_creates_a_new_content_revision(self) -> None:
        _, state = self.baseline()
        candidate, _ = collect(
            self.config,
            state,
            1,
            MONDAY + timedelta(days=1),
            fetcher(self.config, FIXTURES["bodyAdditionRss"], FIXTURES["initialSdk"]),
        )
        self.assertEqual([item["changeType"] for item in candidate["items"]], ["content_changed"])
        self.assertEqual(candidate["items"][0]["revision"], candidate["items"][0]["sourceFingerprint"])

    def test_new_rss_url_creates_new_url_event(self) -> None:
        _, state = self.baseline()
        candidate, _ = collect(
            self.config,
            state,
            1,
            MONDAY + timedelta(days=3),
            fetcher(self.config, FIXTURES["newRss"], FIXTURES["initialSdk"]),
        )
        self.assertEqual([item["changeType"] for item in candidate["items"]], ["new_url"])

    def test_duplicate_sdk_release_is_not_a_new_event(self) -> None:
        _, state = self.baseline()
        candidate, _ = collect(
            self.config,
            state,
            1,
            MONDAY + timedelta(days=1),
            fetcher(self.config, FIXTURES["initialRss"], FIXTURES["initialSdk"]),
        )
        self.assertFalse(any(item["changeType"] == "sdk_release" for item in candidate["items"]))

    def test_processing_epoch_counts_tombstones_and_sdk_revisions(self) -> None:
        _, state = self.baseline()
        updated_sdk = FIXTURES["initialSdk"].replace("First release", "Corrected release notes")
        candidate, state = collect(
            self.config, state, 1, MONDAY + timedelta(days=1),
            fetcher(self.config, "<rss><channel /></rss>", updated_sdk),
        )
        self.assertEqual(candidate["schemaVersion"], "meta-ads-tracker-candidates/v3")
        self.assertEqual(candidate["processingEpoch"]["status"], "completed")
        self.assertEqual(candidate["summary"]["tombstonedItems"], 1)
        self.assertEqual(candidate["summary"]["changedEvents"], 1)
        self.assertEqual(candidate["items"][0]["changeType"], "sdk_release")
        self.assertTrue(any("tombstonedAt" in item for item in state["sources"]["meta-product-news-rss"]["items"].values()))

    def test_fetch_failure_returns_no_candidate_or_state_mutation(self) -> None:
        _, state = self.baseline()
        original = copy.deepcopy(state)
        with self.assertRaises(URLError):
            collect(
                self.config,
                state,
                1,
                MONDAY + timedelta(days=1),
                fetcher(self.config, FIXTURES["initialRss"], FIXTURES["initialSdk"], fail=True),
            )
        self.assertEqual(state, original)

    def test_candidate_hash_and_complete_schema_are_enforced(self) -> None:
        candidate, _ = self.baseline()
        invalid = copy.deepcopy(candidate)
        invalid["week"].pop("label")
        invalid["candidateHash"] = canonical_hash(invalid, "candidateHash")
        with self.assertRaisesRegex(ContractError, "JSON Schema"):
            validate_candidate(invalid)


class MetaAdsWeeklyAndApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_source_config()

    def weekly(self) -> dict:
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
            candidate, state = collect(
                self.config,
                state,
                1,
                MONDAY + timedelta(days=offset),
                fetcher(self.config, rss, FIXTURES["initialSdk"]),
            )
            candidates.append((f"202608{17 + offset}T001500Z-{offset}.json", candidate))
        return assemble_weekly(
            candidates,
            datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 9, 5, tzinfo=timezone.utc),
        )

    def test_weekly_retains_distinct_revisions_and_deduplicates_exact_events(self) -> None:
        weekly = self.weekly()
        validate_weekly_candidate(weekly)
        existing_subjects = [item for item in weekly["items"] if item["officialUrl"].endswith("/existing/")]
        self.assertEqual(len(existing_subjects), 2)
        self.assertEqual(len({item["revision"] for item in existing_subjects}), 2)
        self.assertEqual(len(weekly["candidateRefs"]), 5)

    def test_weekly_requires_successful_candidate_for_every_weekday(self) -> None:
        weekly = self.weekly()
        with self.assertRaisesRegex(ContractError, "missing"):
            assemble_weekly(
                [(reference["fileName"], self._candidate_from_reference(weekly, reference)) for reference in weekly["candidateRefs"][:-1]],
                datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 8, 21, 9, 5, tzinfo=timezone.utc),
            )

    def test_weekly_ignores_legacy_candidate_outside_its_window_but_validates_current_week(self) -> None:
        weekly = self.weekly()
        candidates = [
            (reference["fileName"], self._candidate_from_reference(weekly, reference))
            for reference in weekly["candidateRefs"]
        ]
        legacy = {
            "schemaVersion": "meta-ads-tracker-candidates/v2",
            "generatedAt": "2026-08-16T01:58:08Z",
        }
        assembled = assemble_weekly(
            [("20260816T015808Z-legacy.json", legacy), *candidates],
            datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 9, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(len(assembled["candidateRefs"]), 5)

        invalid_current = copy.deepcopy(candidates[0][1])
        invalid_current["schemaVersion"] = "meta-ads-tracker-candidates/v2"
        invalid_current.pop("processingEpoch")
        with self.assertRaisesRegex(ContractError, "20260817T001500Z-0.json.*processingEpoch"):
            assemble_weekly(
                [
                    ("20260816T015808Z-legacy.json", legacy),
                    ("20260817T001500Z-0.json", invalid_current),
                    *candidates[1:],
                ],
                datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 8, 21, 9, 5, tzinfo=timezone.utc),
            )

    def _candidate_from_reference(self, weekly: dict, reference: dict) -> dict:
        # Reconstruct a schema-valid empty daily candidate for date-coverage testing.
        generated = reference["generatedAt"]
        payload = {
            "schemaVersion": "meta-ads-tracker-candidates/v3",
            "candidateHash": "",
            "generatedAt": generated,
            "baseline": {"mode": "active", "cutoffAt": weekly["candidateRefs"][0]["generatedAt"]},
            "week": weekly["week"],
            "processingEpoch": {"id": "epoch-20260817t001500z", "startedAt": generated, "completedAt": generated, "status": "completed"},
            "sourceRuns": [
                {"sourceId": source["id"], "status": "success", "startedAt": generated, "completedAt": generated, "parsedItems": 0, "newEvents": 0, "changedEvents": 0, "unchangedItems": 0, "tombstonedItems": 0}
                for source in self.config["sources"] if source["enabled"] and source["access"] == "public"
            ],
            "summary": {"parsedItems": 0, "newEvents": 0, "changedEvents": 0, "unchangedItems": 0, "tombstonedItems": 0},
            "items": [],
        }
        payload["candidateHash"] = canonical_hash(payload, "candidateHash")
        return payload

    def test_decision_is_bound_to_exact_event_and_old_weeks_do_not_block(self) -> None:
        weekly = self.weekly()
        event = weekly["items"][0]
        current = approved_decision(weekly, event)
        old = copy.deepcopy(current)
        old["weeklyHash"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            decision_path = Path(directory) / "decisions.json"
            decision_path.write_text(
                json.dumps({"schemaVersion": "meta-ads-tracker-decisions/v2", "items": [old, current]}),
                encoding="utf-8",
            )
            loaded = load_decisions(decision_path)
        self.assertEqual(len(loaded), 2)
        report = build_public_report(weekly, loaded, "2026-08-21T10:05:00Z")
        self.assertEqual(len(report["items"]), 1)
        validate_public_report(report)

        stale = copy.deepcopy(current)
        stale["revision"] = "1" * 64
        with self.assertRaisesRegex(ContractError, "binding mismatch"):
            build_public_report(weekly, [stale], "2026-08-21T10:05:00Z")

    def test_immutable_weekly_file_rejects_changed_content(self) -> None:
        weekly = self.weekly()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-08-21.json"
            write_immutable_weekly(path, weekly)
            write_immutable_weekly(path, weekly)
            changed = copy.deepcopy(weekly)
            changed["generatedAt"] = "2026-08-21T09:06:00Z"
            changed["weeklyHash"] = canonical_hash(changed, "weeklyHash")
            with self.assertRaisesRegex(ContractError, "immutable"):
                write_immutable_weekly(path, changed)

    def test_cutoff_date_resolver_rejects_injection_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ContractError, "YYYY-MM-DD"):
                resolve_weekly_path(Path(directory), "2026-08-21;echo-pwned")
            with self.assertRaisesRegex(ContractError, "YYYY-MM-DD"):
                resolve_weekly_path(Path(directory), "../../2026-08-21")

    def test_groq_contract_has_evidence_and_rejects_action_judgments(self) -> None:
        source = "Official title The feature rolls out gradually."
        valid = {
            "summaryJa": "段階的に提供されます。",
            "summaryEvidence": "The feature rolls out gradually.",
            "effectiveDate": {"value": None, "evidenceExcerpt": None},
            "rollout": {"value": "gradually", "evidenceExcerpt": "rolls out gradually"},
            "targets": {"value": None, "evidenceExcerpt": None},
        }
        self.assertEqual(_schema_error(valid, source), "")
        invalid = {**valid, "actionStatus": "action_required"}
        self.assertEqual(_schema_error(invalid, source), "root_shape")


if __name__ == "__main__":
    unittest.main()
