#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_fallback_policy import high_confidence_json_fallback_topic


class JsonFallbackTopicTest(unittest.TestCase):
    def test_ignores_selection_tags_and_unrelated_body_detail(self) -> None:
        item = {
            "title": "Strong demand for Malaysia's US$1.5b sukuk signals investor confidence",
            "description": "Malaysia's global sukuk issuance drew strong demand.",
            "tags": ["currency"],
            "flags": {},
            "body_evidence_excerpt": "The conference agenda also included private healthcare costs.",
        }

        self.assertEqual(high_confidence_json_fallback_topic(item), "")

    def test_keeps_currency_topic_when_headline_metadata_supports_it(self) -> None:
        item = {
            "title": "Ringgit opens higher against the US dollar",
            "description": "The ringgit rose as markets awaited the Fed decision.",
            "tags": [],
            "flags": {},
            "body_evidence_excerpt": "",
        }

        self.assertEqual(high_confidence_json_fallback_topic(item), "currency")

    def test_keeps_health_topic_when_headline_metadata_supports_it(self) -> None:
        item = {
            "title": "Health Ministry registers rare disease medicines",
            "description": "The Health Ministry announced the latest medicine registrations.",
            "tags": ["health"],
            "flags": {"is_health_system": True},
            "body_evidence_excerpt": "",
        }

        self.assertEqual(high_confidence_json_fallback_topic(item), "health")

    def test_keeps_weather_topic_when_headline_metadata_supports_it(self) -> None:
        item = {
            "title": "MetMalaysia issues thunderstorm warning",
            "description": "Heavy rain is expected in several states.",
            "tags": ["weather"],
            "flags": {"is_weather": True},
            "body_evidence_excerpt": "",
        }

        self.assertEqual(high_confidence_json_fallback_topic(item), "storm_weather")


if __name__ == "__main__":
    unittest.main()
