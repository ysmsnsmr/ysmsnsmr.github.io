from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import canonical_hash, validate_public_report
from meta_ads_tracker_recovery_promotion import (
    build_recovery_promotion,
    build_recovery_public_report,
    load_recovery_decisions,
    resolve_recovery_path,
    validate_promotion_directory,
    validate_recovery_promotion,
    write_immutable_promotion,
)


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = json.loads(
    (ROOT / "data/meta_ads_tracker_weekly_recovery/2026-08-28.json").read_text(encoding="utf-8")
)


def approved_decision(event: dict, *, recovery_hash: str = RECOVERY["recoveryHash"]) -> dict:
    return {
        "recoveryHash": recovery_hash,
        "eventId": event["eventId"],
        "revision": event["revision"],
        "sourceFingerprint": event["sourceFingerprint"],
        "originCandidateHash": event["originCandidateHash"],
        "reviewStatus": "approved",
        "reviewer": "human@example.test",
        "reviewedAt": "2026-08-29T03:10:00Z",
        "priority": "standard",
        "businessImpact": {
            "status": "human_assessed",
            "summary": "人間が公式情報を確認した業務影響です。",
            "assessmentSource": "human_review",
        },
        "action": {
            "status": "not_required",
            "summary": "人間が現時点の対応不要を確認しました。",
            "assessmentSource": "human_review",
        },
    }


class MetaAdsRecoveryPromotionTest(unittest.TestCase):
    def decisions(self) -> list[dict]:
        return [approved_decision(event) for event in RECOVERY["items"]]

    def promotion(self) -> dict:
        return build_recovery_promotion(RECOVERY, self.decisions(), "2026-08-29T03:11:00Z")

    def test_promotion_binds_each_approved_event_to_the_exact_recovery(self) -> None:
        promotion = self.promotion()
        self.assertTrue(promotion["publicationEligible"])
        self.assertEqual(promotion["recoveryHash"], RECOVERY["recoveryHash"])
        self.assertEqual(len(promotion["items"]), 2)
        validate_recovery_promotion(promotion, RECOVERY)

    def test_public_report_explicitly_identifies_delayed_recovery(self) -> None:
        report = build_recovery_public_report(self.promotion(), "2026-08-29T03:12:00Z")
        self.assertEqual(report["schemaVersion"], "meta-ads-weekly-index/v2")
        self.assertEqual(report["publication"]["mode"], "delayed_recovery")
        self.assertEqual(report["publication"]["missingPreCutoffDates"], ["2026-08-28"])
        self.assertEqual(len(report["items"]), 2)
        validate_public_report(report)

    def test_promotion_rejects_missing_or_mismatched_human_approval(self) -> None:
        with self.assertRaisesRegex(ContractError, "without matching human approval"):
            build_recovery_promotion(RECOVERY, [], "2026-08-29T03:11:00Z")
        bad = self.decisions()
        bad[0]["originCandidateHash"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "binding mismatch"):
            build_recovery_promotion(RECOVERY, bad, "2026-08-29T03:11:00Z")

    def test_promotion_cannot_be_rewritten_and_directory_validation_rechecks_recovery(self) -> None:
        promotion = self.promotion()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovery_dir = root / "recovery"
            recovery_dir.mkdir()
            (recovery_dir / "2026-08-28.json").write_text(json.dumps(RECOVERY), encoding="utf-8")
            promotion_dir = root / "promotions"
            path = promotion_dir / "2026-08-28.json"
            write_immutable_promotion(path, promotion, RECOVERY)
            self.assertEqual(validate_promotion_directory(promotion_dir, recovery_dir), 1)
            changed = copy.deepcopy(promotion)
            changed["generatedAt"] = "2026-08-29T03:13:00Z"
            changed["promotionHash"] = canonical_hash(changed, "promotionHash")
            with self.assertRaisesRegex(ContractError, "immutable"):
                write_immutable_promotion(path, changed, RECOVERY)
            (recovery_dir / "2026-08-28.json").write_text(json.dumps({**RECOVERY, "recoveryHash": "0" * 64}), encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_promotion_directory(promotion_dir, recovery_dir)

    def test_decision_contract_and_path_resolver_reject_unsafe_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            path.write_text(json.dumps({"schemaVersion": "meta-ads-tracker-recovery-decisions/v1", "items": [approved_decision(RECOVERY["items"][0], recovery_hash="bad")]}), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "SHA-256"):
                load_recovery_decisions(path)
            recovery_dir = Path(directory) / "recovery"
            recovery_dir.mkdir()
            with self.assertRaisesRegex(ContractError, "YYYY-MM-DD"):
                resolve_recovery_path(recovery_dir, "2026-08-28/../../x")


if __name__ == "__main__":
    unittest.main()
