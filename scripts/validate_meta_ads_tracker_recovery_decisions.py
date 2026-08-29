#!/usr/bin/env python3
"""Validate human approval bindings for Meta Ads delayed recoveries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_recovery_promotion import DEFAULT_DECISIONS_PATH, load_recovery_decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_DECISIONS_PATH)
    args = parser.parse_args()
    try:
        decisions = load_recovery_decisions(args.input)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {len(decisions)} delayed-recovery human decision(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
