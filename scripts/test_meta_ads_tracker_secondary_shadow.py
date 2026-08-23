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
PPC_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Meta Ads Manager API update</title><link>https://ppc.land/meta-ads-manager-api-update/?utm_source=newsletter</link></item>
  <item><title>Microsoft Advertising account update</title><link>https://ppc.land/microsoft-advertising-account-update/</link></item>
  <item><title>Facebook consumer feature update</title><link>https://ppc.land/facebook-consumer-feature-update/</link></item>
  <item><title>Threads consumer feature update</title><link>https://ppc.land/threads-consumer-feature-update/</link></item>
  <item><title>Meta Ads on an untrusted host</title><link>https://evil.example.test/meta-ads/</link></item>
</channel></rss>"""
JON_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item><title>How to review a new Meta Ads setting</title><link>https://www.jonloomer.com/meta-ads-manager-rollout/</link><category>Meta Advertising</category></item>
  <item><title>General marketing notes</title><link>https://www.jonloomer.com/general-marketing-notes/</link><category>Marketing</category></item>
</channel></rss>"""


class SecondaryShadowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_and_validate_config()

    def fetcher(self, *, fail: bool = False, bodies: dict[str, str] | None = None):
        source_bodies = bodies or {
            "ppc-land-meta-ads": PPC_RSS,
            "jon-loomer-meta-ads": JON_RSS,
        }

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            if fail:
                raise URLError("secondary response body must never be retained")
            content_type = "text/xml; charset=utf-8" if source["id"] == "ppc-land-meta-ads" else "application/rss+xml; charset=UTF-8"
            return source_bodies[source["id"]], content_type

        return fetch

    def test_config_declares_an_isolated_non_public_rss_shadow_boundary(self) -> None:
        self.assertEqual(self.config["policies"], {
            "publicationEligible": False,
            "officialCandidateIntegration": False,
            "persistRawResponseBody": False,
            "requireHumanOfficialVerification": True,
            "stateBranch": "automation/meta-ads-shadow-state",
            "baselineGeneration": "rss-migration-2026-08",
        })
        sources = {source["id"]: source for source in self.config["sources"]}
        self.assertEqual(sources["ppc-land-meta-ads"]["fetchUrl"], "https://ppc.land/rss/")
        self.assertEqual(sources["ppc-land-meta-ads"]["parser"], "rss")
        self.assertEqual(sources["jon-loomer-meta-ads"]["fetchUrl"], "https://www.jonloomer.com/feed/")
        self.assertEqual(sources["jon-loomer-meta-ads"]["parser"], "rss")
        self.assertFalse(sources["anagrams-meta-ads"]["enabled"])
        self.assertEqual(sources["anagrams-meta-ads"]["collectionMode"], "manual_only")

    def test_config_rejects_public_escape_hatches_and_invalid_rss_contracts(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["policies"]["publicationEligible"] = True
        with self.assertRaisesRegex(ContractError, "never be public"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["expectedContentTypes"] = ["text/html"]
        with self.assertRaisesRegex(ContractError, "must match its parser"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["match"] = {"kind": "rss_category", "categories": ["Meta Advertising"]}
        invalid["sources"][0]["parser"] = "html"
        invalid["sources"][0]["expectedContentTypes"] = ["text/html"]
        invalid["sources"][0]["transport"].pop("maxFeedItems")
        with self.assertRaisesRegex(ContractError, "requires an rss parser"):
            validate_config(invalid)

    def test_rss_extractors_use_metadata_and_source_specific_match_contracts(self) -> None:
        ppc = extract_signals(self.config["sources"][0], PPC_RSS)
        self.assertEqual(ppc, [{
            "url": "https://ppc.land/meta-ads-manager-api-update/",
            "title": "Meta Ads Manager API update",
            "matchEvidence": ["keyword:meta", "keyword:ads"],
            "fingerprint": ppc[0]["fingerprint"],
        }])
        jon = extract_signals(self.config["sources"][1], JON_RSS)
        self.assertEqual(len(jon), 1)
        self.assertEqual(jon[0]["url"], "https://www.jonloomer.com/meta-ads-manager-rollout/")
        self.assertEqual(jon[0]["matchEvidence"], ["category:Meta Advertising"])
        serialised = json.dumps(ppc + jon)
        self.assertNotIn("Microsoft", serialised)
        self.assertNotIn("consumer", serialised)
        self.assertNotIn("Threads", serialised)
        self.assertNotIn("evil.example.test", serialised)
        self.assertNotIn("<item>", serialised)

    def test_rss_reseed_replaces_legacy_html_state_for_both_sources_and_emits_zero_signals(self) -> None:
        legacy_state = {
            "schemaVersion": "meta-ads-secondary-shadow-state/v1",
            "updatedAt": "2026-08-22T00:00:00Z",
            "baselineCutoffAt": "2026-08-22T00:00:00Z",
            "sources": {
                "ppc-land-meta-ads": {"items": {"https://ppc.land/old/": {"fingerprint": "a" * 64, "lastSeenAt": "2026-08-22T00:00:00Z"}}},
                "jon-loomer-meta-ads": {"items": {"https://www.jonloomer.com/old/": {"fingerprint": "b" * 64, "lastSeenAt": "2026-08-22T00:00:00Z"}}},
            },
        }
        report, state = collect(self.config, legacy_state, 1, NOW, self.fetcher())
        self.assertEqual(report["baseline"], {
            "mode": "seeded",
            "cutoffAt": "2026-08-22T02:00:00Z",
            "generation": "rss-migration-2026-08",
            "resetReason": "legacy_html_state",
            "sourceIds": ["ppc-land-meta-ads", "jon-loomer-meta-ads"],
        })
        self.assertEqual(report["signals"], [])
        self.assertEqual(set(state["sources"]), {"ppc-land-meta-ads", "jon-loomer-meta-ads"})
        self.assertNotIn("https://ppc.land/old/", state["sources"]["ppc-land-meta-ads"]["items"])
        self.assertNotIn("https://www.jonloomer.com/old/", state["sources"]["jon-loomer-meta-ads"]["items"])

    def test_active_rss_state_emits_only_new_unverified_metadata(self) -> None:
        _baseline, state = collect(self.config, {"sources": {}}, 1, NOW, self.fetcher())
        active, _ = collect(self.config, state, 1, NOW.replace(day=23), self.fetcher())
        self.assertEqual(active["summary"]["signals"], 0)
        changed = {
            "ppc-land-meta-ads": PPC_RSS.replace("</channel>", "<item><title>Instagram Ads API update</title><link>https://ppc.land/instagram-ads-api-update/</link></item></channel>"),
            "jon-loomer-meta-ads": JON_RSS.replace("</channel>", "<item><title>New setting</title><link>https://www.jonloomer.com/new-meta-setting/</link><category>Meta Advertising</category></item></channel>"),
        }
        report, _ = collect(self.config, state, 1, NOW.replace(day=23), self.fetcher(bodies=changed))
        self.assertEqual(report["summary"]["signals"], 2)
        self.assertTrue(all(signal["baselineGeneration"] == "rss-migration-2026-08" for signal in report["signals"]))
        self.assertTrue(all(signal["verificationStatus"] == "unverified" for signal in report["signals"]))
        self.assertTrue(all(signal["publicationEligible"] is False for signal in report["signals"]))
        self.assertFalse(report["officialCandidateIntegration"])
        self.assertFalse(report["responseBodyStored"])
        self.assertNotIn("<item>", json.dumps(report))

    def test_unsafe_xml_and_feed_item_overflow_fail_closed(self) -> None:
        source = self.config["sources"][0]
        with self.assertRaisesRegex(ContractError, "invalid or unsafe RSS"):
            extract_signals(source, "<!DOCTYPE rss [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><rss><channel><item><title>&xxe;</title><link>https://ppc.land/x/</link></item></channel></rss>")
        items = "".join(
            f"<item><title>General marketing note {index}</title><link>https://ppc.land/{index}/</link></item>"
            for index in range(101)
        )
        with self.assertRaisesRegex(ContractError, "RSS item limit"):
            extract_signals(source, f"<rss><channel>{items}</channel></rss>")

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

    def test_invalid_state_or_content_type_stops_collection(self) -> None:
        with self.assertRaisesRegex(ContractError, "schemaVersion"):
            validate_state({"schemaVersion": "wrong", "updatedAt": "2026-08-22T00:00:00Z", "baselineCutoffAt": "2026-08-22T00:00:00Z", "sources": {}}, self.config)
        with self.assertRaisesRegex(ContractError, "unexpected response"):
            collect(self.config, {"sources": {}}, 1, NOW, lambda _source, _timeout: ("<rss/>", "application/json"))


if __name__ == "__main__":
    unittest.main()
