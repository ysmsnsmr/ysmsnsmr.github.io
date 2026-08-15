#!/usr/bin/env python3
"""Resolve a validated YYYY-MM-DD input to a weekly artifact path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from publish_meta_ads_tracker import resolve_weekly_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--cutoff-date", required=True)
    args = parser.parse_args()
    try:
        path = resolve_weekly_path(args.directory, args.cutoff_date)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
