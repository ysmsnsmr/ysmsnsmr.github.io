from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_secondary_shadow import (
    DEFAULT_CONFIG,
    collect,
    collect_and_write,
    extract_signals,
    load_and_validate_config,
    validate_state,
    validate_config,
)


NOW = datetime(2026, 8, 22, 2, 0, tzinfo=timezone.utc)
PPC_HTML = """
<html><body>
  <a href="/meta-marketing-api-update/?utm_source=newsletter">Meta Marketing API update</a>
  <a href="https://evil.example.test/meta-ads">Meta Ads on an untrusted host</a>
  <a href="/about/">About PPC Land</a>
</body></html>
"""
JON_HTML = "<html><body><a href='/meta-ads-manager-rollout/'>Meta Ads Manager rollout</a></body></html>"


class SecondaryShadowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_config()

    def fetcher(self, *, fail: bool = False):
        bodies = {
            "ppc-land-meta-ads": PPC_HTML,
            "jon-loomer-meta-ads": JON_HTML,
        }

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            if fail:
                raise URLError("secondary response body must never be retained")
            return bodies[source["id"]], "text/html"

        return fetch

    def test_config_declares_an_isolated_non_public_shadow_boundary(self) -> None:
        self.assertEqual(self.config["policies"], {
            "publicationEligible": False,
            "officialCandidateIntegration": False,
            "persistRawResponseBody": False,
            "requireHumanOfficialVerification": True,
            "stateBranch": "automation/meta-ads-shadow-state",
        })
        automatic = [source["id"] for source in self.config["sources"] if source["enabled"]]
        self.assertEqual(automatic, ["ppc-land-meta-ads", "jon-loomer-meta-ads"])
        anagrams = next(source for source in self.config["sources"] if source["id"] == "anagrams-meta-ads")
        self.assertFalse(anagrams["enabled"])
        self.assertEqual(anagrams["collectionMode"], "manual_only")

    def test_config_rejects_public_or_official_integration_escape_hatches(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["policies"]["publicationEligible"] = True
        with self.assertRaisesRegex(ContractError, "never be public"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["collectionMode"] = "manual_only"
        with self.assertRaisesRegex(ContractError, "must match enabled"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["transport"]["allowedContentHosts"] = ["127.0.0.1"]
        with self.assertRaisesRegex(ContractError, "DNS hostname"):
            validate_config(invalid)

    def test_extractor_keeps_only_same_site_metadata_and_strips_tracking(self) -> None:
        source = self.config["sources"][0]
        signals = extract_signals(source, PPC_HTML)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["url"], "https://ppc.land/meta-marketing-api-update/")
        self.assertEqual(signals[0]["title"], "Meta Marketing API update")
        self.assertEqual(signals[0]["matchedKeywords"], ["meta", "marketing api"])
        self.assertNotIn("evil.example.test", json.dumps(signals))

    def test_initial_baseline_emits_no_signals_then_new_metadata_is_unverified_only(self) -> None:
        baseline, state = collect(self.config, {"sources": {}}, 1, NOW, self.fetcher())
        self.assertEqual(baseline["baseline"]["mode"], "seeded")
        self.assertEqual(baseline["signals"], [])
        self.assertTrue(state["sources"]["ppc-land-meta-ads"]["items"])
        active, _ = collect(self.config, state, 1, NOW.replace(day=23), self.fetcher())
        self.assertEqual(active["baseline"]["mode"], "active")
        self.assertEqual(active["summary"]["signals"], 0)

        changed_bodies = {
            "ppc-land-meta-ads": PPC_HTML + "<a href='/new-meta-ad-format/'>New Meta ad format</a>",
            "jon-loomer-meta-ads": JON_HTML,
        }
        next_report, _ = collect(
            self.config,
            state,
            1,
            NOW.replace(day=23),
            lambda source, _timeout: (changed_bodies[source["id"]], "text/html"),
        )
        self.assertEqual(next_report["summary"]["signals"], 1)
        signal = next_report["signals"][0]
        self.assertEqual(signal["verificationStatus"], "unverified")
        self.assertFalse(signal["publicationEligible"])
        self.assertFalse(next_report["officialCandidateIntegration"])
        self.assertFalse(next_report["responseBodyStored"])
        self.assertNotIn("<a href", json.dumps(next_report))

    def test_any_fetch_failure_preserves_existing_state_and_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            output = root / "report.json"
            original_state = (
                b'{"schemaVersion":"meta-ads-secondary-shadow-state/v1",'
                b'"updatedAt":"2026-08-22T02:00:00Z",'
                b'"baselineCutoffAt":"2026-08-22T02:00:00Z","sources":{}}\n'
            )
            original_output = b'{"existing":"shadow output"}\n'
            state.write_bytes(original_state)
            output.write_bytes(original_output)
            with self.assertRaises(URLError):
                collect_and_write(DEFAULT_CONFIG, state, output, 1, now=NOW, fetch_body=self.fetcher(fail=True))
            self.assertEqual(state.read_bytes(), original_state)
            self.assertEqual(output.read_bytes(), original_output)

    def test_invalid_state_or_content_type_stops_before_or_during_collection(self) -> None:
        with self.assertRaisesRegex(ContractError, "schemaVersion"):
            validate_state({"schemaVersion": "wrong", "updatedAt": "2026-08-22T00:00:00Z", "baselineCutoffAt": "2026-08-22T00:00:00Z", "sources": {}}, self.config)
        with self.assertRaisesRegex(ContractError, "unexpected response"):
            collect(self.config, {"sources": {}}, 1, NOW, lambda _source, _timeout: ("<html></html>", "application/json"))


if __name__ == "__main__":
    unittest.main()
