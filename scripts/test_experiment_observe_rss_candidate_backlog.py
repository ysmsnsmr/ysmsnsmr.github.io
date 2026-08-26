#!/usr/bin/env python3
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import experiment_observe_rss_candidate_backlog as observer


def rss(*items: tuple[str, str, str, str]) -> bytes:
    rendered = []
    for title, description, link, published in items:
        rendered.append(
            "<item>"
            f"<title>{title}</title>"
            f"<description>{description}</description>"
            f"<link>{link.replace('&', '&amp;')}</link>"
            f"<pubDate>{published}</pubDate>"
            "</item>"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<rss version=\"2.0\"><channel><title>Fixture</title>"
        + "".join(rendered)
        + "</channel></rss>"
    ).encode("utf-8")


def fetch_result(data: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        data=data,
        status="200",
        content_type="application/rss+xml; charset=UTF-8",
        method="fixture",
        error="",
    )


class BusinessTodayDay1HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 25, 9, 0, tzinfo=observer.MYT)
        self.candidate_response = rss(
            (
                "Sepang road to close for one month from August 30",
                "Road users should plan journeys during the closure.",
                "https://www.businesstoday.com.my/2026/08/25/sepang-road/?utm_source=demo",
                "Tue, 25 Aug 2026 08:15:00 +0800",
            ),
            (
                "Company quarterly earnings beat market forecast",
                "The listed company reported higher profit.",
                "https://www.businesstoday.com.my/2026/08/25/company-earnings/",
                "Tue, 25 Aug 2026 07:45:00 +0800",
            ),
        )
        baseline, _ = observer.baseline_snapshot("origin/main")
        self.baseline_urls = {source["url"] for source in baseline["sources"]}

    def fake_fetcher(self, url: str) -> SimpleNamespace:
        if url == observer.DAY1_FEED_URL:
            return fetch_result(self.candidate_response)
        if url in self.baseline_urls:
            feed_slug = str(abs(hash(url)))
            return fetch_result(
                rss(
                    (
                        "Malaysia public transport service disruption announced",
                        "Passengers should plan journeys after a service disruption.",
                        f"https://baseline.example.test/{feed_slug}",
                        "Tue, 25 Aug 2026 08:00:00 +0800",
                    )
                )
            )
        return SimpleNamespace(
            ok=False,
            data=b"",
            status="404",
            content_type="text/plain",
            method="fixture",
            error="unexpected fixture URL",
        )

    def test_day1_end_to_end_writes_raw_artifacts_and_replays_scheduled_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            observer,
            "collect_cleaned_reference",
            side_effect=AssertionError("cleaned reference must not be used as production baseline"),
        ):
            run_dir = observer.run_business_today_day1(
                Path(directory),
                run_id="demo-e2e",
                baseline_ref="origin/main",
                fetcher=self.fake_fetcher,
                now=self.now,
            )

            self.assertEqual({path.name for path in run_dir.iterdir()}, observer.DAY1_ARTIFACT_NAMES)
            self.assertEqual((run_dir / "response.xml").read_bytes(), self.candidate_response)
            manifest = json.loads((run_dir / "raw_manifest.json").read_text(encoding="utf-8"))
            raw_payload = json.loads((run_dir / "raw_items.json").read_text(encoding="utf-8"))
            diagnostics = json.loads((run_dir / "selector_diagnostics.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["response_sha256"], observer.sha256_bytes(self.candidate_response))
            self.assertEqual(manifest["item_count"], 2)
            self.assertEqual(len(manifest["baseline"]["sources"]), 4)
            self.assertIn("--include-paul-tan", manifest["baseline"]["cli_args"])
            self.assertEqual(
                [source["feed"] for source in manifest["baseline"]["sources"]],
                ["Malay Mail Malaysia", "Malay Mail Money", "Astro Awani National", "Paul Tan"],
            )
            self.assertEqual(len(diagnostics["baseline_feed_health"]), 4)

            raw_item = raw_payload["items"][0]
            self.assertEqual(
                raw_item["normalized_url"],
                "https://www.businesstoday.com.my/2026/08/25/sepang-road",
            )
            self.assertEqual(
                raw_item["item_id"],
                observer.stable_item_id(observer.DAY1_SOURCE_ID, raw_item["normalized_url"]),
            )
            self.assertEqual(
                {row["item_id"] for row in diagnostics["diagnostics"]},
                {item["item_id"] for item in raw_payload["items"]},
            )
            self.assertEqual(observer.validate_business_today_run(run_dir), [])

    def test_existing_run_id_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            run_dir = observer.run_business_today_day1(
                output_root,
                run_id="no-overwrite",
                baseline_ref="origin/main",
                fetcher=self.fake_fetcher,
                now=self.now,
            )
            original_response = (run_dir / "response.xml").read_bytes()
            with self.assertRaises(FileExistsError):
                observer.run_business_today_day1(
                    output_root,
                    run_id="no-overwrite",
                    baseline_ref="origin/main",
                    fetcher=self.fake_fetcher,
                    now=self.now,
                )
            self.assertEqual((run_dir / "response.xml").read_bytes(), original_response)

    def test_default_run_id_is_filesystem_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = observer.run_business_today_day1(
                Path(directory),
                baseline_ref="origin/main",
                fetcher=self.fake_fetcher,
                now=self.now,
            )
            self.assertRegex(run_dir.name, r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
            self.assertNotIn("+", run_dir.name)

    def test_html_response_is_rejected_without_leaving_a_partial_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)

            def html_fetcher(url: str) -> SimpleNamespace:
                if url == observer.DAY1_FEED_URL:
                    return SimpleNamespace(
                        ok=True,
                        data=b"<html><body>challenge</body></html>",
                        status="200",
                        content_type="text/html; charset=UTF-8",
                        method="fixture",
                        error="",
                    )
                return self.fake_fetcher(url)

            with self.assertRaisesRegex(RuntimeError, "returned HTML"):
                observer.run_business_today_day1(
                    output_root,
                    run_id="html-response",
                    baseline_ref="origin/main",
                    fetcher=html_fetcher,
                    now=self.now,
                )
            self.assertFalse((output_root / "html-response").exists())

    def test_annotation_validator_rejects_unknown_ids_and_missing_event_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = observer.run_business_today_day1(
                Path(directory),
                run_id="annotation-validation",
                baseline_ref="origin/main",
                fetcher=self.fake_fetcher,
                now=self.now,
            )
            annotation_path = run_dir / "annotations.json"
            payload = json.loads(annotation_path.read_text(encoding="utf-8"))
            payload["annotations"] = [
                {
                    "item_id": "unknown",
                    "manual_relevance": "noise",
                    "event_group": "",
                    "relationship_hint": "unknown",
                    "source_hint": "unknown",
                    "review_note": "fixture",
                    "reviewed_at": "2026-08-25T09:30:00+08:00",
                }
            ]
            annotation_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn("annotation_0_unknown_item_id", observer.validate_business_today_run(run_dir))

            raw_payload = json.loads((run_dir / "raw_items.json").read_text(encoding="utf-8"))
            payload["annotations"] = [
                {
                    "item_id": raw_payload["items"][0]["item_id"],
                    "manual_relevance": "useful",
                    "event_group": "",
                    "relationship_hint": "original",
                    "source_hint": "other",
                    "review_note": "fixture",
                    "reviewed_at": "2026-08-25T09:30:00+08:00",
                }
            ]
            annotation_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn("annotation_0_event_group", observer.validate_business_today_run(run_dir))

    def test_tracking_query_normalization_keeps_distinct_articles_distinct(self) -> None:
        first = observer.normalize_url("https://example.test/a/?utm_source=x&ref=one")
        tracked_again = observer.normalize_url("https://example.test/a?ref=one&utm_medium=email")
        second = observer.normalize_url("https://example.test/b?ref=one&utm_medium=email")
        self.assertEqual(first, tracked_again)
        self.assertNotEqual(first, second)
        self.assertEqual(
            observer.stable_item_id(observer.DAY1_SOURCE_ID, first),
            observer.stable_item_id(observer.DAY1_SOURCE_ID, tracked_again),
        )
        self.assertNotEqual(
            observer.stable_item_id(observer.DAY1_SOURCE_ID, first),
            observer.stable_item_id(observer.DAY1_SOURCE_ID, second),
        )


if __name__ == "__main__":
    unittest.main()
