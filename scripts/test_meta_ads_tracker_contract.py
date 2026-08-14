#!/usr/bin/env python3
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError


sys.path.insert(0, str(Path(__file__).resolve().parent))

from meta_ads_tracker_contract import (
    CANONICAL_FIXTURES,
    ContractError,
    DEFAULT_FIXTURE_DIRECTORY,
    load_and_validate_canonical_fixtures,
    load_and_validate_fixture,
    load_and_validate_source_config,
    validate_fixture_json_schema,
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
        fixtures = load_and_validate_canonical_fixtures()

        self.assertEqual(len(fixtures), 5)
        self.assertEqual(
            {fixture["fixture"]["name"]: fixture["fixture"]["state"] for fixture in fixtures},
            CANONICAL_FIXTURES,
        )
        normal_week = next(fixture for fixture in fixtures if fixture["fixture"]["name"] == "normal-week")
        self.assertEqual(
            {item["changeType"] for item in normal_week["items"]},
            {"new_url", "content_changed", "sdk_release"},
        )

    def test_json_schema_is_executed_for_every_fixture(self) -> None:
        fixture = json.loads((DEFAULT_FIXTURE_DIRECTORY / "empty-week.json").read_text(encoding="utf-8"))
        validate_fixture_json_schema(fixture)

        invalid = copy.deepcopy(fixture)
        invalid["unexpected"] = True
        with self.assertRaisesRegex(ContractError, "violates JSON Schema"):
            validate_fixture_json_schema(invalid)

    def test_fixture_filename_and_canonical_set_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            shutil.copytree(DEFAULT_FIXTURE_DIRECTORY, temporary_root / "fixtures")
            fixtures_root = temporary_root / "fixtures"
            (fixtures_root / "normal-week.json").rename(fixtures_root / "renamed.json")

            with self.assertRaisesRegex(ContractError, "exactly match the canonical set"):
                load_and_validate_canonical_fixtures(fixtures_root)
            with self.assertRaisesRegex(ContractError, "filename must match"):
                load_and_validate_fixture(fixtures_root / "renamed.json")

    def test_fixture_items_must_reference_enabled_public_sources_with_matching_type(self) -> None:
        fixture = json.loads((DEFAULT_FIXTURE_DIRECTORY / "normal-week.json").read_text(encoding="utf-8"))

        invalid = copy.deepcopy(fixture)
        invalid["items"][0]["sourceId"] = "unknown-source"
        with self.assertRaisesRegex(ContractError, "enabled public configured source"):
            load_and_validate_fixture_payload(invalid)

        invalid = copy.deepcopy(fixture)
        invalid["items"][0]["sourceId"] = "meta-ads-manager-help"
        with self.assertRaisesRegex(ContractError, "enabled public configured source"):
            load_and_validate_fixture_payload(invalid)

        invalid = copy.deepcopy(fixture)
        invalid["items"][2]["sourceId"] = "meta-product-news-rss"
        with self.assertRaisesRegex(ContractError, "sdk_release requires an sdk_release source"):
            load_and_validate_fixture_payload(invalid)

    def test_unknown_dates_and_assessments_cannot_contain_inferred_values(self) -> None:
        fixture_path = DEFAULT_FIXTURE_DIRECTORY / "long-and-unknown-dates.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["items"][0]["effectiveDate"]["value"] = "2026-08-20"

        with self.assertRaisesRegex(ContractError, "violates JSON Schema"):
            load_and_validate_fixture_payload(fixture)

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["items"][0]["businessImpact"]["summary"] = "推測した影響"
        with self.assertRaisesRegex(ContractError, "violates JSON Schema"):
            load_and_validate_fixture_payload(fixture)

    def test_public_probe_keeps_disabled_help_sources_out_of_monitoring(self) -> None:
        config = load_and_validate_source_config()
        requested_urls: list[str] = []

        def fake_headers(url: str, method: str, timeout: float) -> tuple[int, str, dict[str, str]]:
            requested_urls.append(url)
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
        self.assertEqual(len(requested_urls), 2)
        self.assertEqual(
            [source["requestedMethod"] for source in report["sources"] if not source["reachable"]],
            ["SKIPPED", "SKIPPED"],
        )
        self.assertEqual(report["summary"]["failedSourceIds"], [])

        feasibility_report = probe_sources(config, 1.0, fake_headers, include_disabled=True)
        self.assertEqual(len(requested_urls), 6)
        self.assertEqual(
            [source["requestedMethod"] for source in feasibility_report["sources"]],
            ["HEAD", "HEAD", "HEAD", "HEAD"],
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
