#!/usr/bin/env python3
"""Validate one file or every immutable Meta Ads weekly artifact in a directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import load_json, validate_weekly_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path)
    group.add_argument("--directory", type=Path)
    args = parser.parse_args()
    try:
        paths = [args.input] if args.input else sorted(args.directory.glob("*.json"))
        if not paths:
            raise ContractError("no weekly artifacts found")
        events = sum(len(validate_weekly_candidate(load_json(path))["items"]) for path in paths)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {len(paths)} weekly artifacts with {events} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
