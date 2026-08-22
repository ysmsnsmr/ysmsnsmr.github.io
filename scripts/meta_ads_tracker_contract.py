#!/usr/bin/env python3
"""Validation helpers for the Meta Ads tracker source and fixture contracts.

This module deliberately validates only configuration and anonymised static
fixtures. It does not fetch, retain, or interpret official source content.
"""

from __future__ import annotations

import json
import ipaddress
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SOURCE_SCHEMA_VERSION = "meta-ads-official-sources/v2"
SOURCE_GOVERNANCE_SCHEMA_VERSION = "meta-ads-source-governance/v1"
FIXTURE_SCHEMA_VERSION = "meta-ads-weekly-index-fixture/v1"
DEFAULT_SOURCE_CONFIG = Path(__file__).resolve().parents[1] / "config/meta_ads_official_sources.json"
DEFAULT_SOURCE_GOVERNANCE = Path(__file__).resolve().parents[1] / "config/meta_ads_source_governance.json"
DEFAULT_FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures/meta_ads_tracker"
DEFAULT_FIXTURE_SCHEMA = Path(__file__).resolve().parent / "fixtures/meta_ads_tracker_fixture.schema.json"

SOURCE_KINDS = {"product_news", "help_center", "sdk_release"}
CHANGE_DETECTION_MODES = {
    "feed_entry_and_content_fingerprint",
    "url_content_fingerprint",
    "release_tag",
}
CHANGE_TYPES = {"new_url", "content_changed", "sdk_release"}
PRIORITIES = {"high", "standard", "low"}
FACT_STATUSES = {"stated", "not_stated"}
IMPACT_STATUSES = {"human_assessed", "not_stated"}
ACTION_STATUSES = {"action_required", "review_required", "not_required", "not_stated"}
FIXTURE_STATES = {
    "empty_week",
    "normal_week",
    "high_priority",
    "long_and_unknown_dates",
    "filtered_no_results",
}
CANONICAL_FIXTURES = {
    "empty-week": "empty_week",
    "normal-week": "normal_week",
    "high-priority": "high_priority",
    "long-and-unknown-dates": "long_and_unknown_dates",
    "filtered-no-results": "filtered_no_results",
}
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
GOVERNANCE_STATUSES = {"approved", "legacy_pending_review", "manual_only", "prohibited"}
LEGACY_GRACE_SOURCE_IDS = {"meta-product-news-rss", "meta-business-sdk-releases"}


class ContractError(ValueError):
    """Raised when a source configuration or fixture violates its contract."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"missing file: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON in {path}: {error}") from error


def validate_fixture_json_schema(payload: Any, schema_path: Path = DEFAULT_FIXTURE_SCHEMA) -> None:
    """Validate fixture structure with the versioned Draft 2020-12 JSON Schema."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as error:
        raise ContractError(
            "JSON Schema validation requires jsonschema; install requirements-meta-ads-tracker.txt"
        ) from error

    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "root"
        raise ContractError(f"fixture violates JSON Schema at {location}: {first.message}")


def _expect_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    payload = _expect_object(value, label)
    actual = set(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        raise ContractError(f"{label} keys invalid: {'; '.join(details)}")
    return payload


def _expect_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _expect_identifier(value: Any, label: str) -> str:
    identifier = _expect_string(value, label)
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ContractError(f"{label} must be a lowercase hyphenated identifier")
    return identifier


def _expect_https_url(value: Any, label: str) -> str:
    url = _expect_string(value, label)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ContractError(f"{label} must be an absolute HTTPS URL")
    return url


def _expect_hostname(value: Any, label: str) -> str:
    hostname = _expect_string(value, label).lower()
    if hostname != value or not HOSTNAME_RE.fullmatch(hostname):
        raise ContractError(f"{label} must be a lowercase DNS hostname")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    raise ContractError(f"{label} must not be an IP address")


def _expect_date(value: Any, label: str) -> str:
    parsed_value = _expect_string(value, label)
    if not DATE_RE.fullmatch(parsed_value):
        raise ContractError(f"{label} must use YYYY-MM-DD")
    try:
        date.fromisoformat(parsed_value)
    except ValueError as error:
        raise ContractError(f"{label} is not a calendar date") from error
    return parsed_value


def _expect_iso_timestamp(value: Any, label: str) -> str:
    timestamp = _expect_string(value, label)
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    return timestamp


def validate_source_config(payload: Any) -> dict[str, Any]:
    config = _expect_keys(payload, {"schemaVersion", "policies", "sources"}, "source config")
    if config["schemaVersion"] != SOURCE_SCHEMA_VERSION:
        raise ContractError(f"source config schemaVersion must be {SOURCE_SCHEMA_VERSION}")

    policies = _expect_keys(
        config["policies"],
        {
            "officialSourcesOnly",
            "bypassLoginOrConsent",
            "persistRawResponseBody",
            "failurePublicationAction",
        },
        "source config policies",
    )
    if policies["officialSourcesOnly"] is not True:
        raise ContractError("source config policies.officialSourcesOnly must be true")
    if policies["bypassLoginOrConsent"] is not False:
        raise ContractError("source config policies.bypassLoginOrConsent must be false")
    if policies["persistRawResponseBody"] is not False:
        raise ContractError("source config policies.persistRawResponseBody must be false")
    if policies["failurePublicationAction"] != "keep_published_content_unchanged":
        raise ContractError("source config must retain published content on source failure")

    sources = config["sources"]
    if not isinstance(sources, list) or not sources:
        raise ContractError("source config sources must be a non-empty array")

    ids: set[str] = set()
    for index, source_value in enumerate(sources):
        source = _expect_keys(
            source_value,
            {
                "id",
                "name",
                "kind",
                "sourceUrl",
                "fetchUrl",
                "enabled",
                "access",
                "expectedContentTypes",
                "transport",
                "changeDetection",
                "failureAction",
            },
            f"sources[{index}]",
        )
        source_id = _expect_identifier(source["id"], f"sources[{index}].id")
        if source_id in ids:
            raise ContractError(f"duplicate source id: {source_id}")
        ids.add(source_id)
        _expect_string(source["name"], f"sources[{index}].name")
        if source["kind"] not in SOURCE_KINDS:
            raise ContractError(f"sources[{index}].kind is not supported")
        _expect_https_url(source["sourceUrl"], f"sources[{index}].sourceUrl")
        fetch_url = _expect_https_url(source["fetchUrl"], f"sources[{index}].fetchUrl")
        parsed_fetch_url = urlparse(fetch_url)
        if parsed_fetch_url.username or parsed_fetch_url.password:
            raise ContractError(f"sources[{index}].fetchUrl must not contain credentials")
        try:
            port = parsed_fetch_url.port
        except ValueError as error:
            raise ContractError(f"sources[{index}].fetchUrl has an invalid port") from error
        if port not in {None, 443}:
            raise ContractError(f"sources[{index}].fetchUrl must use the standard HTTPS port")
        if not isinstance(source["enabled"], bool):
            raise ContractError(f"sources[{index}].enabled must be boolean")
        if source["access"] not in {"public", "login_required"}:
            raise ContractError(f"sources[{index}].access is not supported")
        if source["enabled"] and source["access"] != "public":
            raise ContractError(f"sources[{index}] cannot enable a login-required source")
        if source["access"] == "login_required" and source["enabled"]:
            raise ContractError(f"sources[{index}] must disable login-required access")
        content_types = source["expectedContentTypes"]
        if not isinstance(content_types, list) or not content_types:
            raise ContractError(f"sources[{index}].expectedContentTypes must be a non-empty array")
        for content_type_index, content_type in enumerate(content_types):
            text = _expect_string(content_type, f"sources[{index}].expectedContentTypes[{content_type_index}]")
            if text != text.lower() or ";" in text or "/" not in text:
                raise ContractError(f"sources[{index}].expectedContentTypes[{content_type_index}] must be a lowercase media type")
        if len(set(content_types)) != len(content_types):
            raise ContractError(f"sources[{index}].expectedContentTypes must not contain duplicates")
        transport = _expect_keys(
            source["transport"],
            {"allowedFetchHosts", "maxResponseBytes", "maxRedirects", "maxItems"},
            f"sources[{index}].transport",
        )
        allowed_hosts = transport["allowedFetchHosts"]
        if not isinstance(allowed_hosts, list) or not allowed_hosts:
            raise ContractError(f"sources[{index}].transport.allowedFetchHosts must be a non-empty array")
        validated_hosts = [
            _expect_hostname(host, f"sources[{index}].transport.allowedFetchHosts[{host_index}]")
            for host_index, host in enumerate(allowed_hosts)
        ]
        if len(set(validated_hosts)) != len(validated_hosts):
            raise ContractError(f"sources[{index}].transport.allowedFetchHosts must not contain duplicates")
        if parsed_fetch_url.hostname not in validated_hosts:
            raise ContractError(f"sources[{index}].fetchUrl host must be in transport.allowedFetchHosts")
        for key, minimum, maximum in (
            ("maxResponseBytes", 1, 16 * 1024 * 1024),
            ("maxRedirects", 0, 5),
            ("maxItems", 1, 250),
        ):
            value = transport[key]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ContractError(
                    f"sources[{index}].transport.{key} must be an integer between {minimum} and {maximum}"
                )
        if source["changeDetection"] not in CHANGE_DETECTION_MODES:
            raise ContractError(f"sources[{index}].changeDetection is not supported")
        if source["failureAction"] != "keep_published_content_unchanged":
            raise ContractError(f"sources[{index}] must retain published content on source failure")
    return config


def validate_source_governance(payload: Any, source_config: dict[str, Any]) -> dict[str, Any]:
    governance = _expect_keys(payload, {"schemaVersion", "policies", "sources"}, "source governance")
    if governance["schemaVersion"] != SOURCE_GOVERNANCE_SCHEMA_VERSION:
        raise ContractError(f"source governance schemaVersion must be {SOURCE_GOVERNANCE_SCHEMA_VERSION}")
    policies = _expect_keys(
        governance["policies"],
        {
            "establishedAt",
            "legacyReviewDeadlineDays",
            "deadlineTimezone",
            "newAutomatedSourceRequirement",
            "deadlineAction",
            "prohibitedAction",
        },
        "source governance policies",
    )
    established_at = date.fromisoformat(_expect_date(policies["establishedAt"], "source governance policies.establishedAt"))
    if policies["legacyReviewDeadlineDays"] != 14:
        raise ContractError("source governance policies.legacyReviewDeadlineDays must be 14")
    if policies["deadlineTimezone"] != "Asia/Kuala_Lumpur":
        raise ContractError("source governance policies.deadlineTimezone must be Asia/Kuala_Lumpur")
    if policies["newAutomatedSourceRequirement"] != "approved":
        raise ContractError("new automated sources must require approved governance")
    if policies["deadlineAction"] != "stop_automatic_collection" or policies["prohibitedAction"] != "stop_automatic_collection":
        raise ContractError("source governance must stop prohibited or expired automatic collection")

    source_by_id = {source["id"]: source for source in source_config["sources"]}
    records = governance["sources"]
    if not isinstance(records, list):
        raise ContractError("source governance sources must be an array")
    record_ids: set[str] = set()
    for index, value in enumerate(records):
        record = _expect_object(value, f"source governance sources[{index}]")
        source_id = _expect_identifier(record.get("sourceId"), f"source governance sources[{index}].sourceId")
        if source_id in record_ids:
            raise ContractError(f"duplicate source governance record: {source_id}")
        record_ids.add(source_id)
        source = source_by_id.get(source_id)
        if source is None:
            raise ContractError(f"source governance references unknown source: {source_id}")
        status = record.get("status")
        if status not in GOVERNANCE_STATUSES:
            raise ContractError(f"source governance sources[{index}].status is not supported")
        _expect_string(record.get("rationale"), f"source governance sources[{index}].rationale")
        if status == "legacy_pending_review":
            _expect_keys(record, {"sourceId", "status", "reviewDeadline", "rationale"}, f"source governance sources[{index}]")
            deadline = date.fromisoformat(_expect_date(record["reviewDeadline"], f"source governance sources[{index}].reviewDeadline"))
            if source_id not in LEGACY_GRACE_SOURCE_IDS:
                raise ContractError(f"only existing approved source IDs may use legacy grace: {source_id}")
            if deadline != date.fromordinal(established_at.toordinal() + 14):
                raise ContractError(f"source governance sources[{index}].reviewDeadline must be exactly 14 days after establishedAt")
            if not source["enabled"] or source["access"] != "public":
                raise ContractError(f"legacy pending source {source_id} must be an enabled public source")
        elif status == "approved":
            _expect_keys(record, {"sourceId", "status", "approvedAt", "approvedBy", "evidenceUrl", "rationale"}, f"source governance sources[{index}]")
            _expect_iso_timestamp(record["approvedAt"], f"source governance sources[{index}].approvedAt")
            _expect_string(record["approvedBy"], f"source governance sources[{index}].approvedBy")
            _expect_https_url(record["evidenceUrl"], f"source governance sources[{index}].evidenceUrl")
            if not source["enabled"] or source["access"] != "public":
                raise ContractError(f"approved automatic source {source_id} must be enabled and public")
        else:
            _expect_keys(record, {"sourceId", "status", "rationale"}, f"source governance sources[{index}]")
            if source["enabled"]:
                raise ContractError(f"{status} source {source_id} must be disabled")
    if record_ids != set(source_by_id):
        raise ContractError("source governance records must exactly match configured source IDs")
    return governance


def load_and_validate_source_governance(
    path: Path = DEFAULT_SOURCE_GOVERNANCE,
    source_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return validate_source_governance(load_json(path), source_config or load_and_validate_source_config())


def governed_automated_sources(
    source_config: dict[str, Any],
    governance: dict[str, Any],
    today: date,
) -> list[dict[str, Any]]:
    """Return the only sources that may be fetched; expired governance stops before I/O."""
    records = {record["sourceId"]: record for record in governance["sources"]}
    allowed: list[dict[str, Any]] = []
    blocked: list[str] = []
    for source in source_config["sources"]:
        if not source["enabled"] or source["access"] != "public":
            continue
        record = records[source["id"]]
        if record["status"] == "approved":
            allowed.append(source)
        elif record["status"] == "legacy_pending_review" and today < date.fromisoformat(record["reviewDeadline"]):
            allowed.append(source)
        else:
            blocked.append(source["id"])
    if blocked:
        raise ContractError(f"automatic collection blocked by source governance: {', '.join(sorted(blocked))}")
    return allowed


def _validate_date_fact(value: Any, label: str) -> None:
    fact = _expect_keys(value, {"status", "value"}, label)
    if fact["status"] not in FACT_STATUSES:
        raise ContractError(f"{label}.status is not supported")
    if fact["status"] == "stated":
        _expect_date(fact["value"], f"{label}.value")
    elif fact["value"] is not None:
        raise ContractError(f"{label}.value must be null when its status is not_stated")


def _validate_text_fact(value: Any, label: str) -> None:
    fact = _expect_keys(value, {"status", "value"}, label)
    if fact["status"] not in FACT_STATUSES:
        raise ContractError(f"{label}.status is not supported")
    if fact["status"] == "stated":
        _expect_string(fact["value"], f"{label}.value")
    elif fact["value"] is not None:
        raise ContractError(f"{label}.value must be null when its status is not_stated")


def _validate_assessment(value: Any, label: str, statuses: set[str]) -> None:
    assessment = _expect_keys(value, {"status", "summary", "assessmentSource"}, label)
    if assessment["status"] not in statuses:
        raise ContractError(f"{label}.status is not supported")
    if assessment["status"] == "not_stated":
        if assessment["summary"] is not None or assessment["assessmentSource"] is not None:
            raise ContractError(f"{label} must not contain an inferred assessment")
        return
    _expect_string(assessment["summary"], f"{label}.summary")
    if assessment["assessmentSource"] != "human_review":
        raise ContractError(f"{label}.assessmentSource must be human_review")


def _validate_item(value: Any, label: str, display_sources: dict[str, dict[str, Any]]) -> None:
    item = _expect_keys(
        value,
        {
            "id",
            "changeType",
            "sourceId",
            "title",
            "officialUrl",
            "priority",
            "announcementDate",
            "effectiveDate",
            "rollout",
            "targets",
            "businessImpact",
            "action",
            "reviewStatus",
        },
        label,
    )
    _expect_identifier(item["id"], f"{label}.id")
    if item["changeType"] not in CHANGE_TYPES:
        raise ContractError(f"{label}.changeType is not supported")
    source_id = _expect_identifier(item["sourceId"], f"{label}.sourceId")
    source = display_sources.get(source_id)
    if source is None:
        raise ContractError(f"{label}.sourceId must reference an enabled public configured source")
    if item["changeType"] == "sdk_release" and source["kind"] != "sdk_release":
        raise ContractError(f"{label}.changeType sdk_release requires an sdk_release source")
    if source["kind"] == "sdk_release" and item["changeType"] != "sdk_release":
        raise ContractError(f"{label}.sourceId for an sdk_release source requires changeType sdk_release")
    _expect_string(item["title"], f"{label}.title")
    _expect_https_url(item["officialUrl"], f"{label}.officialUrl")
    if item["priority"] not in PRIORITIES:
        raise ContractError(f"{label}.priority is not supported")
    _validate_date_fact(item["announcementDate"], f"{label}.announcementDate")
    _validate_date_fact(item["effectiveDate"], f"{label}.effectiveDate")
    _validate_text_fact(item["rollout"], f"{label}.rollout")
    _validate_text_fact(item["targets"], f"{label}.targets")
    _validate_assessment(item["businessImpact"], f"{label}.businessImpact", IMPACT_STATUSES)
    _validate_assessment(item["action"], f"{label}.action", ACTION_STATUSES)
    if item["reviewStatus"] != "approved":
        raise ContractError(f"{label}.reviewStatus must be approved for public display")


def validate_weekly_fixture(
    payload: Any,
    source_config: dict[str, Any] | None = None,
    *,
    require_anonymised_urls: bool = True,
) -> dict[str, Any]:
    validate_fixture_json_schema(payload)
    fixture = _expect_keys(payload, {"schemaVersion", "fixture", "week", "filters", "items"}, "fixture")
    if fixture["schemaVersion"] != FIXTURE_SCHEMA_VERSION:
        raise ContractError(f"fixture schemaVersion must be {FIXTURE_SCHEMA_VERSION}")

    descriptor = _expect_keys(fixture["fixture"], {"name", "state", "description"}, "fixture.fixture")
    _expect_identifier(descriptor["name"], "fixture.fixture.name")
    if descriptor["state"] not in FIXTURE_STATES:
        raise ContractError("fixture.fixture.state is not supported")
    _expect_string(descriptor["description"], "fixture.fixture.description")

    week = _expect_keys(fixture["week"], {"startDate", "endDate", "label"}, "fixture.week")
    start_date = _expect_date(week["startDate"], "fixture.week.startDate")
    end_date = _expect_date(week["endDate"], "fixture.week.endDate")
    if start_date > end_date:
        raise ContractError("fixture.week.startDate must not be after endDate")
    _expect_string(week["label"], "fixture.week.label")

    filters = _expect_keys(fixture["filters"], {"sourceId", "priority", "query"}, "fixture.filters")
    if filters["sourceId"] != "all":
        _expect_identifier(filters["sourceId"], "fixture.filters.sourceId")
    if filters["priority"] not in {"all", *PRIORITIES}:
        raise ContractError("fixture.filters.priority is not supported")
    _expect_string(filters["query"], "fixture.filters.query", allow_empty=True)

    config = source_config if source_config is not None else load_and_validate_source_config()
    display_sources = {
        source["id"]: source
        for source in config["sources"]
        if source["enabled"] and source["access"] == "public"
    }
    items = fixture["items"]
    if not isinstance(items, list):
        raise ContractError("fixture.items must be an array")
    item_ids: set[str] = set()
    for index, item in enumerate(items):
        _validate_item(item, f"fixture.items[{index}]", display_sources)
        item_id = item["id"]
        if item_id in item_ids:
            raise ContractError(f"duplicate fixture item id: {item_id}")
        item_ids.add(item_id)
        if require_anonymised_urls and urlparse(item["officialUrl"]).hostname != "official.example.test":
            raise ContractError("fixtures must use anonymised official.example.test URLs")

    state = descriptor["state"]
    if state in {"empty_week", "filtered_no_results"} and items:
        raise ContractError(f"{state} fixtures must not contain items")
    if state not in {"empty_week", "filtered_no_results"} and not items:
        raise ContractError(f"{state} fixtures must contain at least one item")
    if state == "empty_week" and (filters["sourceId"] != "all" or filters["priority"] != "all" or filters["query"]):
        raise ContractError("empty_week must use unfiltered controls")
    if state == "filtered_no_results" and filters["sourceId"] == "all" and filters["priority"] == "all" and not filters["query"]:
        raise ContractError("filtered_no_results must have an active filter")
    if state == "high_priority" and not any(item["priority"] == "high" for item in items):
        raise ContractError("high_priority must contain a high-priority item")
    if state == "long_and_unknown_dates" and not any(
        item["effectiveDate"]["status"] == "not_stated" or item["announcementDate"]["status"] == "not_stated"
        for item in items
    ):
        raise ContractError("long_and_unknown_dates must contain an unknown date")
    return fixture


def load_and_validate_source_config(path: Path = DEFAULT_SOURCE_CONFIG) -> dict[str, Any]:
    return validate_source_config(load_json(path))


def load_and_validate_fixture(
    path: Path, source_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    fixture = validate_weekly_fixture(load_json(path), source_config)
    if path.stem != fixture["fixture"]["name"]:
        raise ContractError(f"fixture filename must match fixture.fixture.name: {path}")
    return fixture


def load_and_validate_canonical_fixtures(
    directory: Path = DEFAULT_FIXTURE_DIRECTORY,
    source_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("*.json"))
    actual_names = {path.stem for path in paths}
    expected_names = set(CANONICAL_FIXTURES)
    if actual_names != expected_names:
        raise ContractError(
            "fixture files must exactly match the canonical set: "
            f"expected {sorted(expected_names)}, got {sorted(actual_names)}"
        )
    fixtures = [load_and_validate_fixture(path, source_config) for path in paths]
    actual_states = {fixture["fixture"]["name"]: fixture["fixture"]["state"] for fixture in fixtures}
    if actual_states != CANONICAL_FIXTURES:
        raise ContractError(
            "fixture name/state mapping must exactly match the canonical set: "
            f"expected {CANONICAL_FIXTURES}, got {actual_states}"
        )
    return fixtures
