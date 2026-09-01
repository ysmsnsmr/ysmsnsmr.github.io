#!/usr/bin/env python3
"""Run one durable BusinessToday raw-shadow collection per MYT day.

This is intentionally a thin operational wrapper around the Day-1 harness:
it does not change production sources, selector policy, or rendered news.
"""

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from experiment_observe_rss_candidate_backlog import (
        DAY1_SCHEMA_VERSION,
        DAY1_SOURCE_ID,
        DAY1_FEED_URL,
        MYT,
        run_business_today_day1,
    )
except ModuleNotFoundError:
    from scripts.experiment_observe_rss_candidate_backlog import (
        DAY1_SCHEMA_VERSION,
        DAY1_SOURCE_ID,
        DAY1_FEED_URL,
        MYT,
        run_business_today_day1,
    )


WINDOW_SCHEMA_VERSION = "malaysia-news-source-shadow/window-runner/v1"
DEFAULT_MAX_DAYS = 7
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "tmp" / "malaysia_news_source_shadow" / "business_today"


@dataclass(frozen=True)
class WindowResult:
    status: str
    collected_dates: int
    run_dir: Path | None = None
    receipt_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect at most one durable BusinessToday raw shadow artifact per MYT date."
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--feed-url", default=DAY1_FEED_URL)
    return parser.parse_args()


def parse_retrieved_date(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        return ""
    return parsed.astimezone(MYT).date().isoformat()


def collected_dates(output_root: Path) -> set[str]:
    if not output_root.is_dir():
        return set()
    dates: set[str] = set()
    for run_dir in output_root.iterdir():
        manifest_path = run_dir / "raw_manifest.json"
        if not run_dir.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        if manifest.get("schema_version") != DAY1_SCHEMA_VERSION:
            continue
        if manifest.get("source_id") != DAY1_SOURCE_ID:
            continue
        retrieved_date = parse_retrieved_date(manifest.get("retrieved_at"))
        if retrieved_date:
            dates.add(retrieved_date)
    return dates


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with temporary.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_failure_receipt(output_root: Path, now: datetime, exc: Exception) -> Path:
    failures = output_root / "failures"
    failures.mkdir(parents=True, exist_ok=True)
    safe_timestamp = now.astimezone(MYT).strftime("%Y%m%dT%H%M%S%f")
    receipt = failures / f"failure-{safe_timestamp}.json"
    if receipt.exists():
        raise FileExistsError(f"Refusing to overwrite existing failure receipt: {receipt}")
    atomic_write_json(
        receipt,
        {
            "schema_version": WINDOW_SCHEMA_VERSION,
            "observed_at": now.astimezone(MYT).isoformat(),
            "target_date": now.astimezone(MYT).date().isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )
    return receipt


def run_daily_window(
    output_root: Path,
    max_days: int = DEFAULT_MAX_DAYS,
    baseline_ref: str | None = None,
    feed_url: str = DAY1_FEED_URL,
    now: datetime | None = None,
    runner: Callable[..., Path] = run_business_today_day1,
) -> WindowResult:
    if max_days < 1:
        raise ValueError("max_days must be 1 or greater.")
    observed_at = (now or datetime.now(MYT)).astimezone(MYT)
    output_root.mkdir(parents=True, exist_ok=True)
    dates = collected_dates(output_root)
    today = observed_at.date().isoformat()
    if len(dates) >= max_days:
        return WindowResult("completed_window", len(dates))
    if today in dates:
        return WindowResult("skipped_already_collected_today", len(dates))

    try:
        run_dir = runner(
            output_root,
            baseline_ref=baseline_ref,
            feed_url=feed_url,
            now=observed_at,
        )
    except Exception as exc:
        receipt = write_failure_receipt(output_root, observed_at, exc)
        return WindowResult("failed", len(dates), receipt_path=receipt)
    return WindowResult("collected", len(dates) + 1, run_dir=run_dir)


def main() -> int:
    args = parse_args()
    try:
        result = run_daily_window(
            Path(args.output_root),
            max_days=args.max_days,
            baseline_ref=args.baseline_ref,
            feed_url=args.feed_url,
        )
    except (OSError, ValueError) as exc:
        print(f"BusinessToday 7-day shadow: FAIL\nreason: {exc}")
        return 1
    print(f"BusinessToday 7-day shadow: {result.status}")
    print(f"collected_dates: {result.collected_dates}/{args.max_days}")
    if result.run_dir:
        print(f"run directory: {result.run_dir}")
    if result.receipt_path:
        print(f"failure receipt: {result.receipt_path}")
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
