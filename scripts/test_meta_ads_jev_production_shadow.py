from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from meta_ads_jev_production_shadow import load_feed, run_shadow, select_items


def _presentation(summary: str | None) -> dict:
    status = "machine" if summary is not None else "missing"
    return {
        "locales": {
            "en": {
                "fields": {
                    "summary": {"status": status, "value": summary},
                }
            }
        }
    }


def _feed() -> dict:
    return {
        "schemaVersion": "meta-ads-personal-feed/v5",
        "generatedAt": "2026-09-20T02:00:00Z",
        "items": [
            {
                "id": "older",
                "sourceId": "source-a",
                "title": "Older title",
                "url": "https://example.test/older",
                "publishedDate": "2026-09-18",
                "updatedDate": None,
                "firstObservedAt": "2026-09-18T00:00:00Z",
                "presentation": _presentation("Older public summary"),
            },
            {
                "id": "newer",
                "sourceId": "source-b",
                "title": "Newer title",
                "url": "https://example.test/newer",
                "publishedDate": "2026-09-20",
                "updatedDate": None,
                "firstObservedAt": "2026-09-20T00:00:00Z",
                "presentation": _presentation(None),
            },
        ],
    }


def _provider_response(choice: str = "strategic_signal") -> dict:
    probabilities = {
        "direct_impact": 0.1,
        "strategic_signal": 0.7,
        "unrelated": 0.1,
        "unclear": 0.1,
    }
    return {
        "model": "jev-1.13.0",
        "answers": {
            "adsRelevance": {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": 0.7,
            }
        },
    }


class MetaAdsJevProductionShadowTests(unittest.TestCase):
    def test_load_and_selection_use_latest_public_items(self) -> None:
        payload = _feed()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.json"
            raw = (json.dumps(payload) + "\n").encode()
            path.write_bytes(raw)
            feed, digest = load_feed(path)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        selected = select_items(feed, 2)
        self.assertEqual([item["itemId"] for item in selected], ["newer", "older"])
        self.assertEqual(selected[0]["sourceContext"], "")
        self.assertEqual(selected[1]["sourceContext"], "Older public summary")

    def test_report_does_not_retain_public_text_url_or_credential(self) -> None:
        captured = []

        def post_json(payload: dict, api_key: str, timeout: float) -> dict:
            self.assertEqual(api_key, "secret-key")
            captured.append(payload)
            return _provider_response()

        feed = _feed()
        report = run_shadow(
            feed,
            "a" * 64,
            "secret-key",
            5,
            2,
            post_json=post_json,
            generated_at="2026-09-20T03:00:00Z",
        )
        self.assertEqual(report["summary"]["classified"], 2)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertFalse(report["productionEffect"])
        self.assertFalse(report["routingEffect"])
        rendered = json.dumps(report)
        for forbidden in (
            "secret-key",
            "Older title",
            "Newer title",
            "Older public summary",
            "https://example.test",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(len(captured), 2)

    def test_provider_failure_is_isolated_in_artifact(self) -> None:
        def post_json(payload: dict, api_key: str, timeout: float) -> dict:
            raise RuntimeError("provider secret body")

        report = run_shadow(_feed(), "b" * 64, "key", 5, 2, post_json=post_json)
        self.assertEqual(report["summary"]["classified"], 0)
        self.assertEqual(report["summary"]["failed"], 2)
        self.assertEqual(report["summary"]["errorCodes"], {"transport_error": 2})
        self.assertNotIn("provider secret body", json.dumps(report))

    def test_limit_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            select_items(_feed(), 0)
        with self.assertRaises(ValueError):
            select_items(_feed(), 51)


if __name__ == "__main__":
    unittest.main()
