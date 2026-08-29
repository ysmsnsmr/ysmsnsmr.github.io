#!/usr/bin/env python3
"""Validate the Personal Feed configuration, state, and public payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_personal_feed import DEFAULT_CONFIG, DEFAULT_OUTPUT, DEFAULT_STATE, load_config, validate_feed, validate_state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        state = validate_state(json.loads(args.state.read_text(encoding="utf-8")), config)
        feed = validate_feed(json.loads(args.input.read_text(encoding="utf-8")), config)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated Personal Feed with {len(config['sources'])} sources, {sum(len(item['items']) for item in state['sources'].values())} retained records, and {len(feed['items'])} public items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
