#!/usr/bin/env python3
"""Versioned daily, weekly, approval, and public-report contracts."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config, validate_weekly_fixture


PUBLIC_SCHEMA_VERSION = "meta-ads-weekly-index/v1"
DECISIONS_SCHEMA_VERSION = "meta-ads-tracker-decisions/v2"
CANDIDATE_SCHEMA_VERSION = "meta-ads-tracker-candidates/v2"
WEEKLY_SCHEMA_VERSION = "meta-ads-tracker-weekly-candidate/v1"
SCHEMA_DIRECTORY = Path(__file__).resolve().parent / "schemas"
CANDIDATE_SCHEMA = SCHEMA_DIRECTORY / "meta_ads_tracker_candidate.schema.json"
WEEKLY_SCHEMA = SCHEMA_DIRECTORY / "meta_ads_tracker_weekly.schema.json"
KUALA_LUMPUR = ZoneInfo("Asia/Kuala_Lumpur")
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
DECISION_OVERRIDE_FIELDS = {
    "priority",
    "effectiveDate",
    "rollout",
    "targets",
    "businessImpact",
    "action",
}
DECISION_FIELDS = {
    "eventId",
    "revision",
    "sourceFingerprint",
    "originCandidateHash",
    "weeklyHash",
    "reviewStatus",
    "reviewer",
    "reviewedAt",
    *DECISION_OVERRIDE_FIELDS,
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


def canonical_hash(value: Any, hash_field: str | None = None) -> str:
    payload = deepcopy(value)
    if hash_field is not None and isinstance(payload, dict):
        payload.pop(hash_field, None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_subject_id(source_id: str, official_url: str) -> str:
    digest = hashlib.sha256(official_url.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}-{digest}"


def make_event_id(source_id: str, subject_id: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{subject_id}\n{fingerprint}".encode("utf-8")).hexdigest()[:20]
    return f"{source_id}-{digest}"


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value.strip()


def parse_timestamp(value: Any, label: str) -> datetime:
    text = _non_empty_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include a timezone")
    return parsed


def _schema_validator(schema_path: Path) -> Draft202012Validator:
    schema = load_json(schema_path)
    candidate_schema = load_json(CANDIDATE_SCHEMA)
    registry = Registry().with_resource(
        candidate_schema["$id"], Resource.from_contents(candidate_schema)
    )
    return Draft202012Validator(schema, format_checker=FormatChecker(), registry=registry)


def _validate_schema(payload: Any, schema_path: Path, label: str) -> None:
    errors = sorted(_schema_validator(schema_path).iter_errors(payload), key=lambda error: list(error.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) or "root"
    raise ContractError(f"{label} violates JSON Schema at {location}: {first.message}")


def _enabled_sources(source_config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    config = source_config or load_and_validate_source_config()
    return {
        source["id"]: source
        for source in config["sources"]
        if source["enabled"] and source["access"] == "public"
    }


def _validate_event_semantics(
    item: dict[str, Any],
    index: int,
    configured_sources: dict[str, dict[str, Any]],
    *,
    weekly: bool,
) -> None:
    label = f"{'weekly' if weekly else 'candidate'}.items[{index}]"
    if item["id"] != item["eventId"]:
        raise ContractError(f"{label}.id must equal eventId")
    expected_subject = make_subject_id(item["sourceId"], item["officialUrl"])
    if item["subjectId"] != expected_subject:
        raise ContractError(f"{label}.subjectId does not match its official URL")
    if item["revision"] != item["sourceFingerprint"]:
        raise ContractError(f"{label}.revision must equal sourceFingerprint")
    expected_event = make_event_id(item["sourceId"], item["subjectId"], item["sourceFingerprint"])
    if item["eventId"] != expected_event:
        raise ContractError(f"{label}.eventId does not bind the subject and fingerprint")
    source = configured_sources.get(item["sourceId"])
    if source is None:
        raise ContractError(f"{label}.sourceId is not enabled/public")
    official_host = urlparse(item["officialUrl"]).hostname
    configured_host = urlparse(source["sourceUrl"]).hostname
    if official_host != configured_host:
        raise ContractError(f"{label}.officialUrl must stay on configured official host {configured_host}")
    if source["kind"] == "sdk_release" and item["changeType"] != "sdk_release":
        raise ContractError(f"{label} from the SDK source must be sdk_release")
    if item["changeType"] == "sdk_release" and source["kind"] != "sdk_release":
        raise ContractError(f"{label}.sdk_release requires the SDK source")
    parse_timestamp(item["detectedAt"], f"{label}.detectedAt")
    if weekly:
        _non_empty_string(item.get("originCandidateHash"), f"{label}.originCandidateHash")
    elif "originCandidateHash" in item:
        raise ContractError(f"{label}.originCandidateHash belongs only in a weekly artifact")


def validate_candidate(candidate: Any, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    _validate_schema(candidate, CANDIDATE_SCHEMA, "candidate")
    assert isinstance(candidate, dict)
    if canonical_hash(candidate, "candidateHash") != candidate["candidateHash"]:
        raise ContractError("candidateHash does not match canonical candidate content")
    generated_at = parse_timestamp(candidate["generatedAt"], "candidate.generatedAt")
    cutoff_at = parse_timestamp(candidate["baseline"]["cutoffAt"], "candidate.baseline.cutoffAt")
    if candidate["baseline"]["mode"] == "seeded":
        if candidate["items"]:
            raise ContractError("a seeded baseline candidate must contain zero changes")
        if cutoff_at != generated_at:
            raise ContractError("initial baseline cutoffAt must equal generatedAt")
    elif cutoff_at > generated_at:
        raise ContractError("baseline cutoffAt cannot be after candidate.generatedAt")

    configured_sources = _enabled_sources(source_config)
    run_ids = [run["sourceId"] for run in candidate["sourceRuns"]]
    if len(run_ids) != len(set(run_ids)) or set(run_ids) != set(configured_sources):
        raise ContractError("candidate.sourceRuns must contain every enabled public source exactly once")
    if any(parse_timestamp(run["fetchedAt"], "candidate.sourceRuns.fetchedAt") != generated_at for run in candidate["sourceRuns"]):
        raise ContractError("candidate source run timestamps must equal generatedAt")

    event_ids: set[str] = set()
    for index, item in enumerate(candidate["items"]):
        _validate_event_semantics(item, index, configured_sources, weekly=False)
        if parse_timestamp(item["detectedAt"], f"candidate.items[{index}].detectedAt") != generated_at:
            raise ContractError(f"candidate.items[{index}].detectedAt must equal candidate.generatedAt")
        if item["eventId"] in event_ids:
            raise ContractError(f"duplicate candidate eventId: {item['eventId']}")
        event_ids.add(item["eventId"])
    local_date = generated_at.astimezone(KUALA_LUMPUR).date()
    week_start = date.fromisoformat(candidate["week"]["startDate"])
    week_end = date.fromisoformat(candidate["week"]["endDate"])
    expected_start = local_date.fromordinal(local_date.toordinal() - local_date.weekday())
    expected_end = expected_start.fromordinal(expected_start.toordinal() + 6)
    if week_start != expected_start or week_end != expected_end:
        raise ContractError("candidate.week must be the Monday-Sunday window containing generatedAt")
    return candidate


def validate_weekly_candidate(weekly: Any, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    _validate_schema(weekly, WEEKLY_SCHEMA, "weekly candidate")
    assert isinstance(weekly, dict)
    if canonical_hash(weekly, "weeklyHash") != weekly["weeklyHash"]:
        raise ContractError("weeklyHash does not match canonical weekly content")
    generated_at = parse_timestamp(weekly["generatedAt"], "weekly.generatedAt")
    cutoff_at = parse_timestamp(weekly["cutoffAt"], "weekly.cutoffAt")
    local_cutoff = cutoff_at.astimezone(KUALA_LUMPUR)
    if local_cutoff.weekday() != 4 or (local_cutoff.hour, local_cutoff.minute, local_cutoff.second) != (17, 0, 0):
        raise ContractError("weekly.cutoffAt must be Friday 17:00:00 Asia/Kuala_Lumpur")
    if generated_at < cutoff_at:
        raise ContractError("weekly.generatedAt cannot be before cutoffAt")
    start = local_cutoff.date()
    start = start.fromordinal(start.toordinal() - start.weekday())
    end = start.fromordinal(start.toordinal() + 6)
    if weekly["week"]["startDate"] != start.isoformat() or weekly["week"]["endDate"] != end.isoformat():
        raise ContractError("weekly.week must be the Monday-Sunday window containing cutoffAt")

    refs = weekly["candidateRefs"]
    refs_by_hash = {reference["candidateHash"]: reference for reference in refs}
    file_names = {reference["fileName"] for reference in refs}
    if len(refs_by_hash) != len(refs) or len(file_names) != len(refs):
        raise ContractError("weekly.candidateRefs must not repeat a candidateHash or fileName")
    for index, reference in enumerate(refs):
        candidate_time = parse_timestamp(reference["generatedAt"], f"weekly.candidateRefs[{index}].generatedAt")
        local_date = candidate_time.astimezone(KUALA_LUMPUR).date()
        friday = start.fromordinal(start.toordinal() + 4)
        if candidate_time > cutoff_at or not (start <= local_date <= friday):
            raise ContractError(f"weekly.candidateRefs[{index}] is outside the Monday-Friday cutoff window")
    configured_sources = _enabled_sources(source_config)
    event_ids: set[str] = set()
    for index, item in enumerate(weekly["items"]):
        _validate_event_semantics(item, index, configured_sources, weekly=True)
        reference = refs_by_hash.get(item["originCandidateHash"])
        if reference is None:
            raise ContractError(f"weekly.items[{index}] references an unknown candidateHash")
        if item["detectedAt"] != reference["generatedAt"]:
            raise ContractError(f"weekly.items[{index}].detectedAt does not match its origin candidate")
        if item["eventId"] in event_ids:
            raise ContractError(f"duplicate weekly eventId: {item['eventId']}")
        event_ids.add(item["eventId"])
    return weekly


def load_decisions(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != DECISIONS_SCHEMA_VERSION:
        raise ContractError(f"decisions schemaVersion must be {DECISIONS_SCHEMA_VERSION}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ContractError("decisions.items must be an array")
    decisions: list[dict[str, Any]] = []
    keys: set[tuple[str, str, str]] = set()
    for index, decision in enumerate(raw_items):
        if not isinstance(decision, dict) or set(decision) - DECISION_FIELDS:
            raise ContractError(f"decisions.items[{index}] has an invalid shape")
        for field in (
            "eventId", "revision", "sourceFingerprint", "originCandidateHash", "weeklyHash",
            "reviewer", "reviewedAt",
        ):
            _non_empty_string(decision.get(field), f"decisions.items[{index}].{field}")
        if not IDENTIFIER_RE.fullmatch(decision["eventId"]):
            raise ContractError(f"decisions.items[{index}].eventId must be an identifier")
        for field in ("revision", "sourceFingerprint", "originCandidateHash", "weeklyHash"):
            if not HASH_RE.fullmatch(decision[field]):
                raise ContractError(f"decisions.items[{index}].{field} must be a SHA-256 hash")
        if decision.get("reviewStatus") != "approved":
            raise ContractError(f"decisions.items[{index}] must be explicitly approved")
        for field in ("priority", "businessImpact", "action"):
            if field not in decision:
                raise ContractError(f"decisions.items[{index}].{field} is required for approval")
        parse_timestamp(decision["reviewedAt"], f"decisions.items[{index}].reviewedAt")
        if "notes" in decision and not isinstance(decision["notes"], str):
            raise ContractError(f"decisions.items[{index}].notes must be a string")
        key = (decision["weeklyHash"], decision["eventId"], decision["revision"])
        if key in keys:
            raise ContractError(f"duplicate decision binding: {key}")
        keys.add(key)
        decisions.append(decision)
    return decisions


def _merge_item(candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    public_keys = {
        "id", "changeType", "sourceId", "title", "officialUrl", "priority",
        "announcementDate", "effectiveDate", "rollout", "targets", "businessImpact", "action",
    }
    item = {key: value for key, value in candidate.items() if key in public_keys}
    for key in DECISION_OVERRIDE_FIELDS:
        if key in decision:
            item[key] = decision[key]
    item["reviewStatus"] = "approved"
    return item


def _decision_matches_event(decision: dict[str, Any], weekly: dict[str, Any], event: dict[str, Any]) -> bool:
    return all(
        (
            decision["weeklyHash"] == weekly["weeklyHash"],
            decision["eventId"] == event["eventId"],
            decision["revision"] == event["revision"],
            decision["sourceFingerprint"] == event["sourceFingerprint"],
            decision["originCandidateHash"] == event["originCandidateHash"],
        )
    )


def build_public_report(weekly: dict[str, Any], decisions: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    validate_weekly_candidate(weekly)
    current = [decision for decision in decisions if decision["weeklyHash"] == weekly["weeklyHash"]]
    events = {event["eventId"]: event for event in weekly["items"]}
    unknown = [decision["eventId"] for decision in current if decision["eventId"] not in events]
    if unknown:
        raise ContractError(f"current-week decisions reference unknown events: {sorted(unknown)}")
    selected: list[dict[str, Any]] = []
    for event in weekly["items"]:
        matches = [decision for decision in current if decision["eventId"] == event["eventId"]]
        if not matches:
            continue
        if len(matches) != 1 or not _decision_matches_event(matches[0], weekly, event):
            raise ContractError(f"decision binding mismatch for event {event['eventId']}")
        reviewed_at = parse_timestamp(matches[0]["reviewedAt"], "decision.reviewedAt")
        if reviewed_at < parse_timestamp(weekly["generatedAt"], "weekly.generatedAt"):
            raise ContractError(f"decision predates weekly artifact for event {event['eventId']}")
        selected.append(_merge_item(event, matches[0]))
    if weekly["items"] and not selected:
        raise ContractError("cannot publish changed weekly items without a matching approval")
    report = {
        "schemaVersion": PUBLIC_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "week": weekly["week"],
        "filters": {"sourceId": "all", "priority": "all", "query": ""},
        "items": selected,
    }
    validate_public_report(report)
    return report


def validate_public_report(report: Any, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schemaVersion") != PUBLIC_SCHEMA_VERSION:
        raise ContractError(f"public report schemaVersion must be {PUBLIC_SCHEMA_VERSION}")
    parse_timestamp(report.get("generatedAt"), "public report.generatedAt")
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
    return validate_weekly_fixture(fixture, source_config, require_anonymised_urls=False)
