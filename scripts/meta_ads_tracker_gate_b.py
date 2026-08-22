#!/usr/bin/env python3
"""Validate human evidence for the secondary-shadow Beta Readiness gate.

The gate does not collect from third-party sources and does not promote a
shadow signal.  It only evaluates a reviewed, versioned ledger committed in a
normal pull request.  A valid but incomplete ledger is BLOCK, not PASS.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from meta_ads_tracker_contract import ContractError, _expect_identifier, _expect_https_url


CONFIG_SCHEMA_VERSION = "meta-ads-secondary-shadow-gate-b-config/v1"
RECORD_SCHEMA_VERSION = "meta-ads-secondary-shadow-gate-b-record/v1"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/meta_ads_secondary_shadow_gate_b.json"
DEFAULT_RECORD = Path(__file__).resolve().parents[1] / "data/meta_ads_tracker_secondary_shadow_gate_b.json"
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
OUTCOMES = {"useful", "not_useful", "duplicate", "insufficient_evidence"}
VERIFICATION_OUTCOMES = {"official_source_found", "not_found", "not_checked"}


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    if set(value) != expected:
        raise ContractError(f"{label} keys must be exactly {', '.join(sorted(expected))}")
    return value


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value.strip()


def _expect_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContractError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def parse_timestamp(value: Any, label: str) -> datetime:
    text = _expect_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include a timezone")
    return parsed


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"missing {label}: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid {label} JSON: {path}") from error


def validate_config(payload: Any) -> dict[str, Any]:
    config = _expect_keys(payload, {"schemaVersion", "criteria", "reviewRecordPath", "reviewTimezone"}, "Gate B config")
    if config["schemaVersion"] != CONFIG_SCHEMA_VERSION:
        raise ContractError(f"Gate B config schemaVersion must be {CONFIG_SCHEMA_VERSION}")
    criteria = _expect_keys(
        config["criteria"],
        {
            "minimumObservationDays",
            "minimumReviewsTotal",
            "minimumReviewsPerAutomaticSource",
            "minimumUsefulReviews",
            "maximumReviewMinutesPerIsoWeek",
            "blockingFindingCategories",
        },
        "Gate B criteria",
    )
    expected_criteria = {
        "minimumObservationDays": 14,
        "minimumReviewsTotal": 10,
        "minimumReviewsPerAutomaticSource": 3,
        "minimumUsefulReviews": 3,
        "maximumReviewMinutesPerIsoWeek": 60,
    }
    for key, expected in expected_criteria.items():
        if criteria[key] != expected:
            raise ContractError(f"Gate B criteria.{key} must remain {expected}")
    if criteria["blockingFindingCategories"] != ["fix", "dlq"]:
        raise ContractError("Gate B must block unresolved fix and dlq findings")
    if config["reviewRecordPath"] != "data/meta_ads_tracker_secondary_shadow_gate_b.json":
        raise ContractError("Gate B reviewRecordPath must be the dedicated review ledger")
    if config["reviewTimezone"] != "Asia/Kuala_Lumpur":
        raise ContractError("Gate B reviewTimezone must be Asia/Kuala_Lumpur")
    return config


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return validate_config(_load_json(path, "Gate B config"))


def _automatic_source_ids(shadow_config_path: Path) -> set[str]:
    # Keep Gate B's required source set tied to the P5-D source registry.
    from meta_ads_tracker_secondary_shadow import load_and_validate_config

    return {source["id"] for source in load_and_validate_config(shadow_config_path)["sources"] if source["enabled"]}


def _validate_optional_timestamp(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    return parse_timestamp(value, label)


def validate_record(
    payload: Any,
    *,
    automatic_source_ids: set[str],
) -> dict[str, Any]:
    record = _expect_keys(payload, {"schemaVersion", "observationWindow", "reviews", "findings"}, "Gate B review record")
    if record["schemaVersion"] != RECORD_SCHEMA_VERSION:
        raise ContractError(f"Gate B review record schemaVersion must be {RECORD_SCHEMA_VERSION}")
    window = _expect_keys(record["observationWindow"], {"startedAt", "endedAt"}, "Gate B observationWindow")
    started_at = _validate_optional_timestamp(window["startedAt"], "Gate B observationWindow.startedAt")
    ended_at = _validate_optional_timestamp(window["endedAt"], "Gate B observationWindow.endedAt")
    if (started_at is None) != (ended_at is None):
        raise ContractError("Gate B observationWindow must set both timestamps or neither")
    if started_at and ended_at and ended_at < started_at:
        raise ContractError("Gate B observationWindow.endedAt must not precede startedAt")

    reviews = record["reviews"]
    if not isinstance(reviews, list):
        raise ContractError("Gate B reviews must be an array")
    review_ids: set[str] = set()
    reviewed_signals: set[tuple[str, str, str]] = set()
    for index, value in enumerate(reviews):
        review = _expect_keys(
            value,
            {
                "reviewId",
                "sourceId",
                "signalId",
                "observedAt",
                "reviewedAt",
                "workflowRunId",
                "stateBranchCommit",
                "artifactSha256",
                "outcome",
                "officialVerification",
                "officialReferenceUrl",
                "minutesSpent",
                "notes",
            },
            f"Gate B reviews[{index}]",
        )
        review_id = _expect_identifier(review["reviewId"], f"Gate B reviews[{index}].reviewId")
        if review_id in review_ids:
            raise ContractError(f"duplicate Gate B reviewId: {review_id}")
        review_ids.add(review_id)
        source_id = _expect_identifier(review["sourceId"], f"Gate B reviews[{index}].sourceId")
        if source_id not in automatic_source_ids:
            raise ContractError(f"Gate B reviews[{index}].sourceId is not an automatic shadow source")
        signal_id = _expect_string(review["signalId"], f"Gate B reviews[{index}].signalId")
        observed_at = parse_timestamp(review["observedAt"], f"Gate B reviews[{index}].observedAt")
        reviewed_at = parse_timestamp(review["reviewedAt"], f"Gate B reviews[{index}].reviewedAt")
        if reviewed_at < observed_at:
            raise ContractError(f"Gate B reviews[{index}].reviewedAt must not precede observedAt")
        if started_at and ended_at and not started_at <= observed_at <= ended_at:
            raise ContractError(f"Gate B reviews[{index}].observedAt must be within observationWindow")
        run_id = _expect_string(review["workflowRunId"], f"Gate B reviews[{index}].workflowRunId")
        if not run_id.isdigit():
            raise ContractError(f"Gate B reviews[{index}].workflowRunId must be a GitHub run id")
        commit = _expect_string(review["stateBranchCommit"], f"Gate B reviews[{index}].stateBranchCommit")
        if not GIT_SHA_RE.fullmatch(commit):
            raise ContractError(f"Gate B reviews[{index}].stateBranchCommit must be a 40-character commit SHA")
        artifact_hash = _expect_string(review["artifactSha256"], f"Gate B reviews[{index}].artifactSha256")
        if not HASH_RE.fullmatch(artifact_hash):
            raise ContractError(f"Gate B reviews[{index}].artifactSha256 must be SHA-256")
        signal_key = (source_id, signal_id, commit)
        if signal_key in reviewed_signals:
            raise ContractError("the same shadow signal revision may be reviewed only once")
        reviewed_signals.add(signal_key)
        if review["outcome"] not in OUTCOMES:
            raise ContractError(f"Gate B reviews[{index}].outcome is unsupported")
        if review["officialVerification"] not in VERIFICATION_OUTCOMES:
            raise ContractError(f"Gate B reviews[{index}].officialVerification is unsupported")
        reference = review["officialReferenceUrl"]
        if review["officialVerification"] == "official_source_found":
            _expect_https_url(reference, f"Gate B reviews[{index}].officialReferenceUrl")
        elif reference is not None:
            raise ContractError(f"Gate B reviews[{index}].officialReferenceUrl must be null without official verification")
        _expect_int(review["minutesSpent"], f"Gate B reviews[{index}].minutesSpent", 1, 60)
        if review["notes"] is not None and not isinstance(review["notes"], str):
            raise ContractError(f"Gate B reviews[{index}].notes must be a string or null")

    findings = record["findings"]
    if not isinstance(findings, list):
        raise ContractError("Gate B findings must be an array")
    finding_ids: set[str] = set()
    for index, value in enumerate(findings):
        finding = _expect_keys(value, {"findingId", "category", "status", "openedAt", "resolvedAt", "summary"}, f"Gate B findings[{index}]")
        finding_id = _expect_identifier(finding["findingId"], f"Gate B findings[{index}].findingId")
        if finding_id in finding_ids:
            raise ContractError(f"duplicate Gate B findingId: {finding_id}")
        finding_ids.add(finding_id)
        if finding["category"] not in {"fix", "dlq"}:
            raise ContractError(f"Gate B findings[{index}].category must be fix or dlq")
        opened_at = parse_timestamp(finding["openedAt"], f"Gate B findings[{index}].openedAt")
        if finding["status"] == "open":
            if finding["resolvedAt"] is not None:
                raise ContractError(f"Gate B open finding {finding_id} must not have resolvedAt")
        elif finding["status"] == "resolved":
            resolved_at = parse_timestamp(finding["resolvedAt"], f"Gate B findings[{index}].resolvedAt")
            if resolved_at < opened_at:
                raise ContractError(f"Gate B resolved finding {finding_id} precedes its openedAt")
        else:
            raise ContractError(f"Gate B findings[{index}].status must be open or resolved")
        _expect_string(finding["summary"], f"Gate B findings[{index}].summary")
    return record


def evaluate(config: dict[str, Any], record: dict[str, Any], *, automatic_source_ids: set[str]) -> dict[str, Any]:
    criteria = config["criteria"]
    zone = ZoneInfo(config["reviewTimezone"])
    reasons: list[str] = []
    window = record["observationWindow"]
    if window["startedAt"] is None:
        reasons.append("observation window is not declared")
    else:
        started = parse_timestamp(window["startedAt"], "Gate B observationWindow.startedAt")
        ended = parse_timestamp(window["endedAt"], "Gate B observationWindow.endedAt")
        if ended - started < timedelta(days=criteria["minimumObservationDays"]):
            reasons.append(f"observation window is shorter than {criteria['minimumObservationDays']} days")

    reviews = record["reviews"]
    source_counts = Counter(review["sourceId"] for review in reviews)
    useful_count = sum(review["outcome"] == "useful" for review in reviews)
    if len(reviews) < criteria["minimumReviewsTotal"]:
        reasons.append(f"reviews {len(reviews)}/{criteria['minimumReviewsTotal']}")
    for source_id in sorted(automatic_source_ids):
        if source_counts[source_id] < criteria["minimumReviewsPerAutomaticSource"]:
            reasons.append(f"{source_id} reviews {source_counts[source_id]}/{criteria['minimumReviewsPerAutomaticSource']}")
    if useful_count < criteria["minimumUsefulReviews"]:
        reasons.append(f"useful reviews {useful_count}/{criteria['minimumUsefulReviews']}")

    weekly_minutes: dict[str, int] = defaultdict(int)
    for review in reviews:
        reviewed_at = parse_timestamp(review["reviewedAt"], "Gate B reviewedAt").astimezone(zone)
        iso_year, iso_week, _ = reviewed_at.isocalendar()
        weekly_minutes[f"{iso_year}-W{iso_week:02d}"] += review["minutesSpent"]
    for week, minutes in sorted(weekly_minutes.items()):
        if minutes > criteria["maximumReviewMinutesPerIsoWeek"]:
            reasons.append(f"{week} review time {minutes}/{criteria['maximumReviewMinutesPerIsoWeek']} minutes")

    open_findings = [
        finding["findingId"]
        for finding in record["findings"]
        if finding["category"] in criteria["blockingFindingCategories"] and finding["status"] == "open"
    ]
    if open_findings:
        reasons.append(f"unresolved findings: {', '.join(open_findings)}")
    return {
        "schemaVersion": "meta-ads-secondary-shadow-gate-b-result/v1",
        "status": "PASS" if not reasons else "BLOCK",
        "criteria": criteria,
        "evidence": {
            "reviewCount": len(reviews),
            "usefulReviewCount": useful_count,
            "reviewsByAutomaticSource": {source_id: source_counts[source_id] for source_id in sorted(automatic_source_ids)},
            "reviewMinutesByIsoWeek": dict(sorted(weekly_minutes.items())),
            "openFindingIds": open_findings,
        },
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--shadow-config", type=Path, default=Path("config/meta_ads_secondary_shadow_sources.json"))
    parser.add_argument("--validate-only", action="store_true", help="check ledger shape without asserting readiness")
    parser.add_argument("--require-ready", action="store_true", help="return non-zero unless evidence satisfies every Gate B criterion")
    parser.add_argument("--output", type=Path, help="write the evaluation result as JSON")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        source_ids = _automatic_source_ids(args.shadow_config)
        record = validate_record(_load_json(args.record, "Gate B review record"), automatic_source_ids=source_ids)
        result = evaluate(config, record, automatic_source_ids=source_ids)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    if args.validate_only:
        print("PASS: Gate B ledger contract is valid; readiness is evaluated separately.")
        return 0
    print(f"Gate B: {result['status']}")
    for reason in result["reasons"]:
        print(f"- {reason}")
    return 2 if args.require_ready and result["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
