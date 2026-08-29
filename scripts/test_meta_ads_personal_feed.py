from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from meta_ads_tracker_contract import ContractError
from meta_ads_personal_feed import (
    DEFAULT_CONFIG,
    STATE_SCHEMA_VERSION,
    collect,
    collect_and_write,
    extract_items,
    load_config,
    validate_config,
    validate_feed,
)


NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
PPC = """<rss><channel>
<item><title>Meta Ads Manager API update</title><link>https://ppc.land/meta-ads-manager-api-update/?utm_source=test</link><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item>
<item><title>Facebook consumer feature update</title><link>https://ppc.land/facebook-consumer-feature-update/</link></item>
</channel></rss>"""
JON = """<rss><channel>
<item><title>How to review a new Meta Ads setting</title><link>https://www.jonloomer.com/meta-ads-manager-rollout/</link><category>Meta Advertising</category><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item>
<item><title>General marketing notes</title><link>https://www.jonloomer.com/general-marketing-notes/</link><category>Marketing</category></item>
</channel></rss>"""
META = """<rss><channel><item><title>Product update</title><link>https://about.fb.com/news/2026/08/product-update/</link><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item></channel></rss>"""
SDK = json.dumps([{
    "tag_name": "v27.0.0", "name": "v27.0.0", "html_url": "https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v27.0.0", "published_at": "2026-08-29T01:00:00Z", "updated_at": "2026-08-29T02:00:00Z", "draft": False, "prerelease": False,
}])


class PersonalFeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()

    def fetcher(self, *, fail: bool = False, bodies: dict[str, str] | None = None):
        source_bodies = bodies or {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "ppc-land-meta-ads": PPC,
            "jon-loomer-meta-ads": JON,
        }

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            if fail:
                raise URLError("response body must not be retained")
            content_type = "application/json; charset=utf-8" if source["parser"] == "github_releases" else "application/rss+xml; charset=UTF-8"
            return source_bodies[source["id"]], content_type

        return fetch

    def test_config_adds_two_official_and_two_unofficial_public_sources(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        self.assertEqual(set(sources), {"meta-product-news-rss", "meta-business-sdk-releases", "ppc-land-meta-ads", "jon-loomer-meta-ads"})
        self.assertEqual(sources["ppc-land-meta-ads"]["fetchUrl"], "https://ppc.land/rss/")
        self.assertEqual(sources["jon-loomer-meta-ads"]["fetchUrl"], "https://www.jonloomer.com/feed/")
        self.assertEqual(sources["meta-business-sdk-releases"]["parser"], "github_releases")
        self.assertFalse(self.config["policies"]["persistRawResponseBody"])

    def test_config_rejects_insecure_source_and_invalid_source_classification(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["fetchUrl"] = "http://about.fb.com/feed"
        with self.assertRaisesRegex(ContractError, "HTTPS"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["classification"] = "unknown"
        with self.assertRaisesRegex(ContractError, "classification"):
            validate_config(invalid)

    def test_rss_keyword_and_category_filters_only_admit_relevant_unofficial_items(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        ppc = extract_items(sources["ppc-land-meta-ads"], PPC)
        jon = extract_items(sources["jon-loomer-meta-ads"], JON)
        self.assertEqual([item["title"] for item in ppc], ["Meta Ads Manager API update"])
        self.assertEqual(ppc[0]["url"], "https://ppc.land/meta-ads-manager-api-update/")
        self.assertEqual([item["title"] for item in jon], ["How to review a new Meta Ads setting"])
        self.assertEqual(jon[0]["matchEvidence"], ["category:Meta Advertising"])

    def test_first_collection_publishes_provenance_labelled_baseline_without_human_decisions(self) -> None:
        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher())
        self.assertEqual(len(feed["sources"]), 4)
        self.assertEqual(len(feed["items"]), 4)
        self.assertEqual({item["sourceId"] for item in feed["items"]}, {"meta-product-news-rss", "meta-business-sdk-releases", "ppc-land-meta-ads", "jon-loomer-meta-ads"})
        sdk = next(item for item in feed["items"] if item["sourceId"] == "meta-business-sdk-releases")
        self.assertEqual(sdk["updatedDate"], "2026-08-29")
        self.assertTrue(all(item["firstObservedAt"] == "2026-08-29T09:00:00Z" for item in feed["items"]))
        self.assertEqual(set(next_state["sources"]), {source["id"] for source in self.config["sources"]})
        validate_feed(feed, self.config)

    def test_changed_rss_item_updates_in_place_and_keeps_initial_observation(self) -> None:
        initial_state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        _feed, seeded = collect(self.config, initial_state, 1, NOW, self.fetcher())
        changed_bodies = {"meta-product-news-rss": META, "meta-business-sdk-releases": SDK, "ppc-land-meta-ads": PPC.replace("API update", "API update revised"), "jon-loomer-meta-ads": JON}
        feed, state = collect(self.config, seeded, 1, NOW.replace(day=30), self.fetcher(bodies=changed_bodies))
        ppc = next(item for item in feed["items"] if item["sourceId"] == "ppc-land-meta-ads")
        self.assertEqual(ppc["title"], "Meta Ads Manager API update revised")
        self.assertEqual(ppc["firstObservedAt"], "2026-08-29T09:00:00Z")
        self.assertEqual(ppc["lastObservedAt"], "2026-08-30T09:00:00Z")
        self.assertEqual(len(state["sources"]["ppc-land-meta-ads"]["items"]), 1)

    def test_fetch_failure_preserves_existing_state_and_public_feed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            output_path = root / "feed.json"
            state_bytes = b'{"schemaVersion":"meta-ads-personal-feed-state/v1","updatedAt":null,"sources":{}}\n'
            output_bytes = b'{"schemaVersion":"meta-ads-personal-feed/v1","generatedAt":null,"sources":[],"items":[]}\n'
            state_path.write_bytes(state_bytes)
            output_path.write_bytes(output_bytes)
            with self.assertRaises(URLError):
                collect_and_write(DEFAULT_CONFIG, state_path, output_path, 1, now=NOW, fetch_body=self.fetcher(fail=True))
            self.assertEqual(state_path.read_bytes(), state_bytes)
            self.assertEqual(output_path.read_bytes(), output_bytes)


if __name__ == "__main__":
    unittest.main()
