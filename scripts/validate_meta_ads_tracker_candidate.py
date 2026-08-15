#!/usr/bin/env python3
"""Validate one versioned Meta Ads daily candidate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import load_json, validate_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = validate_candidate(load_json(args.input))
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {len(candidate['items'])} daily candidate events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
