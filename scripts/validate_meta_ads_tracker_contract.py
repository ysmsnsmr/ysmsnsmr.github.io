#!/usr/bin/env python3
"""Validate the Meta Ads tracker source configuration and static fixtures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_contract import (
    ContractError,
    DEFAULT_FIXTURE_DIRECTORY,
    DEFAULT_SOURCE_CONFIG,
    load_and_validate_fixture,
    load_and_validate_source_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURE_DIRECTORY)
    args = parser.parse_args()

    try:
        config = load_and_validate_source_config(args.config)
        fixture_paths = sorted(args.fixtures_dir.glob("*.json"))
        if not fixture_paths:
            raise ContractError(f"no fixture JSON files found in {args.fixtures_dir}")
        fixtures = [load_and_validate_fixture(path) for path in fixture_paths]
    except ContractError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        "PASS: "
        f"{len(config['sources'])} official-source configurations and "
        f"{len(fixtures)} anonymous weekly fixtures satisfy the contract."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
