from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_ads_groq_real_candidate_probe import run_probe


class GroqRealCandidateProbeTest(unittest.TestCase):
    def test_uses_current_candidate_and_discards_generated_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            feed_path = Path(directory) / "feed.json"
            feed_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "item-1",
                                "sourceId": "test-source",
                                "title": "Stored title",
                                "url": "https://example.test/article",
                                "publishedDate": "2026-09-01",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = {
                "policies": {
                    "bilingualPresentation": {
                        "maxInputChars": 12000,
                        "shortHeadlineMaxChars": 240,
                        "summaryMaxChars": 1600,
                    }
                },
                "sources": [
                    {
                        "id": "test-source",
                        "fetchUrl": "https://example.test/feed.xml",
                    }
                ],
                "discoveredSources": [],
            }
            source_item = {
                "url": "https://example.test/article",
                "title": "Fetched title",
                "sourceContext": "Fetched source context",
            }
            with (
                patch("meta_ads_groq_real_candidate_probe.load_config", return_value=config),
                patch("meta_ads_groq_real_candidate_probe._all_sources", return_value=config["sources"]),
                patch("meta_ads_groq_real_candidate_probe.bounded_request", return_value=("ignored", "application/rss+xml")),
                patch("meta_ads_groq_real_candidate_probe.extract_items", return_value=[source_item]),
                patch(
                    "meta_ads_groq_real_candidate_probe.request_bilingual_presentation",
                    return_value={
                        "shortHeadlineEn": "discarded",
                        "summaryEn": "discarded",
                        "shortHeadlineJa": "discarded",
                        "summaryJa": "discarded",
                    },
                ) as present,
            ):
                result = run_probe(
                    api_key="test-key",
                    model="test-model",
                    source_id="test-source",
                    feed_path=feed_path,
                    config_path=Path(directory) / "config.json",
                )
            self.assertEqual(
                result,
                {
                    "sourceId": "test-source",
                    "candidateFound": True,
                    "contextLimit": 12000,
                    "locale": "bilingual",
                    "status": "success",
                },
            )
            kwargs = present.call_args.kwargs
            self.assertEqual(kwargs["title"], "Fetched title")
            self.assertEqual(kwargs["source_context"], "Fetched source context")
            self.assertEqual(kwargs["max_attempts"], 1)

    def test_can_select_only_missing_candidates_and_title_only_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            feed_path = Path(directory) / "feed.json"
            feed_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "item-machine",
                                "sourceId": "test-source",
                                "title": "Machine title",
                                "url": "https://example.test/machine",
                                "publishedDate": "2026-09-02",
                                "presentation": {"locales": {"en": {"status": "machine"}}},
                            },
                            {
                                "id": "item-missing",
                                "sourceId": "test-source",
                                "title": "Missing title",
                                "url": "https://example.test/missing",
                                "publishedDate": "2026-09-01",
                                "presentation": {"locales": {"en": {"status": "missing"}}},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = {
                "policies": {"bilingualPresentation": {"maxInputChars": 12000, "shortHeadlineMaxChars": 240, "summaryMaxChars": 1600}},
                "sources": [{"id": "test-source", "fetchUrl": "https://example.test/feed.xml"}],
                "discoveredSources": [],
            }
            source_item = {
                "url": "https://example.test/missing",
                "title": "Missing title",
                "sourceContext": "Context that must not be sent in title-only mode",
            }
            with (
                patch("meta_ads_groq_real_candidate_probe.load_config", return_value=config),
                patch("meta_ads_groq_real_candidate_probe._all_sources", return_value=config["sources"]),
                patch("meta_ads_groq_real_candidate_probe.bounded_request", return_value=("ignored", "application/rss+xml")),
                patch("meta_ads_groq_real_candidate_probe.extract_items", return_value=[source_item]),
                patch("meta_ads_groq_real_candidate_probe.request_bilingual_presentation", return_value={"ok": "discarded"}) as present,
            ):
                result = run_probe(
                    api_key="test-key",
                    model="test-model",
                    source_id="test-source",
                    feed_path=feed_path,
                    config_path=Path(directory) / "config.json",
                    max_input_chars=0,
                    require_missing=True,
                    candidate_id="item-missing",
                )
            self.assertEqual(result["contextLimit"], 0)
            self.assertEqual(present.call_args.kwargs["source_context"], "")

    def test_can_probe_english_and_japanese_two_field_requests_for_same_missing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            feed_path = Path(directory) / "feed.json"
            feed_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "item-missing",
                                "sourceId": "test-source",
                                "title": "Missing title",
                                "url": "https://example.test/missing",
                                "publishedDate": "2026-09-01",
                                "presentation": {"locales": {"en": {"status": "missing"}}},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = {
                "policies": {"bilingualPresentation": {"maxInputChars": 12000, "shortHeadlineMaxChars": 240, "summaryMaxChars": 1600}},
                "sources": [{"id": "test-source", "fetchUrl": "https://example.test/feed.xml"}],
                "discoveredSources": [],
            }
            source_item = {
                "url": "https://example.test/missing",
                "title": "Missing title",
                "sourceContext": "Same context for both locale probes",
            }
            with (
                patch("meta_ads_groq_real_candidate_probe.load_config", return_value=config),
                patch("meta_ads_groq_real_candidate_probe._all_sources", return_value=config["sources"]),
                patch("meta_ads_groq_real_candidate_probe.bounded_request", return_value=("ignored", "application/rss+xml")),
                patch("meta_ads_groq_real_candidate_probe.extract_items", return_value=[source_item]),
                patch("meta_ads_groq_real_candidate_probe._request_locale_presentation", return_value={"ok": "discarded"}) as present,
                patch("meta_ads_groq_real_candidate_probe.request_presentation", return_value={"ok": "discarded"}) as japanese_present,
            ):
                for locale in ("en", "ja"):
                    result = run_probe(
                        api_key="test-key",
                        model="test-model",
                        source_id="test-source",
                        feed_path=feed_path,
                        config_path=Path(directory) / "config.json",
                        max_input_chars=4000,
                        require_missing=True,
                        candidate_id="item-missing",
                        locale=locale,
                    )
                    self.assertEqual(result["locale"], locale)
                    if locale == "en":
                        self.assertEqual(present.call_args.kwargs["locale"], locale)
                        self.assertEqual(present.call_args.kwargs["title"], "Missing title")
                    else:
                        self.assertEqual(japanese_present.call_args.kwargs["title"], "Missing title")


if __name__ == "__main__":
    unittest.main()
