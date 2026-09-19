from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "meta_ads_jev_ads_relevance_shadow"
    / "human_labels.json"
)
EXPECTED_KEYS = {
    "itemId",
    "sourceId",
    "url",
    "title",
    "sourceContext",
    "sourceFingerprint",
    "humanLane",
    "humanReason",
    "labelSource",
    "sourceArtifact",
}
ALLOWED_HOSTS = {
    "jon-loomer-meta-ads": "www.jonloomer.com",
    "social-media-today-meta-ads": "www.socialmediatoday.com",
    "meta-business-sdk-releases": "github.com",
    "meta-product-news-rss": "about.fb.com",
}
LABEL_SOURCE = (
    "git:8618730:scripts/test_meta_ads_personal_feed.py"
    "#test_action_watch_drop_lanes_match_the_reviewed_fifteen_item_set"
)
SOURCE_ARTIFACT = (
    "data/meta_ads_personal_feed_state.json"
    "@908595bbd3461311f6f9ba250711530f968baf83"
)


class MetaAdsJevHumanLabelFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.items = cls.fixture["items"]

    def test_fixture_is_artifact_only_and_complete(self) -> None:
        self.assertEqual(
            set(self.fixture),
            {"schemaVersion", "fixtureId", "productionEffect", "items"},
        )
        self.assertEqual(
            self.fixture["schemaVersion"],
            "meta-ads-jev-human-label-fixture/v1",
        )
        self.assertEqual(
            self.fixture["fixtureId"],
            "meta-ads-reviewed-fifteen-2026-09-19",
        )
        self.assertIs(self.fixture["productionEffect"], False)
        self.assertEqual(len(self.items), 15)
        self.assertEqual(
            Counter(item["humanLane"] for item in self.items),
            Counter({"ACTION": 5, "WATCH": 5, "DROP": 5}),
        )

    def test_records_have_stable_ids_and_exact_provenance(self) -> None:
        item_ids: set[str] = set()
        urls: set[str] = set()
        for item in self.items:
            self.assertEqual(set(item), EXPECTED_KEYS)
            self.assertRegex(item["sourceFingerprint"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                item["itemId"],
                f'{item["sourceId"]}-{item["sourceFingerprint"][:20]}',
            )
            self.assertNotIn(item["itemId"], item_ids)
            self.assertNotIn(item["url"], urls)
            item_ids.add(item["itemId"])
            urls.add(item["url"])
            self.assertIn(item["sourceId"], ALLOWED_HOSTS)
            parsed = urlsplit(item["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.hostname, ALLOWED_HOSTS[item["sourceId"]])
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)
            self.assertTrue(item["title"])
            self.assertIsInstance(item["sourceContext"], str)
            self.assertIn(item["humanLane"], {"ACTION", "WATCH", "DROP"})
            self.assertIsNone(item["humanReason"])
            self.assertEqual(item["labelSource"], LABEL_SOURCE)
            self.assertEqual(item["sourceArtifact"], SOURCE_ARTIFACT)

    def test_known_corrected_and_watch_edges_are_frozen(self) -> None:
        by_title = {item["title"]: item for item in self.items}
        self.assertEqual(
            by_title[
                "ChatGPT Ads Get Automated Bidding, Placements, and URL Parameters"
            ]["humanLane"],
            "DROP",
        )
        self.assertEqual(
            by_title[
                "Introducing Muse: The World’s First Personal AI Agent Built for Everyone"
            ]["humanLane"],
            "WATCH",
        )
        self.assertEqual(
            by_title["Meta adds AI-powered assistant for SMB owners"]["humanLane"],
            "WATCH",
        )

    def test_fixture_contains_no_jev_output_or_production_routing(self) -> None:
        serialized = json.dumps(self.fixture, ensure_ascii=False)
        for prohibited in (
            "adsRelevance",
            "probabilities",
            "suggestedLane",
            "modelId",
            "questionSetVersion",
            "reviewStatus",
            "assessmentSource",
        ):
            self.assertNotIn(prohibited, serialized)
        self.assertIsNone(re.search(r"(?i)(api[_-]?key|secret|token)", serialized))


if __name__ == "__main__":
    unittest.main()
