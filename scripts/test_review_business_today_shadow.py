#!/usr/bin/env python3
import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import review_business_today_shadow as review


class ReviewBusinessTodayShadowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 26, 10, 0, tzinfo=review.MYT)

    def make_run(self, directory: str) -> Path:
        run_dir = Path(directory) / "run"
        run_dir.mkdir()
        raw_items = [
            {"item_id": "item-1", "published_at": "2026-08-26T08:00:00+08:00", "title": "Transit update", "article_url": "https://example.test/1"},
            {"item_id": "item-2", "published_at": "2026-08-26T08:01:00+08:00", "title": "Market update", "article_url": "https://example.test/2"},
            {"item_id": "item-3", "published_at": "2026-08-26T08:02:00+08:00", "title": "Weather update", "article_url": "https://example.test/3"},
        ]
        diagnostics = [
            {"item_id": "item-1", "selector_score": 8, "selector_category": "【生活インパクト】", "selector_eligible": True, "selected_after_caps": True, "displaced_by_cap": False, "exclusion_reasons": []},
            {"item_id": "item-2", "selector_score": 5, "selector_category": "【知っておくと得】", "selector_eligible": True, "selected_after_caps": False, "displaced_by_cap": True, "exclusion_reasons": []},
            {"item_id": "item-3", "selector_score": 0, "selector_category": "【速報】", "selector_eligible": False, "selected_after_caps": False, "displaced_by_cap": False, "exclusion_reasons": ["selector_score_below_3"]},
        ]
        (run_dir / "raw_items.json").write_text(json.dumps({"items": raw_items}), encoding="utf-8")
        (run_dir / "annotations.json").write_text(json.dumps({"annotations": []}), encoding="utf-8")
        (run_dir / "selector_diagnostics.json").write_text(json.dumps({"diagnostics": diagnostics}), encoding="utf-8")
        return run_dir

    def test_export_import_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(directory)
            queue_path = Path(directory) / "queue.csv"
            self.assertEqual(review.export_queue_csv(run_dir, queue_path), 3)
            with queue_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0].update({"manual_relevance": "useful", "event_group": "transit-20260826", "relationship_hint": "original", "source_hint": "government"})
            rows[1].update({"manual_relevance": "noise", "relationship_hint": "unknown", "source_hint": "other", "review_note": "market-only"})
            with queue_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=review.QUEUE_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

            with patch.object(review, "assert_valid_business_today_run"):
                updates, annotations = review.import_queue_csv(run_dir, queue_path, now=self.now)
            self.assertEqual((updates, annotations), (2, 2))
            saved = json.loads((run_dir / "annotations.json").read_text(encoding="utf-8"))["annotations"]
            self.assertEqual(saved[0]["reviewed_at"], self.now.isoformat())
            summary = review.review_summary(run_dir)
            self.assertEqual(summary["pending_items"], 1)
            self.assertEqual(summary["reviewed_event_groups"], 1)
            self.assertEqual(summary["noise_rate"], "1/2 (50.0%)")
            self.assertEqual(summary["selector_recall_useful"], "1/1 (100.0%)")
            self.assertEqual(summary["selector_precision_reviewed"], "1/2 (50.0%)")

    def test_invalid_import_does_not_replace_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self.make_run(directory)
            queue_path = Path(directory) / "queue.csv"
            review.export_queue_csv(run_dir, queue_path)
            with queue_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["item_id"] = "unknown-item"
            rows[0]["manual_relevance"] = "noise"
            with queue_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=review.QUEUE_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

            before = (run_dir / "annotations.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "Unknown item_id"):
                review.import_queue_csv(run_dir, queue_path, now=self.now)
            self.assertEqual((run_dir / "annotations.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
