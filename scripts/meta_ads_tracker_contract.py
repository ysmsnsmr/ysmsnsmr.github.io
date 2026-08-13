#!/usr/bin/env python3
"""Validation helpers for the Meta Ads tracker source and fixture contracts.

This module deliberately validates only configuration and anonymised static
fixtures. It does not fetch, retain, or interpret official source content.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SOURCE_SCHEMA_VERSION = "meta-ads-official-sources/v1"
FIXTURE_SCHEMA_VERSION = "meta-ads-weekly-index-fixture/v1"
DEFAULT_SOURCE_CONFIG = Path(__file__).resolve().parents[1] / "config/meta_ads_official_sources.json"
DEFAULT_FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures/meta_ads_tracker"

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
IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ContractError(ValueError):
    """Raised when a source configuration or fixture violates its contract."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"missing file: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON in {path}: {error}") from error


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


def _expect_date(value: Any, label: str) -> str:
    parsed_value = _expect_string(value, label)
    if not DATE_RE.fullmatch(parsed_value):
        raise ContractError(f"{label} must use YYYY-MM-DD")
    try:
        date.fromisoformat(parsed_value)
    except ValueError as error:
        raise ContractError(f"{label} is not a calendar date") from error
    return parsed_value


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
        _expect_https_url(source["fetchUrl"], f"sources[{index}].fetchUrl")
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
            _expect_string(content_type, f"sources[{index}].expectedContentTypes[{content_type_index}]")
        if source["changeDetection"] not in CHANGE_DETECTION_MODES:
            raise ContractError(f"sources[{index}].changeDetection is not supported")
        if source["failureAction"] != "keep_published_content_unchanged":
            raise ContractError(f"sources[{index}] must retain published content on source failure")
    return config


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


def _validate_item(value: Any, label: str) -> None:
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
    _expect_identifier(item["sourceId"], f"{label}.sourceId")
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


def validate_weekly_fixture(payload: Any) -> dict[str, Any]:
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

    items = fixture["items"]
    if not isinstance(items, list):
        raise ContractError("fixture.items must be an array")
    item_ids: set[str] = set()
    for index, item in enumerate(items):
        _validate_item(item, f"fixture.items[{index}]")
        item_id = item["id"]
        if item_id in item_ids:
            raise ContractError(f"duplicate fixture item id: {item_id}")
        item_ids.add(item_id)
        if urlparse(item["officialUrl"]).hostname != "official.example.test":
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


def load_and_validate_fixture(path: Path) -> dict[str, Any]:
    return validate_weekly_fixture(load_json(path))
