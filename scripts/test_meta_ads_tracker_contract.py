#!/usr/bin/env python3
import copy
import json
import sys
import unittest
from pathlib import Path
from urllib.error import URLError


sys.path.insert(0, str(Path(__file__).resolve().parent))

from meta_ads_tracker_contract import (
    ContractError,
    DEFAULT_FIXTURE_DIRECTORY,
    load_and_validate_fixture,
    load_and_validate_source_config,
    validate_source_config,
)
from meta_ads_tracker_probe_sources import probe_source, probe_sources


class MetaAdsTrackerContractTest(unittest.TestCase):
    def test_source_config_has_only_official_public_or_disabled_auth_sources(self) -> None:
        config = load_and_validate_source_config()

        self.assertTrue(config["policies"]["officialSourcesOnly"])
        self.assertFalse(config["policies"]["bypassLoginOrConsent"])
        self.assertFalse(config["policies"]["persistRawResponseBody"])
        self.assertEqual(
            [source["id"] for source in config["sources"] if source["enabled"]],
            ["meta-product-news-rss", "meta-business-sdk-releases"],
        )
        self.assertEqual(
            [source["id"] for source in config["sources"] if source["access"] == "login_required"],
            ["meta-ads-manager-help", "meta-audience-help"],
        )

    def test_login_required_source_cannot_be_enabled(self) -> None:
        config = load_and_validate_source_config()
        invalid = copy.deepcopy(config)
        invalid["sources"][1]["enabled"] = True

        with self.assertRaisesRegex(ContractError, "login-required"):
            validate_source_config(invalid)

    def test_five_anonymous_fixtures_validate_and_cover_the_required_states(self) -> None:
        fixture_paths = sorted(DEFAULT_FIXTURE_DIRECTORY.glob("*.json"))
        fixtures = [load_and_validate_fixture(path) for path in fixture_paths]

        self.assertEqual(
            {fixture["fixture"]["name"] for fixture in fixtures},
            {
                "empty-week",
                "normal-week",
                "high-priority",
                "long-and-unknown-dates",
                "filtered-no-results",
            },
        )
        self.assertEqual(
            {fixture["fixture"]["state"] for fixture in fixtures},
            {
                "empty_week",
                "normal_week",
                "high_priority",
                "long_and_unknown_dates",
                "filtered_no_results",
            },
        )
        normal_week = next(fixture for fixture in fixtures if fixture["fixture"]["name"] == "normal-week")
        self.assertEqual(
            {item["changeType"] for item in normal_week["items"]},
            {"new_url", "content_changed", "sdk_release"},
        )

    def test_unknown_dates_and_assessments_cannot_contain_inferred_values(self) -> None:
        fixture_path = DEFAULT_FIXTURE_DIRECTORY / "long-and-unknown-dates.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["items"][0]["effectiveDate"]["value"] = "2026-08-20"

        with self.assertRaisesRegex(ContractError, "must be null"):
            load_and_validate_fixture_payload(fixture)

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["items"][0]["businessImpact"]["summary"] = "推測した影響"
        with self.assertRaisesRegex(ContractError, "must not contain an inferred assessment"):
            load_and_validate_fixture_payload(fixture)

    def test_public_probe_keeps_disabled_help_sources_out_of_monitoring(self) -> None:
        config = load_and_validate_source_config()

        def fake_headers(url: str, method: str, timeout: float) -> tuple[int, str, dict[str, str]]:
            if "github" in url:
                return 200, url, {"Content-Type": "application/json; charset=utf-8", "ETag": "sdk"}
            if "about.fb.com" in url:
                return 200, url, {"Content-Type": "application/rss+xml; charset=UTF-8", "ETag": "rss"}
            return 200, "https://www.facebook.com/login/", {"Content-Type": "text/html; charset=utf-8"}

        report = probe_sources(config, 1.0, fake_headers)

        self.assertFalse(report["responseBodyStored"])
        self.assertEqual(
            report["summary"]["eligibleSourceIds"],
            ["meta-product-news-rss", "meta-business-sdk-releases"],
        )
        self.assertEqual(
            report["summary"]["disabledAuthenticationSourceIds"],
            ["meta-ads-manager-help", "meta-audience-help"],
        )

    def test_probe_failure_preserves_existing_publication(self) -> None:
        source = load_and_validate_source_config()["sources"][0]

        def offline_headers(url: str, method: str, timeout: float) -> tuple[int, str, dict[str, str]]:
            raise URLError("offline")

        result = probe_source(source, 1.0, offline_headers)

        self.assertFalse(result["reachable"])
        self.assertEqual(result["publicationAction"], "keep_published_content_unchanged")


def load_and_validate_fixture_payload(payload: object) -> dict[str, object]:
    from meta_ads_tracker_contract import validate_weekly_fixture

    return validate_weekly_fixture(payload)


if __name__ == "__main__":
    unittest.main()
