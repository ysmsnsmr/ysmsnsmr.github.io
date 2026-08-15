#!/usr/bin/env python3
"""Publish only human decisions bound to an immutable weekly artifact."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import (
    build_public_report,
    load_decisions,
    load_json,
    validate_weekly_candidate,
    write_json,
)


def resolve_weekly_path(directory: Path, cutoff_date: str) -> Path:
    try:
        parsed = date.fromisoformat(cutoff_date)
    except (TypeError, ValueError) as error:
        raise ContractError("weekly cutoff date must use a real YYYY-MM-DD date") from error
    if parsed.isoformat() != cutoff_date:
        raise ContractError("weekly cutoff date must use canonical YYYY-MM-DD")
    root = directory.resolve(strict=True)
    candidate = (root / f"{cutoff_date}.json").resolve(strict=True)
    if candidate.parent != root:
        raise ContractError("weekly artifact path escapes its configured directory")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weekly-dir", type=Path, default=Path("data/meta_ads_tracker_weekly"))
    parser.add_argument("--cutoff-date", required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        weekly_path = resolve_weekly_path(args.weekly_dir, args.cutoff_date)
        weekly = load_json(weekly_path)
        validate_weekly_candidate(weekly)
        decisions = load_decisions(args.decisions)
        report = build_public_report(
            weekly,
            decisions,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        write_json(args.output, report)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: published {len(report['items'])} approved Meta Ads events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
