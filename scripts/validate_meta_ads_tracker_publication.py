#!/usr/bin/env python3
"""Validate a production Meta Ads tracker report before publication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_publication import load_json, validate_public_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/meta_ads_official_sources.json"))
    args = parser.parse_args()
    try:
        report = load_json(args.input)
        validate_public_report(report, load_and_validate_source_config(args.config))
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {len(report['items'])} approved Meta Ads items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
