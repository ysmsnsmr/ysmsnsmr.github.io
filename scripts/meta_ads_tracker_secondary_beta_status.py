#!/usr/bin/env python3
"""Build the public, signal-free status used by the Secondary β UI.

This module deliberately exposes no shadow observations.  It only translates
the Gate B evidence ledger into a small static status document so the public
UI cannot accidentally become a second publication path for non-official
signals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_gate_b import _automatic_source_ids, _load_json, evaluate, load_config, validate_record
from meta_ads_tracker_publication import write_json


SCHEMA_VERSION = "meta-ads-secondary-beta-status/v1"
DEFAULT_CONFIG = Path("config/meta_ads_secondary_shadow_gate_b.json")
DEFAULT_RECORD = Path("data/meta_ads_tracker_secondary_shadow_gate_b.json")
DEFAULT_SHADOW_CONFIG = Path("config/meta_ads_secondary_shadow_sources.json")
DEFAULT_OUTPUT = Path("meta-ads-updates/secondary-beta.json")


def build_status(config: dict[str, Any], record: dict[str, Any], *, automatic_source_ids: set[str]) -> dict[str, Any]:
    """Return the only Secondary β data allowed in the public site."""
    gate = evaluate(config, record, automatic_source_ids=automatic_source_ids)
    status = gate["status"]
    if status == "PASS":
        message = "Gate Bの証跡は満たしました。ただしSecondary signalの公開には、別途の人間による昇格判断が必要です。"
    else:
        message = "Gate BはBLOCKです。必要な人間レビュー証跡が揃うまで、Secondary βを進めません。"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "gateB": {"status": status, "message": message},
        "secondarySignalsVisible": False,
        "officialCandidateIntegration": False,
        "publicationEligible": False,
    }


def validate_status(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("Secondary β public status must be an object")
    expected = {
        "schemaVersion",
        "gateB",
        "secondarySignalsVisible",
        "officialCandidateIntegration",
        "publicationEligible",
    }
    if set(payload) != expected:
        raise ContractError("Secondary β public status has unsupported fields")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ContractError(f"Secondary β public status schemaVersion must be {SCHEMA_VERSION}")
    gate = payload["gateB"]
    if not isinstance(gate, dict) or set(gate) != {"status", "message"}:
        raise ContractError("Secondary β public status gateB must contain only status and message")
    if gate["status"] not in {"PASS", "BLOCK"} or not isinstance(gate["message"], str) or not gate["message"].strip():
        raise ContractError("Secondary β public status gateB is invalid")
    if any(payload[name] is not False for name in ("secondarySignalsVisible", "officialCandidateIntegration", "publicationEligible")):
        raise ContractError("Secondary β public status must not expose signals or create an official/publication path")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--shadow-config", type=Path, default=DEFAULT_SHADOW_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail unless the committed output equals the derived status")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        source_ids = _automatic_source_ids(args.shadow_config)
        record = validate_record(_load_json(args.record, "Gate B review record"), automatic_source_ids=source_ids)
        expected = validate_status(build_status(config, record, automatic_source_ids=source_ids))
        encoded = json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            actual = args.output.read_text(encoding="utf-8")
            if actual != encoded:
                raise ContractError("Secondary β public status is stale; rebuild it from the Gate B ledger")
        else:
            write_json(args.output, expected)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: Secondary β public status is {expected['gateB']['status']} and exposes no signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
