from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
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
    _meta_business_news_date,
    _presentation_from_environment,
    _print_presentation_stats,
    _print_source_pipeline_stats,
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
SOCIAL_MEDIA_TODAY = """<rss><channel>
<item><title>Meta expands Ads Manager campaign controls</title><link>https://www.socialmediatoday.com/news/meta-expands-ads-manager-campaign-controls/123456/</link><description>Meta announced new campaign controls for advertisers.</description><pubDate>Fri, 29 Aug 2026 02:00:00 -0400</pubDate></item>
<item><title>Meta launches a new AI subscription</title><link>https://www.socialmediatoday.com/news/meta-ai-subscription/123457/</link><description>Meta announced a consumer subscription package.</description><pubDate>Fri, 29 Aug 2026 01:00:00 -0400</pubDate></item>
</channel></rss>"""
JON = """<rss><channel>
<item><title>How to review a new Meta Ads setting</title><link>https://www.jonloomer.com/meta-ads-manager-rollout/</link><description>Review the new setting before changing a campaign.</description><category>Meta Advertising</category><pubDate>Fri, 29 Aug 2026 02:00:00 +0000</pubDate></item>
<item><title>General marketing notes</title><link>https://www.jonloomer.com/general-marketing-notes/</link><category>Marketing</category></item>
</channel></rss>"""
JON_WITH_OFFICIAL_LINK = """<rss><channel>
<item>
  <title>One-Click CAPI Activated, New Meta Ads Features, and More</title>
  <link>https://www.jonloomer.com/one-click-capi-activated/</link>
  <description><![CDATA[
    <p>Meta published an <a href="https://www.facebook.com/business/news/pixel-conversionsapi-updates?utm_source=jon#announcement">official announcement</a>.</p>
    <p><a href="https://www.facebook.com/business/news/pixel-conversionsapi-updates">Duplicate canonical URL</a></p>
    <p><a href="https://www.facebook.com.evil.example/business/news/not-official">Lookalike host</a></p>
    <p><a href="http://www.facebook.com/business/news/not-https">Insecure URL</a></p>
    <p><a href="https://www.facebook.com/business/help/not-news">Wrong path</a></p>
  ]]></description>
  <category>Meta Advertising</category>
  <pubDate>Thu, 14 May 2026 11:30:51 +0000</pubDate>
</item>
</channel></rss>"""
META_BUSINESS_NEWS = """<!doctype html><html><head>
<meta property="og:url" content="https://www.facebook.com/business/news/pixel-conversionsapi-updates">
<meta property="og:type" content="article">
<meta property="og:title" content="Removing Technical Barriers to Help Businesses Get More From Their Ads">
<meta property="og:description" content="Meta announces updates to the Meta Pixel and Conversions API for advertisers.">
</head><body><main><span>Announcement</span><span>April 15, 2026</span></main>
<script>Announcement January 1, 1999</script></body></html>"""
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
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY,
            "jon-loomer-meta-ads": JON,
        }

        def fetch(source: dict, _timeout: float) -> tuple[str, str]:
            if fail:
                raise URLError("response body must not be retained")
            if source["parser"] == "github_releases":
                content_type = "application/json; charset=utf-8"
            elif source["parser"] == "meta_business_news_html":
                content_type = "text/html; charset=utf-8"
            else:
                content_type = "application/rss+xml; charset=UTF-8"
            body = source_bodies.get(source["id"], META_BUSINESS_NEWS)
            return body, content_type

        return fetch

    def test_config_adds_keyword_filtered_and_discovered_official_sources(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        discovered = {source["id"]: source for source in self.config["discoveredSources"]}
        self.assertEqual(set(sources), {"meta-product-news-rss", "meta-business-sdk-releases", "social-media-today-meta-ads", "jon-loomer-meta-ads"})
        self.assertEqual(set(discovered), {"meta-business-news-discovered"})
        self.assertEqual(sources["social-media-today-meta-ads"]["fetchUrl"], "https://www.socialmediatoday.com/feeds/news/")
        self.assertEqual(sources["social-media-today-meta-ads"]["match"]["kind"], "all_groups")
        self.assertEqual(sources["jon-loomer-meta-ads"]["fetchUrl"], "https://www.jonloomer.com/feed/")
        self.assertEqual(sources["meta-business-sdk-releases"]["parser"], "github_releases")
        self.assertEqual(discovered["meta-business-news-discovered"]["classification"], "official")
        self.assertEqual(discovered["meta-business-news-discovered"]["discovery"]["fromSourceId"], "jon-loomer-meta-ads")
        self.assertEqual(discovered["meta-business-news-discovered"]["transport"]["allowedFetchHosts"], ["www.facebook.com"])
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

        invalid = copy.deepcopy(self.config)
        invalid["discoveredSources"][0]["classification"] = "unofficial"
        with self.assertRaisesRegex(ContractError, "classification must be official"):
            validate_config(invalid)

        invalid = copy.deepcopy(self.config)
        invalid["discoveredSources"][0]["discovery"]["allowedPathPrefix"] = "/business/"
        with self.assertRaisesRegex(ContractError, "allowedPathPrefix"):
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

    def test_unofficial_rss_filters_only_admit_relevant_items(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        social_media_today = extract_items(sources["social-media-today-meta-ads"], SOCIAL_MEDIA_TODAY)
        jon = extract_items(sources["jon-loomer-meta-ads"], JON)
        self.assertEqual([item["title"] for item in social_media_today], ["Meta expands Ads Manager campaign controls"])
        self.assertEqual(social_media_today[0]["matchEvidence"], ["keyword:meta", "keyword:ads manager"])
        self.assertEqual([item["title"] for item in jon], ["How to review a new Meta Ads setting"])
        self.assertEqual(jon[0]["matchEvidence"], ["category:Meta Advertising"])
        self.assertIn("Review the new setting", jon[0]["sourceContext"])

    def test_jon_rss_extracts_only_canonical_meta_business_news_links(self) -> None:
        sources = {source["id"]: source for source in self.config["sources"]}
        discovery = self.config["discoveredSources"][0]
        jon = extract_items(sources["jon-loomer-meta-ads"], JON_WITH_OFFICIAL_LINK, discovery_source=discovery)
        self.assertEqual(len(jon), 1)
        self.assertEqual(
            jon[0]["discoveredLinks"],
            ["https://www.facebook.com/business/news/pixel-conversionsapi-updates"],
        )
        self.assertEqual(jon[0]["deferredDiscoveredLinks"], 0)

    def test_meta_business_news_date_accepts_observed_label_variants(self) -> None:
        cases = {
            "Announcement · April 15, 2026": "2026-04-15",
            "Announcements · June 23, 2026": "2026-06-23",
            "[Announcement] · [July 7, 2026]": "2026-07-07",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(_meta_business_news_date(value), expected)

    def test_discovered_meta_page_is_verified_and_promoted_as_official(self) -> None:
        bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY,
            "jon-loomer-meta-ads": JON_WITH_OFFICIAL_LINK,
            "meta-business-news-discovered": META_BUSINESS_NEWS,
        }
        pipeline: dict = {}
        feed, next_state = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(bodies=bodies),
            source_pipeline_stats=pipeline,
        )
        descriptor = next(source for source in feed["sources"] if source["id"] == "meta-business-news-discovered")
        promoted = next(item for item in feed["items"] if item["sourceId"] == "meta-business-news-discovered")
        self.assertEqual(descriptor["classification"], "official")
        self.assertEqual(promoted["url"], "https://www.facebook.com/business/news/pixel-conversionsapi-updates")
        self.assertEqual(promoted["title"], "Removing Technical Barriers to Help Businesses Get More From Their Ads")
        self.assertEqual(promoted["publishedDate"], "2026-04-15")
        self.assertIsNone(promoted["updatedDate"])
        self.assertEqual(promoted["matchEvidence"], ["discovered-via:jon-loomer-meta-ads"])
        self.assertNotIn("sourceContext", json.dumps(feed))
        self.assertNotIn("sourceContext", json.dumps(next_state))
        discovered_pipeline = pipeline["sources"]["meta-business-news-discovered"]
        self.assertEqual(
            (
                discovered_pipeline["mode"],
                discovered_pipeline["fetched"],
                discovered_pipeline["discoveredLinks"],
                discovered_pipeline["attemptedLinks"],
                discovered_pipeline["rejectedLinks"],
                discovered_pipeline["retainedItems"],
            ),
            ("discovered_official", True, 1, 1, 0, 1),
        )
        validate_feed(feed, self.config)
        validate_state(next_state, self.config)

    def test_discovered_page_failure_isolated_without_leaking_details(self) -> None:
        bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY,
            "jon-loomer-meta-ads": JON_WITH_OFFICIAL_LINK,
        }

        def fetch(source: dict, timeout: float) -> tuple[str, str]:
            if source["id"] == "meta-business-news-discovered":
                raise URLError("secret response from blocked URL")
            return self.fetcher(bodies=bodies)(source, timeout)

        pipeline: dict = {}
        feed, next_state = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            fetch,
            source_pipeline_stats=pipeline,
        )
        self.assertEqual(len(feed["items"]), 4)
        self.assertNotIn("meta-business-news-discovered", {source["id"] for source in feed["sources"]})
        self.assertEqual(next_state["sources"]["meta-business-news-discovered"]["items"], {})
        counts = pipeline["sources"]["meta-business-news-discovered"]
        self.assertEqual((counts["fetched"], counts["attemptedLinks"], counts["rejectedLinks"]), (False, 1, 1))
        output = io.StringIO()
        with redirect_stdout(output):
            _print_source_pipeline_stats(pipeline)
        self.assertNotIn("secret response", output.getvalue())
        self.assertNotIn("pixel-conversionsapi-updates", output.getvalue())

    def test_discovered_page_with_mismatched_canonical_url_is_not_promoted(self) -> None:
        bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY,
            "jon-loomer-meta-ads": JON_WITH_OFFICIAL_LINK,
            "meta-business-news-discovered": META_BUSINESS_NEWS.replace(
                'content="https://www.facebook.com/business/news/pixel-conversionsapi-updates"',
                'content="https://www.facebook.com/business/news/a-different-article"',
            ),
        }
        pipeline: dict = {}
        feed, _state = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(bodies=bodies),
            source_pipeline_stats=pipeline,
        )
        self.assertNotIn("meta-business-news-discovered", {item["sourceId"] for item in feed["items"]})
        counts = pipeline["sources"]["meta-business-news-discovered"]
        self.assertEqual(
            (counts["fetched"], counts["parsedItems"], counts["validItems"], counts["rejectedLinks"]),
            (True, 1, 0, 1),
        )

    def test_transient_discovered_page_failure_keeps_prior_verified_item(self) -> None:
        bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY,
            "jon-loomer-meta-ads": JON_WITH_OFFICIAL_LINK,
            "meta-business-news-discovered": META_BUSINESS_NEWS,
        }
        _feed, seeded = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(bodies=bodies),
        )

        def fetch(source: dict, timeout: float) -> tuple[str, str]:
            if source["id"] == "meta-business-news-discovered":
                raise URLError("temporary block")
            return self.fetcher(bodies=bodies)(source, timeout)

        feed, next_state = collect(self.config, seeded, 1, NOW.replace(day=30), fetch)
        promoted = next(item for item in feed["items"] if item["sourceId"] == "meta-business-news-discovered")
        self.assertEqual(promoted["lastObservedAt"], "2026-08-29T09:00:00Z")
        retained = next(iter(next_state["sources"]["meta-business-news-discovered"]["items"].values()))
        self.assertEqual(retained["lastObservedAt"], "2026-08-29T09:00:00Z")

    def test_first_collection_publishes_provenance_labelled_baseline_without_human_decisions(self) -> None:
        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher())
        self.assertEqual(len(feed["sources"]), 4)
        self.assertEqual(len(feed["items"]), 4)
        self.assertEqual(feed["schemaVersion"], FEED_SCHEMA_VERSION)
        self.assertEqual({item["sourceId"] for item in feed["items"]}, {"meta-product-news-rss", "meta-business-sdk-releases", "social-media-today-meta-ads", "jon-loomer-meta-ads"})
        sdk = next(item for item in feed["items"] if item["sourceId"] == "meta-business-sdk-releases")
        self.assertEqual(sdk["updatedDate"], "2026-08-29")
        self.assertTrue(all(item["firstObservedAt"] == "2026-08-29T09:00:00Z" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["status"] == "pending" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["sourceFingerprint"] for item in feed["items"]))
        self.assertEqual(
            set(next_state["sources"]),
            {source["id"] for source in self.config["sources"] + self.config["discoveredSources"]},
        )
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
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(item["presentation"]["status"] == "generated" for item in feed["items"]))
        self.assertTrue(all(item["presentation"]["schemaVersion"] == PRESENTATION_SCHEMA_VERSION for item in feed["items"]))
        self.assertNotIn("sourceContext", json.dumps(seeded))

        calls.clear()
        unchanged_feed, unchanged_state = collect(self.config, seeded, 1, NOW.replace(day=30), self.fetcher(), presenter)
        self.assertEqual(calls, [])
        self.assertEqual(
            next(item for item in unchanged_feed["items"] if item["sourceId"] == "social-media-today-meta-ads")["presentation"]["generatedAt"],
            "2026-08-29T09:00:00Z",
        )

        calls.clear()
        changed_bodies = {
            "meta-product-news-rss": META,
            "meta-business-sdk-releases": SDK,
            "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY.replace("campaign controls", "measurement controls"),
            "jon-loomer-meta-ads": JON,
        }
        changed_feed, changed_state = collect(self.config, unchanged_state, 1, NOW.replace(day=31), self.fetcher(bodies=changed_bodies), presenter)
        self.assertEqual(len(calls), 1)
        changed = next(item for item in changed_feed["items"] if item["sourceId"] == "social-media-today-meta-ads")
        self.assertEqual(changed["presentation"]["generatedAt"], "2026-08-31T09:00:00Z")
        validate_state(changed_state, self.config)

    def test_presentation_backfill_is_bounded_and_reports_safe_source_counts(self) -> None:
        calls: list[tuple[str, str]] = []
        stats: dict = {}

        def presenter(title: str, source_context: str, _policy: dict) -> dict[str, str]:
            calls.append((title, source_context))
            return {"shortHeadlineJa": f"{title} の短見出し", "summaryJa": f"{title} の要約"}

        feed, next_state = collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(),
            presenter,
            presentation_limit=1,
            presentation_stats=stats,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(stats["requestLimit"], 1)
        self.assertTrue(stats["rendererEnabled"])
        self.assertEqual((stats["eligible"], stats["attempted"], stats["generated"], stats["failed"], stats["deferred"]), (4, 1, 1, 0, 3))
        self.assertEqual(sum(source["eligible"] for source in stats["sources"].values()), 4)
        self.assertEqual(sum(source["attempted"] for source in stats["sources"].values()), 1)
        self.assertNotIn("campaign controls", json.dumps(stats))
        self.assertNotIn("Meta expands Ads Manager", json.dumps(stats))
        self.assertEqual(sum(item["presentation"]["status"] == "generated" for item in feed["items"]), 1)
        validate_state(next_state, self.config)

    def test_source_pipeline_reports_safe_match_counts_without_source_content(self) -> None:
        pipeline: dict = {}
        collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(),
            source_pipeline_stats=pipeline,
        )
        social = pipeline["sources"]["social-media-today-meta-ads"]
        self.assertEqual(pipeline["parserVersion"], "meta-ads-personal-feed-parser/v2")
        self.assertTrue(all(pipeline["sources"][source["id"]]["fetched"] for source in self.config["sources"]))
        self.assertFalse(pipeline["sources"]["meta-business-news-discovered"]["fetched"])
        self.assertEqual(
            (social["parsedItems"], social["validItems"], social["matchedItems"], social["excludedItems"]),
            (2, 2, 1, 1),
        )
        self.assertEqual(social["matchGroupMatches"], [2, 1])
        self.assertEqual(social["retainedItems"], 1)
        self.assertTrue(all(pipeline["sources"][source["id"]]["responseBytes"] > 0 for source in self.config["sources"]))
        self.assertEqual(pipeline["sources"]["meta-business-news-discovered"]["responseBytes"], 0)
        output = io.StringIO()
        with redirect_stdout(output):
            _print_source_pipeline_stats(pipeline)
        log = output.getvalue()
        self.assertIn("SOURCE_PIPELINE: id=social-media-today-meta-ads", log)
        self.assertIn("SOURCE_MATCH_GROUP: id=social-media-today-meta-ads group=1 matched=2", log)
        self.assertIn("SOURCE_MATCH_GROUP: id=social-media-today-meta-ads group=2 matched=1", log)
        self.assertNotIn("campaign controls", log)
        self.assertNotIn("Meta expands Ads Manager", log)

    def test_presentation_backfill_rejects_out_of_policy_limit_before_fetching(self) -> None:
        def unexpected_fetch(_source: dict, _timeout: float) -> tuple[str, str]:
            raise AssertionError("invalid backfill limit must not fetch a source")

        with self.assertRaisesRegex(ContractError, "from 1 to 12"):
            collect(
                self.config,
                {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
                1,
                NOW,
                unexpected_fetch,
                presentation_limit=13,
            )

    def test_presentation_failure_remains_pending_without_blocking_publication(self) -> None:
        def failing_presenter(_title: str, _source_context: str, _policy: dict) -> dict[str, str]:
            raise PresentationError("source content is intentionally not exposed")

        state = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
        stats: dict = {}
        feed, next_state = collect(self.config, state, 1, NOW, self.fetcher(), failing_presenter, presentation_stats=stats)
        self.assertEqual(len(feed["items"]), 4)
        self.assertTrue(all(item["presentation"]["status"] == "pending" for item in feed["items"]))
        self.assertNotIn("intentionally not exposed", json.dumps(next_state))
        self.assertEqual((stats["attempted"], stats["generated"], stats["failed"]), (4, 0, 4))
        self.assertEqual(stats["failureReasons"], {"unknown": 4})
        self.assertNotIn("intentionally not exposed", json.dumps(stats))
        validate_feed(feed, self.config)

    def test_presentation_failure_logs_only_reason_codes(self) -> None:
        stats: dict = {}

        def failing_presenter(_title: str, _source_context: str, _policy: dict) -> dict[str, str]:
            raise PresentationError("response_invalid_json")

        collect(
            self.config,
            {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}},
            1,
            NOW,
            self.fetcher(),
            failing_presenter,
            presentation_stats=stats,
        )
        self.assertEqual(stats["failureReasons"], {"response_invalid_json": 4})
        self.assertEqual(
            sum(source["failureReasons"].get("response_invalid_json", 0) for source in stats["sources"].values()),
            4,
        )
        output = io.StringIO()
        with redirect_stdout(output):
            _print_presentation_stats(stats)
        self.assertIn("PRESENTATION_FAILURE: code=response_invalid_json count=4", output.getvalue())
        self.assertNotIn("campaign controls", output.getvalue())

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
        changed_bodies = {"meta-product-news-rss": META, "meta-business-sdk-releases": SDK, "social-media-today-meta-ads": SOCIAL_MEDIA_TODAY.replace("campaign controls", "measurement controls"), "jon-loomer-meta-ads": JON}
        feed, state = collect(self.config, seeded, 1, NOW.replace(day=30), self.fetcher(bodies=changed_bodies))
        social_media_today = next(item for item in feed["items"] if item["sourceId"] == "social-media-today-meta-ads")
        self.assertEqual(social_media_today["title"], "Meta expands Ads Manager measurement controls")
        self.assertEqual(social_media_today["firstObservedAt"], "2026-08-29T09:00:00Z")
        self.assertEqual(social_media_today["lastObservedAt"], "2026-08-30T09:00:00Z")
        self.assertEqual(len(state["sources"]["social-media-today-meta-ads"]["items"]), 1)

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
