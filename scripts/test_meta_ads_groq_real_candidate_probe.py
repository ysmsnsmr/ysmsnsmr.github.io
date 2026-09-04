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
            self.assertEqual(result, {"sourceId": "test-source", "candidateFound": True, "status": "success"})
            kwargs = present.call_args.kwargs
            self.assertEqual(kwargs["title"], "Fetched title")
            self.assertEqual(kwargs["source_context"], "Fetched source context")
            self.assertEqual(kwargs["max_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
