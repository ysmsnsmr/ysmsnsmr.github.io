from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment_meta_ads_jev_ads_relevance_shadow import (
    CHOICES,
    EXPECTED_ITEM_COUNT,
    FIXTURE_PATH,
    REQUESTED_MODEL_ID,
    build_request,
    load_fixture,
    run_shadow,
    write_new_artifact,
)


def provider_response(choice: str, model: str = "typesafe/jev-1.13-20260917") -> dict:
    probabilities = {name: 0.0 for name in CHOICES}
    probabilities[choice] = 1.0
    return {
        "model": model,
        "answers": {
            "adsRelevance": {
                "type": "choice",
                "choice": choice,
                "probabilities": probabilities,
                "confidence": 0.9,
            }
        },
    }


class JevAdsRelevanceArtifactRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture, self.fixture_sha256 = load_fixture()

    def test_fixture_is_the_committed_human_fifteen(self) -> None:
        self.assertEqual(FIXTURE_PATH.name, "human_labels.json")
        self.assertEqual(len(self.fixture["items"]), EXPECTED_ITEM_COUNT)
        self.assertTrue(self.fixture_sha256)

    def test_request_sends_only_title_and_bounded_source_context(self) -> None:
        item = self.fixture["items"][0]
        request = build_request(item)
        self.assertEqual(request["model"], REQUESTED_MODEL_ID)
        self.assertEqual(set(request["input"]), {"title", "sourceContext"})
        self.assertEqual(request["input"]["title"], item["title"])
        self.assertEqual(request["input"]["sourceContext"], item["sourceContext"])
        serialized = json.dumps(request)
        for forbidden in (item["url"], item["sourceFingerprint"], item["humanLane"], item["itemId"]):
            self.assertNotIn(forbidden, serialized)

    def test_runner_compares_all_items_without_retaining_fixture_text(self) -> None:
        captured_requests: list[dict] = []

        def post_json(payload: dict, api_key: str, timeout_seconds: float) -> dict:
            self.assertEqual(api_key, "test-key")
            self.assertEqual(timeout_seconds, 7)
            captured_requests.append(payload)
            return provider_response("direct_impact")

        report = run_shadow(
            self.fixture,
            self.fixture_sha256,
            "test-key",
            7,
            post_json=post_json,
            generated_at="2026-09-19T04:00:00Z",
        )
        self.assertEqual(len(captured_requests), EXPECTED_ITEM_COUNT)
        self.assertEqual(report["comparison"]["classified"], EXPECTED_ITEM_COUNT)
        self.assertEqual(report["comparison"]["failed"], 0)
        self.assertFalse(report["productionEffect"])
        rendered = json.dumps(report)
        self.assertNotIn("test-key", rendered)
        for item in self.fixture["items"]:
            self.assertNotIn(item["title"], rendered)
            self.assertNotIn(item["url"], rendered)
            if item["sourceContext"]:
                self.assertNotIn(item["sourceContext"], rendered)

    def test_unclear_and_action_to_drop_are_reported_as_observations(self) -> None:
        def post_json(payload: dict, api_key: str, timeout_seconds: float) -> dict:
            title = payload["input"]["title"]
            if title == "How to Approach Meta Advertising Control":
                return provider_response("unrelated")
            return provider_response("unclear")

        report = run_shadow(self.fixture, self.fixture_sha256, "key", 5, post_json=post_json)
        comparison = report["comparison"]
        self.assertIn(
            "jon-loomer-meta-ads-d457987942b9d8c73735",
            comparison["criticalActionToDrop"],
        )
        self.assertEqual(len(comparison["unclear"]), EXPECTED_ITEM_COUNT - 1)
        self.assertEqual(comparison["failed"], 0)

    def test_provider_failure_is_safely_categorized_without_body(self) -> None:
        def post_json(payload: dict, api_key: str, timeout_seconds: float) -> dict:
            raise RuntimeError("secret provider response body")

        report = run_shadow(self.fixture, self.fixture_sha256, "key", 5, post_json=post_json)
        self.assertEqual(report["comparison"]["failed"], EXPECTED_ITEM_COUNT)
        self.assertEqual(
            {entry["errorCode"] for entry in report["comparison"]["errors"]},
            {"transport_error"},
        )
        self.assertNotIn("secret provider response body", json.dumps(report))

    def test_artifact_write_is_local_new_and_rejects_overwrite(self) -> None:
        report = {"schemaVersion": "test"}
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            path = write_new_artifact(report, "comparison-2026-09-19.json", artifact_dir)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            with self.assertRaises(FileExistsError):
                write_new_artifact(report, "comparison-2026-09-19.json", artifact_dir)
            with self.assertRaises(ValueError):
                write_new_artifact(report, "../escaped.json", artifact_dir)

    def test_default_command_does_not_call_the_provider(self) -> None:
        with patch("experiment_meta_ads_jev_ads_relevance_shadow.post_jev_request") as post:
            from experiment_meta_ads_jev_ads_relevance_shadow import main

            with patch("sys.argv", ["runner"]):
                self.assertEqual(main(), 0)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
