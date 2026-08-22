from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from meta_ads_tracker_collect import collect
from meta_ads_tracker_contract import (
    ContractError,
    governed_automated_sources,
    load_and_validate_source_config,
    load_and_validate_source_governance,
    validate_source_governance,
)


class MetaAdsSourceGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_source_config()
        self.governance = load_and_validate_source_governance(source_config=self.config)

    def test_legacy_grace_covers_only_the_two_existing_automatic_sources(self) -> None:
        allowed = governed_automated_sources(self.config, self.governance, datetime(2026, 9, 4).date())
        self.assertEqual(
            [source["id"] for source in allowed],
            ["meta-product-news-rss", "meta-business-sdk-releases"],
        )
        records = {record["sourceId"]: record for record in self.governance["sources"]}
        self.assertEqual(records["meta-ads-manager-help"]["status"], "manual_only")
        self.assertEqual(records["meta-audience-help"]["status"], "manual_only")

    def test_deadline_stops_all_collection_before_any_fetch_or_write(self) -> None:
        fetches: list[str] = []

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            fetches.append(source["id"])
            return "", "application/rss+xml"

        state = {"sources": {}}
        with self.assertRaisesRegex(ContractError, "blocked by source governance"):
            collect(
                self.config,
                state,
                1,
                datetime(2026, 9, 5, tzinfo=timezone.utc),
                fetch,
                self.governance,
            )
        self.assertEqual(fetches, [])
        self.assertEqual(state, {"sources": {}})

    def test_new_source_cannot_bypass_approval_with_a_legacy_record(self) -> None:
        config = copy.deepcopy(self.config)
        source = copy.deepcopy(config["sources"][0])
        source["id"] = "new-official-source"
        source["name"] = "New official source"
        source["fetchUrl"] = "https://new.example.test/feed"
        source["sourceUrl"] = "https://new.example.test/feed"
        source["transport"]["allowedFetchHosts"] = ["new.example.test"]
        config["sources"].append(source)

        governance = copy.deepcopy(self.governance)
        governance["sources"].append(
            {
                "sourceId": "new-official-source",
                "status": "legacy_pending_review",
                "reviewDeadline": "2026-09-05",
                "rationale": "Attempted bypass.",
            }
        )
        with self.assertRaisesRegex(ContractError, "only existing approved source IDs"):
            validate_source_governance(governance, config)

    def test_approved_record_requires_human_evidence_and_survives_the_legacy_deadline(self) -> None:
        governance = copy.deepcopy(self.governance)
        for source_id in ("meta-product-news-rss", "meta-business-sdk-releases"):
            record = next(item for item in governance["sources"] if item["sourceId"] == source_id)
            record.clear()
            record.update(
                {
                    "sourceId": source_id,
                    "status": "approved",
                    "approvedAt": "2026-09-04T09:00:00+08:00",
                    "approvedBy": "human-reviewer",
                    "evidenceUrl": "https://github.com/ysmsnsmr/ysmsnsmr.github.io/pull/8",
                    "rationale": "Human review approved scheduled collection.",
                }
            )
        validated = validate_source_governance(governance, self.config)
        allowed = governed_automated_sources(self.config, validated, datetime(2026, 9, 5).date())
        self.assertEqual([source["id"] for source in allowed], ["meta-product-news-rss", "meta-business-sdk-releases"])

    def test_prohibited_source_must_be_disabled_in_the_same_configuration_change(self) -> None:
        config = copy.deepcopy(self.config)
        governance = copy.deepcopy(self.governance)
        record = governance["sources"][0]
        record.clear()
        record.update(
            {
                "sourceId": "meta-product-news-rss",
                "status": "prohibited",
                "rationale": "Collection is prohibited pending policy clarification.",
            }
        )
        with self.assertRaisesRegex(ContractError, "must be disabled"):
            validate_source_governance(governance, config)
        config["sources"][0]["enabled"] = False
        validate_source_governance(governance, config)


if __name__ == "__main__":
    unittest.main()
