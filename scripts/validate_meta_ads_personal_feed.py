#!/usr/bin/env python3
"""Validate the Personal Feed configuration, state, and public payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from meta_ads_tracker_contract import ContractError
from meta_ads_personal_feed import DEFAULT_CONFIG, DEFAULT_OUTPUT, DEFAULT_STATE, load_config, validate_feed, validate_state


def validate_current_relevance_revisions(state: dict, config: dict) -> None:
    """Require persisted source rules to match the configured rules.

    This is intentionally stricter than the collector's normal validation.  It
    is used by pull-request CI so a relevance-rule change cannot merge before
    its source-local reseed has written the corresponding state.
    """
    configured = {
        source["id"]: source["relevanceRevision"]
        for source in [*config["sources"], *config["discoveredSources"]]
    }
    missing = sorted(set(configured) - set(state["sources"]))
    if missing:
        raise ContractError(
            "personal feed state is missing configured source(s); run a source-local reseed first: "
            + ", ".join(missing)
        )
    stale = sorted(
        source_id
        for source_id, configured_revision in configured.items()
        if state["sources"][source_id].get("relevanceRevision") != configured_revision
    )
    if stale:
        raise ContractError(
            "personal feed state relevanceRevision differs from config; run source-local reseed before merge: "
            + ", ".join(stale)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-current-relevance-revisions",
        action="store_true",
        help="require every configured source state to match its configured relevanceRevision",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        state = validate_state(json.loads(args.state.read_text(encoding="utf-8")), config)
        feed = validate_feed(json.loads(args.input.read_text(encoding="utf-8")), config)
        if args.require_current_relevance_revisions:
            validate_current_relevance_revisions(state, config)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    configured_sources = len(config["sources"]) + len(config["discoveredSources"])
    print(f"PASS: validated Personal Feed with {configured_sources} sources, {sum(len(item['items']) for item in state['sources'].values())} retained records, and {len(feed['items'])} public items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
