#!/usr/bin/env python3
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import run_business_today_shadow_window as window


class BusinessTodayShadowWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 26, 9, 0, tzinfo=window.MYT)

    def write_manifest(self, output_root: Path, run_id: str, observed_at: datetime) -> Path:
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "raw_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": window.DAY1_SCHEMA_VERSION,
                    "source_id": window.DAY1_SOURCE_ID,
                    "retrieved_at": observed_at.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        return run_dir

    def test_collects_once_then_skips_the_same_myt_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            calls = []

            def runner(root: Path, *, now: datetime, **_: object) -> Path:
                calls.append(now)
                return self.write_manifest(root, "first", now)

            first = window.run_daily_window(output_root, now=self.now, runner=runner)
            second = window.run_daily_window(output_root, now=self.now, runner=runner)
            self.assertEqual(first.status, "collected")
            self.assertEqual(second.status, "skipped_already_collected_today")
            self.assertEqual(len(calls), 1)

    def test_forwards_candidate_feed_url_to_day_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            calls = []

            def runner(root: Path, *, now: datetime, feed_url: str, **_: object) -> Path:
                calls.append(feed_url)
                return self.write_manifest(root, "news", now)

            result = window.run_daily_window(
                output_root,
                now=self.now,
                feed_url="https://example.test/category/news/feed/",
                runner=runner,
            )

            self.assertEqual(result.status, "collected")
            self.assertEqual(calls, ["https://example.test/category/news/feed/"])

    def test_stops_after_seven_distinct_dates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for index in range(7):
                self.write_manifest(
                    output_root,
                    f"run-{index}",
                    self.now - timedelta(days=index),
                )

            result = window.run_daily_window(output_root, now=self.now, runner=lambda *_a, **_k: self.fail("runner"))
            self.assertEqual(result.status, "completed_window")
            self.assertEqual(result.collected_dates, 7)

    def test_failure_is_retained_as_an_individual_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)

            def failing_runner(*_args: object, **_kwargs: object) -> Path:
                raise RuntimeError("fixture fetch failure")

            result = window.run_daily_window(output_root, now=self.now, runner=failing_runner)
            self.assertEqual(result.status, "failed")
            self.assertIsNotNone(result.receipt_path)
            receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["error_type"], "RuntimeError")
            self.assertEqual(receipt["error"], "fixture fetch failure")
            self.assertEqual(window.collected_dates(output_root), set())


if __name__ == "__main__":
    unittest.main()
