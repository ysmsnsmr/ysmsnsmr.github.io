#!/usr/bin/env python3
"""Promote explicitly approved delayed-recovery events without rewriting weekly history."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_publication import (
    DECISION_OVERRIDE_FIELDS,
    HASH_RE,
    KUALA_LUMPUR,
    RECOVERY_PUBLIC_SCHEMA_VERSION,
    _enabled_sources,
    _merge_item,
    _validate_event_semantics,
    _validate_schema,
    canonical_hash,
    load_json,
    parse_timestamp,
    validate_public_report,
    write_json,
)
from meta_ads_tracker_weekly_recovery import validate_recovery


RECOVERY_DECISIONS_SCHEMA_VERSION = "meta-ads-tracker-recovery-decisions/v1"
PROMOTION_SCHEMA_VERSION = "meta-ads-tracker-recovery-promotion/v1"
SCHEMA = Path(__file__).resolve().parent / "schemas/meta_ads_tracker_recovery_promotion.schema.json"
DEFAULT_RECOVERY_DIRECTORY = Path("data/meta_ads_tracker_weekly_recovery")
DEFAULT_PROMOTION_DIRECTORY = Path("data/meta_ads_tracker_recovery_promotions")
DEFAULT_DECISIONS_PATH = Path("data/meta_ads_tracker_recovery_decisions.json")

APPROVAL_FIELDS = {
    "recoveryHash", "eventId", "revision", "sourceFingerprint", "originCandidateHash",
    "reviewStatus", "reviewer", "reviewedAt", "priority", "effectiveDate", "rollout",
    "targets", "businessImpact", "action", "notes",
}


def _canonical_date(value: str, label: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ContractError(f"{label} must use a real YYYY-MM-DD date") from error
    if parsed.isoformat() != value:
        raise ContractError(f"{label} must use canonical YYYY-MM-DD")
    return parsed


def resolve_recovery_path(directory: Path, cutoff_date: str) -> Path:
    parsed = _canonical_date(cutoff_date, "recovery cutoff date")
    if parsed.weekday() != 4:
        raise ContractError("recovery cutoff date must be a Friday")
    root = directory.resolve(strict=True)
    path = (root / f"{cutoff_date}.json").resolve(strict=True)
    if path.parent != root:
        raise ContractError("recovery artifact path escapes its configured directory")
    return path


def load_recovery_decisions(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "items"}:
        raise ContractError("recovery decisions have an invalid shape")
    if payload["schemaVersion"] != RECOVERY_DECISIONS_SCHEMA_VERSION:
        raise ContractError(f"recovery decisions schemaVersion must be {RECOVERY_DECISIONS_SCHEMA_VERSION}")
    if not isinstance(payload["items"], list):
        raise ContractError("recovery decisions.items must be an array")
    decisions: list[dict[str, Any]] = []
    keys: set[tuple[str, str, str]] = set()
    for index, decision in enumerate(payload["items"]):
        if not isinstance(decision, dict) or set(decision) - APPROVAL_FIELDS:
            raise ContractError(f"recovery decisions.items[{index}] has an invalid shape")
        required = {
            "recoveryHash", "eventId", "revision", "sourceFingerprint", "originCandidateHash",
            "reviewStatus", "reviewer", "reviewedAt", "priority", "businessImpact", "action",
        }
        if not required <= set(decision):
            raise ContractError(f"recovery decisions.items[{index}] is incomplete")
        for field in ("recoveryHash", "eventId", "revision", "sourceFingerprint", "originCandidateHash", "reviewer", "reviewedAt"):
            if not isinstance(decision[field], str) or not decision[field].strip():
                raise ContractError(f"recovery decisions.items[{index}].{field} must be a non-empty string")
        for field in ("recoveryHash", "revision", "sourceFingerprint", "originCandidateHash"):
            if not HASH_RE.fullmatch(decision[field]):
                raise ContractError(f"recovery decisions.items[{index}].{field} must be a SHA-256 hash")
        if decision["reviewStatus"] != "approved":
            raise ContractError(f"recovery decisions.items[{index}] must be explicitly approved")
        parse_timestamp(decision["reviewedAt"], f"recovery decisions.items[{index}].reviewedAt")
        key = (decision["recoveryHash"], decision["eventId"], decision["revision"])
        if key in keys:
            raise ContractError(f"duplicate recovery decision binding: {key}")
        keys.add(key)
        decisions.append(decision)
    return decisions


def _decision_matches_event(decision: dict[str, Any], recovery: dict[str, Any], event: dict[str, Any]) -> bool:
    return all((
        decision["recoveryHash"] == recovery["recoveryHash"],
        decision["eventId"] == event["eventId"],
        decision["revision"] == event["revision"],
        decision["sourceFingerprint"] == event["sourceFingerprint"],
        decision["originCandidateHash"] == event["originCandidateHash"],
    ))


def build_recovery_promotion(
    recovery: dict[str, Any],
    decisions: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    validate_recovery(recovery)
    generated = parse_timestamp(generated_at, "promotion.generatedAt")
    recovery_generated = parse_timestamp(recovery["generatedAt"], "recovery.generatedAt")
    if generated < recovery_generated:
        raise ContractError("promotion.generatedAt cannot precede recovery.generatedAt")
    current = [decision for decision in decisions if decision["recoveryHash"] == recovery["recoveryHash"]]
    events = {event["eventId"]: event for event in recovery["items"]}
    unknown = [decision["eventId"] for decision in current if decision["eventId"] not in events]
    if unknown:
        raise ContractError(f"recovery decisions reference unknown events: {sorted(unknown)}")
    approved_events: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    for event in recovery["items"]:
        matches = [decision for decision in current if decision["eventId"] == event["eventId"]]
        if not matches:
            continue
        if len(matches) != 1 or not _decision_matches_event(matches[0], recovery, event):
            raise ContractError(f"recovery decision binding mismatch for event {event['eventId']}")
        if parse_timestamp(matches[0]["reviewedAt"], "recovery decision.reviewedAt") < recovery_generated:
            raise ContractError(f"recovery decision predates immutable recovery record for event {event['eventId']}")
        approved_events.append(deepcopy(event))
        approvals.append(deepcopy(matches[0]))
    if recovery["items"] and not approved_events:
        raise ContractError("cannot promote delayed recovery events without matching human approval")
    promotion = {
        "schemaVersion": PROMOTION_SCHEMA_VERSION,
        "promotionHash": "",
        "generatedAt": generated.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "recoveryHash": recovery["recoveryHash"],
        "recoveryGeneratedAt": recovery["generatedAt"],
        "cutoffAt": recovery["cutoffAt"],
        "week": deepcopy(recovery["week"]),
        "recoveryReason": recovery["recoveryReason"],
        "missingPreCutoffDates": deepcopy(recovery["missingPreCutoffDates"]),
        "items": approved_events,
        "approvalRefs": approvals,
        "publicationEligible": True,
    }
    promotion["promotionHash"] = canonical_hash(promotion, "promotionHash")
    validate_recovery_promotion(promotion, recovery)
    return promotion


def validate_recovery_promotion(promotion: Any, recovery: dict[str, Any] | None = None) -> dict[str, Any]:
    _validate_schema(promotion, SCHEMA, "recovery promotion")
    assert isinstance(promotion, dict)
    if canonical_hash(promotion, "promotionHash") != promotion["promotionHash"]:
        raise ContractError("promotionHash does not match canonical promotion content")
    generated = parse_timestamp(promotion["generatedAt"], "promotion.generatedAt")
    recovery_generated = parse_timestamp(promotion["recoveryGeneratedAt"], "promotion.recoveryGeneratedAt")
    cutoff = parse_timestamp(promotion["cutoffAt"], "promotion.cutoffAt")
    if generated < recovery_generated or recovery_generated < cutoff:
        raise ContractError("promotion timestamps are not in recovery order")
    if promotion["publicationEligible"] is not True:
        raise ContractError("recovery promotion must be explicitly publication eligible")
    configured_sources = _enabled_sources(load_and_validate_source_config())
    events = {event["eventId"]: event for event in promotion["items"]}
    if len(events) != len(promotion["items"]):
        raise ContractError("recovery promotion must not repeat event IDs")
    for index, event in enumerate(promotion["items"]):
        _validate_event_semantics(event, index, configured_sources, weekly=True)
    approvals = promotion["approvalRefs"]
    keys: set[tuple[str, str, str]] = set()
    for index, approval in enumerate(approvals):
        key = (approval["recoveryHash"], approval["eventId"], approval["revision"])
        if key in keys:
            raise ContractError("recovery promotion must not repeat approval bindings")
        keys.add(key)
        event = events.get(approval["eventId"])
        if event is None:
            raise ContractError("recovery promotion approval references an unknown event")
        if approval["recoveryHash"] != promotion["recoveryHash"]:
            raise ContractError("recovery promotion approval has a different recoveryHash")
        for field in ("revision", "sourceFingerprint", "originCandidateHash"):
            if approval[field] != event[field]:
                raise ContractError(f"recovery promotion approval {field} does not match its event")
        if parse_timestamp(approval["reviewedAt"], "promotion approval.reviewedAt") < recovery_generated:
            raise ContractError("recovery promotion approval predates its recovery record")
    if set(events) != {approval["eventId"] for approval in approvals}:
        raise ContractError("recovery promotion items and approvals must match exactly")
    if recovery is not None:
        validate_recovery(recovery)
        for field in ("recoveryHash", "recoveryGeneratedAt", "cutoffAt", "week", "recoveryReason", "missingPreCutoffDates"):
            recovery_field = "generatedAt" if field == "recoveryGeneratedAt" else field
            if promotion[field] != recovery[recovery_field]:
                raise ContractError(f"recovery promotion {field} does not match immutable recovery")
        recovery_events = {event["eventId"]: event for event in recovery["items"]}
        for event in promotion["items"]:
            original = recovery_events.get(event["eventId"])
            if original != event:
                raise ContractError("recovery promotion item does not exactly match immutable recovery")
    return promotion


def build_recovery_public_report(promotion: dict[str, Any], generated_at: str) -> dict[str, Any]:
    validate_recovery_promotion(promotion)
    report = {
        "schemaVersion": RECOVERY_PUBLIC_SCHEMA_VERSION,
        "generatedAt": parse_timestamp(generated_at, "public generatedAt").astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "week": deepcopy(promotion["week"]),
        "filters": {"sourceId": "all", "priority": "all", "query": ""},
        "publication": {
            "mode": "delayed_recovery",
            "label": "遅延回復データ",
            "recoveryHash": promotion["recoveryHash"],
            "recoveryGeneratedAt": promotion["recoveryGeneratedAt"],
            "cutoffAt": promotion["cutoffAt"],
            "missingPreCutoffDates": deepcopy(promotion["missingPreCutoffDates"]),
        },
        "items": [],
    }
    approvals = {approval["eventId"]: approval for approval in promotion["approvalRefs"]}
    for event in promotion["items"]:
        report["items"].append(_merge_item(event, approvals[event["eventId"]]))
    validate_public_report(report)
    return report


def write_immutable_promotion(path: Path, promotion: dict[str, Any], recovery: dict[str, Any]) -> None:
    validate_recovery_promotion(promotion, recovery)
    if path.exists():
        existing = validate_recovery_promotion(load_json(path), recovery)
        if existing["promotionHash"] != promotion["promotionHash"]:
            raise ContractError(f"immutable recovery promotion already exists with different content: {path}")
        return
    write_json(path, promotion)


def validate_promotion_directory(directory: Path, recovery_directory: Path) -> int:
    if not directory.exists():
        return 0
    if not directory.is_dir():
        raise ContractError(f"promotion directory is not a directory: {directory}")
    count = 0
    for path in sorted(directory.glob("*.json")):
        promotion = load_json(path)
        cutoff_date = parse_timestamp(promotion.get("cutoffAt"), f"{path}.cutoffAt").astimezone(KUALA_LUMPUR).date().isoformat()
        if path.name != f"{cutoff_date}.json":
            raise ContractError(f"promotion filename must match its cutoff date: {path}")
        recovery = load_json(resolve_recovery_path(recovery_directory, cutoff_date))
        validate_recovery_promotion(promotion, recovery)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-dir", type=Path, default=DEFAULT_RECOVERY_DIRECTORY)
    parser.add_argument("--promotions-dir", type=Path, default=DEFAULT_PROMOTION_DIRECTORY)
    parser.add_argument("--cutoff-date", required=True)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS_PATH)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        recovery_path = resolve_recovery_path(args.recovery_dir, args.cutoff_date)
        recovery = load_json(recovery_path)
        decisions = load_recovery_decisions(args.decisions)
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        promotion = build_recovery_promotion(recovery, decisions, generated_at)
        promotion_path = args.promotions_dir / f"{args.cutoff_date}.json"
        write_immutable_promotion(promotion_path, promotion, recovery)
        report = build_recovery_public_report(promotion, generated_at)
        write_json(args.report_output, report)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: promoted {len(report['items'])} delayed-recovery Meta Ads event(s): {promotion_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
