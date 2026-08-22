#!/usr/bin/env python3
"""Validate the isolated non-official secondary-signal source registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_secondary_shadow import DEFAULT_CONFIG, load_and_validate_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config = load_and_validate_config(args.config)
    except ContractError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    automatic = sum(source["enabled"] for source in config["sources"])
    print(f"PASS: {automatic} automatic secondary shadow sources remain isolated from official publication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
