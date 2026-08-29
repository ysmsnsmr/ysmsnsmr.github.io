#!/usr/bin/env python3
"""Validate committed Meta Ads delayed-recovery promotion records."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_recovery_promotion import (
    DEFAULT_PROMOTION_DIRECTORY,
    DEFAULT_RECOVERY_DIRECTORY,
    validate_promotion_directory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_PROMOTION_DIRECTORY)
    parser.add_argument("--recovery-directory", type=Path, default=DEFAULT_RECOVERY_DIRECTORY)
    args = parser.parse_args()
    try:
        count = validate_promotion_directory(args.directory, args.recovery_directory)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {count} delayed-recovery promotion record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
