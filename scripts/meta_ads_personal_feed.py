#!/usr/bin/env python3
"""Build the personal Meta Ads feed from configured public RSS and API sources.

The feed intentionally records source provenance rather than trying to decide
whether a reader should act.  All configured sources must fetch, parse, and
validate before either the state or public feed file is replaced.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import json
import os
import re
import sys
import urllib.error
import xml.etree.ElementTree as StandardElementTree
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from meta_ads_tracker_collect import _request as bounded_request
from meta_ads_tracker_contract import ContractError, _expect_hostname, _expect_https_url, _expect_identifier
from meta_ads_tracker_publication import write_json
from meta_ads_personal_feed_presentation import PresentationError, request_presentation


SOURCE_SCHEMA_VERSION = "meta-ads-personal-feed-sources/v2"
STATE_SCHEMA_VERSION = "meta-ads-personal-feed-state/v2"
LEGACY_STATE_SCHEMA_VERSION = "meta-ads-personal-feed-state/v1"
FEED_SCHEMA_VERSION = "meta-ads-personal-feed/v2"
LEGACY_FEED_SCHEMA_VERSION = "meta-ads-personal-feed/v1"
PRESENTATION_SCHEMA_VERSION = "meta-ads-personal-feed-presentation/v1"
DEFAULT_CONFIG = Path("config/meta_ads_personal_feed_sources.json")
DEFAULT_STATE = Path("data/meta_ads_personal_feed_state.json")
DEFAULT_OUTPUT = Path("meta-ads-updates/personal-feed.json")
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
PARSER_TYPES = {"rss", "github_releases"}
CONTENT_TYPES = {
    "rss": ["application/rss+xml", "application/xml", "text/xml"],
    "github_releases": ["application/json"],
}
PRESENTATION_STATUSES = {"generated", "pending"}


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(f"{label} keys must be exactly {', '.join(sorted(expected))}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value.strip()


def _limit(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContractError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _timestamp(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include a timezone")
    return text


def _date(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            from datetime import date
            parsed_date = date.fromisoformat(text)
        except ValueError as error:
            raise ContractError(f"{label} must be YYYY-MM-DD") from error
        return parsed_date.isoformat()
    return parsed.date().isoformat()


def _validate_match(value: Any, parser: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise ContractError(f"{label} must include a supported kind")
    kind = value["kind"]
    if kind == "all":
        return _expect_keys(value, {"kind"}, label)
    if kind == "all_groups":
        payload = _expect_keys(value, {"kind", "groups"}, label)
        groups = payload["groups"]
        if not isinstance(groups, list) or len(groups) < 2:
            raise ContractError(f"{label}.groups must contain at least two groups")
        for index, group in enumerate(groups):
            if not isinstance(group, list) or not group or len(group) != len(set(group)):
                raise ContractError(f"{label}.groups[{index}] must be a unique non-empty array")
            for term in group:
                _text(term, f"{label}.groups[{index}] term")
        return payload
    if kind == "rss_category":
        if parser != "rss":
            raise ContractError(f"{label}.kind rss_category requires an rss parser")
        payload = _expect_keys(value, {"kind", "categories"}, label)
        categories = payload["categories"]
        if not isinstance(categories, list) or not categories or len(categories) != len(set(categories)):
            raise ContractError(f"{label}.categories must be a unique non-empty array")
        for category in categories:
            _text(category, f"{label}.categories value")
        return payload
    raise ContractError(f"{label}.kind is unsupported")


def validate_config(payload: Any) -> dict[str, Any]:
    config = _expect_keys(payload, {"schemaVersion", "policies", "sources"}, "personal feed config")
    if config["schemaVersion"] != SOURCE_SCHEMA_VERSION:
        raise ContractError(f"personal feed config schemaVersion must be {SOURCE_SCHEMA_VERSION}")
    policies = _expect_keys(config["policies"], {"persistRawResponseBody", "historyRetentionDays", "maxPublishedItems", "japanesePresentation"}, "personal feed policies")
    if policies["persistRawResponseBody"] is not False:
        raise ContractError("personal feed must not persist raw response bodies")
    _limit(policies["historyRetentionDays"], "personal feed policies.historyRetentionDays", 1, 730)
    _limit(policies["maxPublishedItems"], "personal feed policies.maxPublishedItems", 1, 500)
    presentation = _expect_keys(
        policies["japanesePresentation"],
        {"maxRequestsPerRun", "maxInputChars", "shortHeadlineMaxChars", "summaryMaxChars"},
        "personal feed policies.japanesePresentation",
    )
    _limit(presentation["maxRequestsPerRun"], "personal feed policies.japanesePresentation.maxRequestsPerRun", 1, 50)
    _limit(presentation["maxInputChars"], "personal feed policies.japanesePresentation.maxInputChars", 100, 12_000)
    _limit(presentation["shortHeadlineMaxChars"], "personal feed policies.japanesePresentation.shortHeadlineMaxChars", 10, 120)
    _limit(presentation["summaryMaxChars"], "personal feed policies.japanesePresentation.summaryMaxChars", 40, 600)
    if not isinstance(config["sources"], list) or not config["sources"]:
        raise ContractError("personal feed sources must be a non-empty array")
    ids: set[str] = set()
    for index, value in enumerate(config["sources"]):
        label = f"personal feed sources[{index}]"
        source = _expect_keys(value, {"id", "name", "classification", "sourceUrl", "fetchUrl", "parser", "expectedContentTypes", "platforms", "transport", "match"}, label)
        source_id = _expect_identifier(source["id"], f"{label}.id")
        if source_id in ids:
            raise ContractError(f"duplicate personal feed source id: {source_id}")
        ids.add(source_id)
        _text(source["name"], f"{label}.name")
        if source["classification"] not in {"official", "unofficial"}:
            raise ContractError(f"{label}.classification must be official or unofficial")
        parser = source["parser"]
        if parser not in PARSER_TYPES:
            raise ContractError(f"{label}.parser is unsupported")
        if source["expectedContentTypes"] != CONTENT_TYPES[parser]:
            raise ContractError(f"{label}.expectedContentTypes must match parser")
        fetch_url = _expect_https_url(source["fetchUrl"], f"{label}.fetchUrl")
        _expect_https_url(source["sourceUrl"], f"{label}.sourceUrl")
        parsed = urlsplit(fetch_url)
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ContractError(f"{label}.fetchUrl must use credential-free standard HTTPS")
        platforms = source["platforms"]
        if not isinstance(platforms, list) or not platforms or len(platforms) != len(set(platforms)):
            raise ContractError(f"{label}.platforms must be a unique non-empty array")
        for platform in platforms:
            _text(platform, f"{label}.platforms value")
        transport = _expect_keys(source["transport"], {"allowedFetchHosts", "allowedContentHosts", "maxResponseBytes", "maxRedirects", "maxItems"}, f"{label}.transport")
        for field in ("allowedFetchHosts", "allowedContentHosts"):
            hosts = transport[field]
            if not isinstance(hosts, list) or not hosts or len(hosts) != len(set(hosts)):
                raise ContractError(f"{label}.transport.{field} must be a unique non-empty array")
            for host in hosts:
                _expect_hostname(host, f"{label}.transport.{field} host")
        if parsed.hostname not in transport["allowedFetchHosts"]:
            raise ContractError(f"{label}.fetchUrl host must be allowed")
        _limit(transport["maxResponseBytes"], f"{label}.transport.maxResponseBytes", 1, 16 * 1024 * 1024)
        _limit(transport["maxRedirects"], f"{label}.transport.maxRedirects", 0, 5)
        _limit(transport["maxItems"], f"{label}.transport.maxItems", 1, 100)
        _validate_match(source["match"], parser, f"{label}.match")
    return config


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as error:
        raise ContractError(f"missing personal feed config: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid personal feed config JSON: {path}") from error


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_html(value: str) -> str:
    return _normalise(re.sub(r"<[^>]+>", " ", value or ""))


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    pairs = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(pairs), ""))


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _date_from_feed(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return _date(value, "source date", nullable=True) if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value) else None


def _contains_term(text: str, term: str) -> bool:
    normalized = term.casefold()
    if re.fullmatch(r"[a-z0-9+ ]+", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None
    return normalized in text


def _match(source: dict[str, Any], title: str, categories: list[str]) -> list[str] | None:
    policy = source["match"]
    if policy["kind"] == "all":
        return []
    if policy["kind"] == "rss_category":
        category_set = {item.casefold() for item in categories}
        matched = [item for item in policy["categories"] if item.casefold() in category_set]
        return [f"category:{item}" for item in matched] or None
    evidence: list[str] = []
    for group in policy["groups"]:
        term = next((candidate for candidate in group if _contains_term(title.casefold(), candidate)), None)
        if term is None:
            return None
        evidence.append(f"keyword:{term}")
    return evidence


def _rss_items(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    try:
        root = SafeElementTree.fromstring(body)
    except (DefusedXmlException, StandardElementTree.ParseError) as error:
        raise ContractError(f"personal feed source {source['id']} returned invalid or unsafe RSS") from error
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "item":
            continue
        fields: dict[str, list[str]] = {}
        for child in node:
            name = child.tag.rsplit("}", 1)[-1]
            fields.setdefault(name, []).append(_normalise("".join(child.itertext())))
        title = _strip_html((fields.get("title") or [""])[0])
        url = _canonical_url((fields.get("link") or [""])[0])
        parsed = urlsplit(url)
        if not title or parsed.scheme != "https" or parsed.hostname not in source["transport"]["allowedContentHosts"] or url in seen:
            continue
        evidence = _match(source, title, [item for item in fields.get("category", []) if item])
        if evidence is None:
            continue
        seen.add(url)
        published = _date_from_feed((fields.get("pubDate") or fields.get("published") or [None])[0])
        updated = _date_from_feed((fields.get("updated") or [None])[0])
        source_context = _strip_html(
            (fields.get("description") or fields.get("encoded") or fields.get("content") or [""])[0]
        )
        items.append({
            "key": url,
            "url": url,
            "title": title[:280],
            "publishedDate": published,
            "updatedDate": updated,
            "matchEvidence": evidence,
            # This value is used only during this run.  It is deliberately not persisted.
            "sourceContext": source_context,
            "fingerprint": _fingerprint(url, title, published or "", updated or "", source_context),
        })
        if len(items) > source["transport"]["maxItems"]:
            raise ContractError(f"personal feed source {source['id']} exceeds its item limit")
    return items


def _github_release_items(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ContractError(f"personal feed source {source['id']} returned invalid JSON") from error
    if not isinstance(payload, list):
        raise ContractError(f"personal feed source {source['id']} release payload must be an array")
    items: list[dict[str, Any]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = _strip_html(str(release.get("name") or release.get("tag_name") or ""))
        url = _canonical_url(str(release.get("html_url") or ""))
        parsed = urlsplit(url)
        if not tag or parsed.scheme != "https" or parsed.hostname not in source["transport"]["allowedContentHosts"]:
            continue
        published = _date_from_feed(str(release.get("published_at") or release.get("created_at") or ""))
        updated = _date_from_feed(str(release.get("updated_at") or ""))
        source_context = _normalise(str(release.get("body") or ""))
        items.append({
            "key": str(release.get("tag_name") or url),
            "url": url,
            "title": tag[:280],
            "publishedDate": published,
            "updatedDate": updated,
            "matchEvidence": [],
            # Release notes are used only as model input and are never stored in state or feed JSON.
            "sourceContext": source_context,
            "fingerprint": _fingerprint(str(release.get("tag_name") or url), tag, published or "", updated or "", source_context),
        })
        if len(items) > source["transport"]["maxItems"]:
            raise ContractError(f"personal feed source {source['id']} exceeds its item limit")
    return items


def extract_items(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    if source["parser"] == "rss":
        return _rss_items(source, body)
    if source["parser"] == "github_releases":
        return _github_release_items(source, body)
    raise ContractError(f"personal feed source {source['id']} has an unsupported parser")


def _validate_presentation(value: Any, fingerprint: str | None, label: str, policy: dict[str, Any]) -> dict[str, Any]:
    presentation = _expect_keys(
        value,
        {"schemaVersion", "status", "shortHeadlineJa", "summaryJa", "sourceFingerprint", "generatedAt"},
        label,
    )
    if presentation["schemaVersion"] != PRESENTATION_SCHEMA_VERSION:
        raise ContractError(f"{label}.schemaVersion must be {PRESENTATION_SCHEMA_VERSION}")
    if presentation["status"] not in PRESENTATION_STATUSES:
        raise ContractError(f"{label}.status is unsupported")
    if not isinstance(presentation["sourceFingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", presentation["sourceFingerprint"]):
        raise ContractError(f"{label}.sourceFingerprint must be a SHA-256 hash")
    if fingerprint is not None and presentation["sourceFingerprint"] != fingerprint:
        raise ContractError(f"{label}.sourceFingerprint must match the item fingerprint")
    generated = presentation["status"] == "generated"
    for field in ("shortHeadlineJa", "summaryJa"):
        value = presentation[field]
        if generated:
            maximum = policy["shortHeadlineMaxChars"] if field == "shortHeadlineJa" else policy["summaryMaxChars"]
            if len(_text(value, f"{label}.{field}")) > maximum:
                raise ContractError(f"{label}.{field} exceeds its configured length")
        elif value is not None:
            raise ContractError(f"{label}.{field} must be null while pending")
    _timestamp(presentation["generatedAt"], f"{label}.generatedAt", nullable=not generated)
    if generated and presentation["generatedAt"] is None:
        raise ContractError(f"{label}.generatedAt is required when generated")
    if not generated and presentation["generatedAt"] is not None:
        raise ContractError(f"{label}.generatedAt must be null while pending")
    return presentation


def validate_state(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    state = _expect_keys(payload, {"schemaVersion", "updatedAt", "sources"}, "personal feed state")
    if state["schemaVersion"] not in {LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION}:
        raise ContractError(f"personal feed state schemaVersion must be {LEGACY_STATE_SCHEMA_VERSION} or {STATE_SCHEMA_VERSION}")
    _timestamp(state["updatedAt"], "personal feed state.updatedAt", nullable=True)
    if not isinstance(state["sources"], dict):
        raise ContractError("personal feed state.sources must be an object")
    valid_ids = {source["id"] for source in config["sources"]}
    if set(state["sources"]) - valid_ids:
        raise ContractError("personal feed state has an unknown source")
    for source_id, source_state in state["sources"].items():
        source_payload = _expect_keys(source_state, {"items"}, f"personal feed state.sources.{source_id}")
        if not isinstance(source_payload["items"], dict):
            raise ContractError(f"personal feed state.sources.{source_id}.items must be an object")
        for key, item in source_payload["items"].items():
            _text(key, f"personal feed state.sources.{source_id} key")
            expected = {"url", "title", "publishedDate", "updatedDate", "matchEvidence", "fingerprint", "firstObservedAt", "lastObservedAt"}
            if state["schemaVersion"] == STATE_SCHEMA_VERSION:
                expected.add("presentation")
            entry = _expect_keys(item, expected, f"personal feed state.sources.{source_id}.items.{key}")
            _expect_https_url(entry["url"], "personal feed state item.url")
            _text(entry["title"], "personal feed state item.title")
            _date(entry["publishedDate"], "personal feed state item.publishedDate", nullable=True)
            _date(entry["updatedDate"], "personal feed state item.updatedDate", nullable=True)
            if not isinstance(entry["matchEvidence"], list) or not all(isinstance(value, str) for value in entry["matchEvidence"]):
                raise ContractError("personal feed state item.matchEvidence must be a string array")
            if not isinstance(entry["fingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", entry["fingerprint"]):
                raise ContractError("personal feed state item.fingerprint must be a SHA-256 hash")
            _timestamp(entry["firstObservedAt"], "personal feed state item.firstObservedAt")
            _timestamp(entry["lastObservedAt"], "personal feed state item.lastObservedAt")
            if state["schemaVersion"] == STATE_SCHEMA_VERSION:
                _validate_presentation(
                    entry["presentation"],
                    entry["fingerprint"],
                    "personal feed state item.presentation",
                    config["policies"]["japanesePresentation"],
                )
    return state


def _now(now: datetime) -> str:
    if now.tzinfo is None:
        raise ContractError("personal feed now must include a timezone")
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_descriptors(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [{key: source[key] for key in ("id", "name", "classification", "sourceUrl", "platforms")} for source in config["sources"]]


def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (item["updatedDate"] or item["publishedDate"] or item["firstObservedAt"], item["id"])


def build_feed(state: dict[str, Any], config: dict[str, Any], generated_at: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for source in config["sources"]:
        for key, record in state["sources"].get(source["id"], {"items": {}})["items"].items():
            items.append({
                "id": f"{source['id']}-{record['fingerprint'][:20]}",
                "sourceId": source["id"],
                "title": record["title"],
                "url": record["url"],
                "publishedDate": record["publishedDate"],
                "updatedDate": record["updatedDate"],
                "firstObservedAt": record["firstObservedAt"],
                "lastObservedAt": record["lastObservedAt"],
                "platforms": source["platforms"],
                "matchEvidence": record["matchEvidence"],
                "presentation": record["presentation"],
            })
    items.sort(key=_sort_key, reverse=True)
    return {"schemaVersion": FEED_SCHEMA_VERSION, "generatedAt": generated_at, "sources": _source_descriptors(config), "items": items[:config["policies"]["maxPublishedItems"]]}


def validate_feed(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    feed = _expect_keys(payload, {"schemaVersion", "generatedAt", "sources", "items"}, "personal feed")
    if feed["schemaVersion"] not in {LEGACY_FEED_SCHEMA_VERSION, FEED_SCHEMA_VERSION}:
        raise ContractError(f"personal feed schemaVersion must be {LEGACY_FEED_SCHEMA_VERSION} or {FEED_SCHEMA_VERSION}")
    _timestamp(feed["generatedAt"], "personal feed.generatedAt", nullable=True)
    descriptors = _source_descriptors(config)
    if feed["sources"] != descriptors:
        raise ContractError("personal feed sources must exactly match configured descriptors")
    if not isinstance(feed["items"], list) or len(feed["items"]) > config["policies"]["maxPublishedItems"]:
        raise ContractError("personal feed items exceed configured limit")
    known_sources = {source["id"]: source for source in config["sources"]}
    ids: set[str] = set()
    for index, item in enumerate(feed["items"]):
        expected = {"id", "sourceId", "title", "url", "publishedDate", "updatedDate", "firstObservedAt", "lastObservedAt", "platforms", "matchEvidence"}
        if feed["schemaVersion"] == FEED_SCHEMA_VERSION:
            expected.add("presentation")
        entry = _expect_keys(item, expected, f"personal feed.items[{index}]")
        item_id = _expect_identifier(entry["id"], f"personal feed.items[{index}].id")
        if item_id in ids:
            raise ContractError("personal feed item IDs must be unique")
        ids.add(item_id)
        source = known_sources.get(entry["sourceId"])
        if source is None:
            raise ContractError("personal feed item references an unknown source")
        _text(entry["title"], "personal feed item.title")
        url = _expect_https_url(entry["url"], "personal feed item.url")
        if urlsplit(url).hostname not in source["transport"]["allowedContentHosts"]:
            raise ContractError("personal feed item URL must stay on its configured content host")
        _date(entry["publishedDate"], "personal feed item.publishedDate", nullable=True)
        _date(entry["updatedDate"], "personal feed item.updatedDate", nullable=True)
        _timestamp(entry["firstObservedAt"], "personal feed item.firstObservedAt")
        _timestamp(entry["lastObservedAt"], "personal feed item.lastObservedAt")
        if entry["platforms"] != source["platforms"]:
            raise ContractError("personal feed item platforms must match its source")
        if not isinstance(entry["matchEvidence"], list) or not all(isinstance(value, str) for value in entry["matchEvidence"]):
            raise ContractError("personal feed item.matchEvidence must be a string array")
        if feed["schemaVersion"] == FEED_SCHEMA_VERSION:
            _validate_presentation(
                entry["presentation"],
                None,
                f"personal feed.items[{index}].presentation",
                config["policies"]["japanesePresentation"],
            )
    return feed


def _pending_presentation(fingerprint: str) -> dict[str, Any]:
    return {
        "schemaVersion": PRESENTATION_SCHEMA_VERSION,
        "status": "pending",
        "shortHeadlineJa": None,
        "summaryJa": None,
        "sourceFingerprint": fingerprint,
        "generatedAt": None,
    }


def _presentation_from_environment(timeout: float) -> Callable[[str, str, dict[str, Any]], dict[str, str]] | None:
    setting = os.environ.get("META_ADS_PERSONAL_FEED_JA_ENABLED", "").strip().lower() or "true"
    if setting not in {"true", "false"}:
        raise ContractError("META_ADS_PERSONAL_FEED_JA_ENABLED must be true, false, or unset")
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if setting == "false" or not api_key:
        return None
    model = os.environ.get("META_ADS_PERSONAL_FEED_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"

    def present(title: str, source_context: str, policy: dict[str, Any]) -> dict[str, str]:
        return request_presentation(
            api_key=api_key,
            model=model,
            title=title,
            source_context=source_context[:policy["maxInputChars"]],
            short_headline_max_chars=policy["shortHeadlineMaxChars"],
            summary_max_chars=policy["summaryMaxChars"],
            timeout=timeout,
        )

    return present


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
    present_item: Callable[[str, str, dict[str, Any]], dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_config(config)
    validate_state(state, config)
    generated_at = _now(now)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=config["policies"]["historyRetentionDays"])

    # Finish all external source collection before any optional model request. A source failure
    # therefore cannot cause paid generation work for a run that will not be published.
    raw_by_source: dict[str, list[dict[str, Any]]] = {}
    for source in config["sources"]:
        body, content_type = fetch_body(source, timeout)
        if not isinstance(body, str) or (content_type or "").split(";", 1)[0].strip().lower() not in source["expectedContentTypes"]:
            raise ContractError(f"personal feed source {source['id']} returned an unexpected response")
        raw_by_source[source["id"]] = extract_items(source, body)

    next_state: dict[str, Any] = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": generated_at, "sources": {}}
    presentation_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for source in config["sources"]:
        prior = state["sources"].get(source["id"], {"items": {}})["items"]
        current: dict[str, Any] = {}
        for key, record in prior.items():
            current[key] = {
                "url": record["url"],
                "title": record["title"],
                "publishedDate": record["publishedDate"],
                "updatedDate": record["updatedDate"],
                "matchEvidence": record["matchEvidence"],
                "fingerprint": record["fingerprint"],
                "firstObservedAt": record["firstObservedAt"],
                "lastObservedAt": record["lastObservedAt"],
                "presentation": record.get("presentation") or _pending_presentation(record["fingerprint"]),
            }
        for raw in raw_by_source[source["id"]]:
            existing = prior.get(raw["key"])
            cached = existing.get("presentation") if existing and existing.get("fingerprint") == raw["fingerprint"] else None
            record = {
                "url": raw["url"],
                "title": raw["title"],
                "publishedDate": raw["publishedDate"],
                "updatedDate": raw["updatedDate"],
                "matchEvidence": raw["matchEvidence"],
                "fingerprint": raw["fingerprint"],
                "firstObservedAt": existing["firstObservedAt"] if existing else generated_at,
                "lastObservedAt": generated_at,
                "presentation": cached or _pending_presentation(raw["fingerprint"]),
            }
            current[raw["key"]] = record
            if record["presentation"]["status"] != "generated":
                presentation_candidates.append((record, raw))
        retained: dict[str, Any] = {}
        for key, record in current.items():
            observed = datetime.fromisoformat(record["lastObservedAt"].replace("Z", "+00:00"))
            if observed >= cutoff:
                retained[key] = record
        next_state["sources"][source["id"]] = {"items": retained}

    presentation_policy = config["policies"]["japanesePresentation"]
    presentation_candidates.sort(
        key=lambda pair: (
            pair[0]["updatedDate"] or pair[0]["publishedDate"] or pair[0]["firstObservedAt"],
            pair[0]["url"],
        ),
        reverse=True,
    )
    if present_item is not None:
        for record, raw in presentation_candidates[:presentation_policy["maxRequestsPerRun"]]:
            try:
                generated = present_item(record["title"], raw["sourceContext"], presentation_policy)
                record["presentation"] = {
                    "schemaVersion": PRESENTATION_SCHEMA_VERSION,
                    "status": "generated",
                    "shortHeadlineJa": generated["shortHeadlineJa"],
                    "summaryJa": generated["summaryJa"],
                    "sourceFingerprint": record["fingerprint"],
                    "generatedAt": generated_at,
                }
            except (KeyError, PresentationError, ValueError, OSError):
                # Optional rendering must not block source collection or expose source bodies.
                record["presentation"] = _pending_presentation(record["fingerprint"])

    feed = build_feed(next_state, config, generated_at)
    validate_state(next_state, config)
    validate_feed(feed, config)
    return feed, next_state


def collect_and_write(
    config_path: Path,
    state_path: Path,
    output_path: Path,
    timeout: float,
    *,
    now: datetime | None = None,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
    present_item: Callable[[str, str, dict[str, Any]], dict[str, str]] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
    renderer = present_item if present_item is not None else _presentation_from_environment(timeout)
    feed, next_state = collect(config, state, timeout, now or datetime.now(timezone.utc), fetch_body, renderer)
    # Both payloads are fully constructed and validated before either single-file atomic write.
    write_json(output_path, feed)
    write_json(state_path, next_state)
    return feed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        feed = collect_and_write(args.config, args.state, args.output, args.timeout)
    except (ContractError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: published {len(feed['items'])} personal feed item(s) from {len(feed['sources'])} source(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
