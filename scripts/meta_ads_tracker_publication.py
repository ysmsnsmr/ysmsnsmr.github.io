#!/usr/bin/env python3
"""Shared candidate, approval, and public-report contracts for Meta Ads tracker."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config, validate_weekly_fixture


PUBLIC_SCHEMA_VERSION = "meta-ads-weekly-index/v1"
DECISIONS_SCHEMA_VERSION = "meta-ads-tracker-decisions/v1"
CANDIDATE_SCHEMA_VERSION = "meta-ads-tracker-candidates/v1"
DECISION_FIELDS = {
    "reviewStatus",
    "reviewer",
    "reviewedAt",
    "priority",
    "effectiveDate",
    "rollout",
    "targets",
    "businessImpact",
    "action",
    "notes",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"missing JSON file: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON in {path}: {error}") from error


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value.strip()


def _iso_timestamp(value: Any, label: str) -> str:
    text = _non_empty_string(value, label)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    return text


def validate_candidate(candidate: Any, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(candidate, dict) or candidate.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        raise ContractError(f"candidate schemaVersion must be {CANDIDATE_SCHEMA_VERSION}")
    if not isinstance(candidate.get("generatedAt"), str):
        raise ContractError("candidate.generatedAt is required")
    if not isinstance(candidate.get("week"), dict) or not isinstance(candidate.get("items"), list):
        raise ContractError("candidate requires week and items")
    config = source_config or load_and_validate_source_config()
    configured_sources = {
        source["id"]: source
        for source in config["sources"]
        if source["enabled"] and source["access"] == "public"
    }
    item_ids: set[str] = set()
    for index, raw_item in enumerate(candidate["items"]):
        if not isinstance(raw_item, dict):
            raise ContractError(f"candidate.items[{index}] must be an object")
        item_id = _non_empty_string(raw_item.get("id"), f"candidate.items[{index}].id")
        if item_id in item_ids:
            raise ContractError(f"duplicate candidate item id: {item_id}")
        item_ids.add(item_id)
        source = configured_sources.get(raw_item.get("sourceId"))
        if source is None:
            raise ContractError(f"candidate.items[{index}].sourceId is not enabled/public")
        official_host = urlparse(str(raw_item.get("officialUrl") or "")).hostname
        configured_host = urlparse(source["sourceUrl"]).hostname
        if official_host != configured_host:
            raise ContractError(
                f"candidate.items[{index}].officialUrl must stay on configured official host {configured_host}"
            )
        if raw_item.get("reviewStatus") != "pending":
            raise ContractError(f"candidate.items[{index}].reviewStatus must be pending")
        context = raw_item.get("sourceContext")
        if context is not None and (not isinstance(context, str) or len(context) > 4000):
            raise ContractError(f"candidate.items[{index}].sourceContext is too large")
    return candidate


def load_decisions(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != DECISIONS_SCHEMA_VERSION:
        raise ContractError(f"decisions schemaVersion must be {DECISIONS_SCHEMA_VERSION}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ContractError("decisions.items must be an array")
    decisions: dict[str, dict[str, Any]] = {}
    for index, decision in enumerate(raw_items):
        if not isinstance(decision, dict):
            raise ContractError(f"decisions.items[{index}] must be an object")
        item_id = _non_empty_string(decision.get("itemId"), f"decisions.items[{index}].itemId")
        if item_id in decisions:
            raise ContractError(f"duplicate decision itemId: {item_id}")
        unknown = set(decision) - {"itemId", *DECISION_FIELDS}
        if unknown:
            raise ContractError(f"decision {item_id} has unknown fields: {sorted(unknown)}")
        if decision.get("reviewStatus") != "approved":
            raise ContractError(f"decision {item_id} must be explicitly approved")
        _non_empty_string(decision.get("reviewer"), f"decision {item_id}.reviewer")
        _iso_timestamp(decision.get("reviewedAt"), f"decision {item_id}.reviewedAt")
        decisions[item_id] = decision
    return decisions


def _merge_item(candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    public_keys = {
        "id", "changeType", "sourceId", "title", "officialUrl", "priority",
        "announcementDate", "effectiveDate", "rollout", "targets", "businessImpact", "action",
    }
    item = {key: value for key, value in candidate.items() if key in public_keys}
    for key in DECISION_FIELDS:
        if key in {"reviewStatus", "reviewer", "reviewedAt", "notes"}:
            continue
        if key in decision:
            item[key] = decision[key]
    item["reviewStatus"] = "approved"
    return item


def build_public_report(candidate: dict[str, Any], decisions: dict[str, dict[str, Any]], generated_at: str) -> dict[str, Any]:
    validate_candidate(candidate)
    if candidate["items"] and not decisions:
        raise ContractError("cannot build a public report for changed items without explicit approvals")
    candidate_ids = {item["id"] for item in candidate["items"]}
    unknown_decisions = set(decisions) - candidate_ids
    if unknown_decisions:
        raise ContractError(f"decisions reference items outside this candidate: {sorted(unknown_decisions)}")
    items = [_merge_item(item, decisions[item["id"]]) for item in candidate["items"] if item["id"] in decisions]
    report = {
        "schemaVersion": PUBLIC_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "week": candidate["week"],
        "filters": {"sourceId": "all", "priority": "all", "query": ""},
        "items": items,
    }
    validate_public_report(report)
    return report


def validate_public_report(report: Any, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schemaVersion") != PUBLIC_SCHEMA_VERSION:
        raise ContractError(f"public report schemaVersion must be {PUBLIC_SCHEMA_VERSION}")
    if not isinstance(report.get("generatedAt"), str):
        raise ContractError("public report generatedAt is required")
    week = report.get("week")
    if not isinstance(week, dict) or not {"startDate", "endDate", "label"} <= set(week):
        raise ContractError("public report week is incomplete")
    items = report.get("items")
    if not isinstance(items, list):
        raise ContractError("public report items must be an array")
    fixture = {
        "schemaVersion": "meta-ads-weekly-index-fixture/v1",
        "fixture": {
            "name": "production-week",
            "state": "empty_week" if not items else "normal_week",
            "description": "Production-approved Meta Ads tracker report.",
        },
        "week": week,
        "filters": {"sourceId": "all", "priority": "all", "query": ""},
        "items": items,
    }
    validated = validate_weekly_fixture(fixture, source_config, require_anonymised_urls=False)
    return validated
