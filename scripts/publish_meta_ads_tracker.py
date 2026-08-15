#!/usr/bin/env python3
"""Publish only explicitly approved Meta Ads tracker decisions."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import build_public_report, load_decisions, load_json, validate_candidate, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = load_json(args.candidate)
        validate_candidate(candidate)
        decisions = load_decisions(args.decisions)
        if candidate["items"] and not decisions:
            raise ContractError("cannot publish a changed candidate without an explicit approval decision")
        report = build_public_report(
            candidate,
            decisions,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        write_json(args.output, report)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: published {len(report['items'])} approved Meta Ads items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
