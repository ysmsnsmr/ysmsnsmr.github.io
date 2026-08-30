from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from meta_ads_tracker_contract import ContractError
from meta_ads_personal_feed import (
    DEFAULT_CONFIG,
    FEED_SCHEMA_VERSION,
    PRESENTATION_SCHEMA_VERSION,
    STATE_SCHEMA_VERSION,
    _presentation_from_environment,
    collect,
    collect_and_write,
    extract_items,
    load_config,
    validate_config,
    validate_feed,
    validate_state,
)
from meta_ads_personal_feed_presentation import PresentationError


NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
JON = """<rss><channel>
<item><title>How to review a new Meta Ads setting</title><link>https://www.jonloomer.com/meta-ads-manager-rollout/</link><description>Review the new setting before changing a campaign.</description><category>Meta Advertising</category><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item>
<item><title>General marketing notes</title><link>https://www.jonloomer.com/general-marketing-notes/</link><category>Marketing</category></item>
</channel></rss>"""
META = """<rss><channel><item><title>Product update</title><link>https://about.fb.com/news/2026/08/product-update/</link><description>Meta announced a product update.</description><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item></channel></rss>"""
SDK = json.dumps([{
    "tag_name": "v27.0.0", "name": "v27.0.0", "html_url": "https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v27.0.0", "body": "Adds the latest Marketing API release support.", "published_at": "2026-08-29T01:00:00Z", "updated_at": "2026-08-29T02:00:00Z", "draft": False, "prerelease": False,
}])


class PersonalFeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()

    def fetcher(self, *, fail: bool = False, bodies: dict[str, str] | None = None):
        source_bodies = bodies or {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "jon-loomer-meta-ads": JON,
        }

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            if fail:
                raise URLError("response body must not be retained")
            content_type = "application/json; charset=utf-8" if source["parser"] == "github_releases" else "application/rss+xml; charset=UTF-8"
            return source_bodies[source["id"]], content_type

        return fetch

    def test_config_keeps_two_official_and_one_unofficial_public_sources(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        self.assertEqual(set(sources), {"meta-product-news-rss", "meta-business-sdk-releases", "jon-loomer-meta-ads"})
        self.assertEqual(sources["jon-loomer-meta-ads"]["fetchUrl"], "https://www.jonloomer.com/feed/")
        self.assertEqual(sources["meta-business-sdk-releases"]["parser"], "github_releases")
        self.assertFalse(self.config["policies"]["persistRawResponseBody"])
        self.assertEqual(self.config["policies"]["japanesePresentation"]["maxRequestsPerRun"], 12)

    def test_config_rejects_insecure_source_and_invalid_source_classification(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["fetchUrl"] = "http://about.fb.com/feed"
        with self.assertRaisesRegex(ContractError, "HTTPS"):
            validate_config(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["sources"][0]["classification"] = "unknown"
        with self.assertRaisesRegex(ContractError, "classification"):
            validate_config(invalid)

    def test_empty_workflow_variables_use_the_documented_presentation_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "META_ADS_PERSONAL_FEED_JA_ENABLED": "",
                "META_ADS_PERSONAL_FEED_GROQ_MODEL": "",
                "GROQ_API_KEY": "test-key",
            },
            clear=False,
        ):
            renderer = _presentation_from_environment(1)
        self.assertIsNotNone(renderer)
        with patch.dict(os.environ, {"META_ADS_PERSONAL_FEED_JA_ENABLED": "false"}, clear=False):
            self.assertIsNone(_presentation_from_environment(1))
        with patch.dict(os.environ, {"META_ADS_PERSONAL_FEED_JA_ENABLED": "invalid"}, clear=False):
            with self.assertRaisesRegex(ContractError, "true, false"):
                _presentation_from_environment(1)

    def test_rss_category_filters_only_admit_relevant_jon_loomer_items(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        jon = extract_items(sources["jon-loomer-meta-ads"], JON)
        self.assertEqual([item["title"] for item in jon], ["How to review a new Meta Ads setting"])
        self.assertEqual(jon[0]["matchEvidence"], ["category:Meta Advertising"])
        self.assertIn("Review the new setting", jon[0]["sourceContext"])

    def test_first_collection_publishes_provenance_labelled_baseline_without_human_decisions(self) -> None:
        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher())
        self.assertEqual(len(feed["sources"]), 3)
        self.assertEqual(len(feed["items"]), 3)
        self.assertEqual(feed["schemaVersion"], FEED_SCHEMA_VERSION)
        self.assertEqual({item["sourceId"] for item in feed["items"]}, {"meta-product-news-rss", "meta-business-sdk-releases", "jon-loomer-meta-ads"})
        sdk = next(item for item in feed["items"] if item["sourceId"] == "meta-business-sdk-releases")
        self.assertEqual(sdk["updatedDate"], "2026-08-29")
        self.assertTrue(all(item["firstObservedAt"] == "2026-08-29T09:00:00Z" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["status"] == "pending" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["sourceFingerprint"] for item in feed["items"]))
        self.assertEqual(set(next_state["sources"]), {source["id"] for source in self.config["sources"]})
        self.assertNotIn("sourceContext", json.dumps(next_state))
        validate_feed(feed, self.config)
        validate_state(next_state, self.config)

    def test_generated_presentation_is_cached_by_content_fingerprint(self) -> None:
        calls: list[tuple[str, str]] = []

        def presenter(title: str, source_context: str, _policy: dict) -> dict[str, str]:
            calls.append((title, source_context))
            return {"shortHeadlineJa": f"{title} の短見出し", "summaryJa": f"{title} の要約"}

        initial_state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, seeded = collect(self.config, initial_state, 1, NOW, self.fetcher(), presenter)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(item["presentation"]["status"] == "generated" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["schemaVersion"] == PRESENTATION_SCHEMA_VERSION for item in feed["items"]))
        self.assertNotIn("sourceContext", json.dumps(seeded))

        calls.clear()
        unchanged_feed, unchanged_state = collect(self.config, seeded, 1, NOW.replace(day=30), self.fetcher(), presenter)
        self.assertEqual(calls, [])
        self.assertEqual(
            next(item for item in unchanged_feed["items"] if item["sourceId"] == "jon-loomer-meta-ads")["presentation"]["generatedAt"],
            "2026-08-29T09:00:00Z",
        )

        calls.clear()
        changed_bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "jon-loomer-meta-ads": JON.replace("review a new", "reassess a changed"),
        }
        changed_feed, changed_state = collect(self.config, unchanged_state, 1, NOW.replace(day=31), self.fetcher(bodies=changed_bodies), presenter)
        self.assertEqual(len(calls), 1)
        changed = next(item for item in changed_feed["items"] if item["sourceId"] == "jon-loomer-meta-ads")
        self.assertEqual(changed["presentation"]["generatedAt"], "2026-08-31T09:00:00Z")
        validate_state(changed_state, self.config)

    def test_presentation_failure_remains_pending_without_blocking_publication(self) -> None:
        def failing_presenter(_title: str, _source_context: str, _policy: dict) -> dict[str, str]:
            raise PresentationError("source content is intentionally not exposed")

        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher(), failing_presenter)
        self.assertEqual(len(feed["items"]), 3)
        self.assertTrue(all(item["presentation"]["status"] == "pending" for item in feed["items"]))
        self.assertNotIn("intentionally not exposed", json.dumps(next_state))
        validate_feed(feed, self.config)

    def test_presentation_contract_rejects_stale_fingerprint_and_overlong_text(self) -> None:
        def presenter(title: str, _source_context: str, _policy: dict) -> dict[str, str]:
            return {"shortHeadlineJa": f"{title} の短見出し", "summaryJa": f"{title} の要約"}

        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher(), presenter)
        source_id = "meta-product-news-rss"
        key, record = next(iter(next_state["sources"][source_id]["items"].items()))
        stale = copy.deepcopy(next_state)
        stale["sources"][source_id]["items"][key]["presentation"]["sourceFingerprint"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "sourceFingerprint"):
            validate_state(stale, self.config)

        overlong = copy.deepcopy(feed)
        overlong["items"][0]["presentation"]["summaryJa"] = "あ" * 361
        with self.assertRaisesRegex(ContractError, "configured length"):
            validate_feed(overlong, self.config)

    def test_legacy_state_is_upgraded_without_persisting_source_context(self) -> None:
        seeded_feed, seeded_state = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(),
        )
        legacy_state = copy.deepcopy(seeded_state)
        legacy_state["schemaVersion"] = "meta-ads-personal-feed-state/v1"
        for source in legacy_state["sources"].values():
            for record in source["items"].values():
                del record["presentation"]

        def presenter(title: str, _source_context: str, _policy: dict) -> dict[str, str]:
            return {"shortHeadlineJa": f"{title} の短見出し", "summaryJa": f"{title} の要約"}

        feed, upgraded = collect(self.config, legacy_state, 1, NOW.replace(day=30), self.fetcher(), presenter)
        self.assertEqual(seeded_feed["schemaVersion"], FEED_SCHEMA_VERSION)
        self.assertEqual(upgraded["schemaVersion"], STATE_SCHEMA_VERSION)
        self.assertEqual(feed["schemaVersion"], FEED_SCHEMA_VERSION)
        self.assertTrue(all(item["presentation"]["status"] == "generated" for item in feed["items"]))
        self.assertNotIn("sourceContext", json.dumps(upgraded))
        validate_state(upgraded, self.config)

    def test_changed_rss_item_updates_in_place_and_keeps_initial_observation(self) -> None:
        initial_state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        _feed, seeded = collect(self.config, initial_state, 1, NOW, self.fetcher())
        changed_bodies = {"meta-product-news-rss": META, "meta-business-sdk-releases": SDK, "jon-loomer-meta-ads": JON.replace("How to review", "How to reassess")}
        feed, state = collect(self.config, seeded, 1, NOW.replace(day=30), self.fetcher(bodies=changed_bodies))
        jon = next(item for item in feed["items"] if item["sourceId"] == "jon-loomer-meta-ads")
        self.assertEqual(jon["title"], "How to reassess a new Meta Ads setting")
        self.assertEqual(jon["firstObservedAt"], "2026-08-29T09:00:00Z")
        self.assertEqual(jon["lastObservedAt"], "2026-08-30T09:00:00Z")
        self.assertEqual(len(state["sources"]["jon-loomer-meta-ads"]["items"]), 1)

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
