from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_gate_b import _automatic_source_ids, _load_json, evaluate, load_config, validate_record
from meta_ads_tracker_secondary_beta_status import build_status, validate_status


ROOT = Path(__file__).resolve().parents[1]


class SecondaryBetaPublicStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "config/meta_ads_secondary_shadow_gate_b.json")
        self.source_ids = _automatic_source_ids(ROOT / "config/meta_ads_secondary_shadow_sources.json")
        self.record = validate_record(
            _load_json(ROOT / "data/meta_ads_tracker_secondary_shadow_gate_b.json", "Gate B review record"),
            automatic_source_ids=self.source_ids,
        )

    def test_status_is_derived_from_gate_b_and_never_contains_signals(self) -> None:
        status = build_status(self.config, self.record, automatic_source_ids=self.source_ids)
        self.assertEqual(status["gateB"]["status"], evaluate(self.config, self.record, automatic_source_ids=self.source_ids)["status"])
        self.assertEqual(status["gateB"]["status"], "BLOCK")
        self.assertFalse(status["secondarySignalsVisible"])
        self.assertFalse(status["officialCandidateIntegration"])
        self.assertFalse(status["publicationEligible"])
        self.assertNotIn("signals", status)
        self.assertEqual(validate_status(status), status)

    def test_status_rejects_signal_or_publication_escape_hatches(self) -> None:
        status = build_status(self.config, self.record, automatic_source_ids=self.source_ids)
        invalid = copy.deepcopy(status)
        invalid["secondarySignalsVisible"] = True
        with self.assertRaisesRegex(ContractError, "must not expose"):
            validate_status(invalid)
        invalid = copy.deepcopy(status)
        invalid["signals"] = []
        with self.assertRaisesRegex(ContractError, "unsupported fields"):
            validate_status(invalid)

    def test_committed_document_is_exactly_the_derived_status(self) -> None:
        expected = json.dumps(build_status(self.config, self.record, automatic_source_ids=self.source_ids), ensure_ascii=False, indent=2) + "\n"
        self.assertEqual((ROOT / "meta-ads-updates/secondary-beta.json").read_text(encoding="utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
