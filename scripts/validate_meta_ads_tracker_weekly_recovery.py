#!/usr/bin/env python3
"""Validate committed, non-public Meta Ads weekly recovery records."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_weekly_recovery import (
    DEFAULT_RECOVERY_DIRECTORY,
    validate_recovery_directory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_RECOVERY_DIRECTORY)
    args = parser.parse_args()
    try:
        count = validate_recovery_directory(args.directory)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {count} non-public weekly recovery record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
