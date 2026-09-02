#!/usr/bin/env python3
"""Build the personal Meta Ads feed from configured public sources.

The feed intentionally records source provenance rather than trying to decide
whether a reader should act. Direct RSS/API sources must all fetch, parse, and
validate before either the state or public feed file is replaced. Optional
official pages discovered inside a direct source are rejected independently.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import xml.etree.ElementTree as StandardElementTree
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from meta_ads_tracker_collect import _request as bounded_request
from meta_ads_tracker_contract import ContractError, _expect_hostname, _expect_https_url, _expect_identifier
from meta_ads_tracker_publication import write_json
from meta_ads_personal_feed_presentation import PresentationError, request_presentation


SOURCE_SCHEMA_VERSION = "meta-ads-personal-feed-sources/v3"
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
    "meta_business_news_html": ["text/html"],
}
PRESENTATION_STATUSES = {"generated", "pending"}
PARSER_VERSION = "meta-ads-personal-feed-parser/v2"


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


def _validate_platforms(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) != len(set(value)):
        raise ContractError(f"{label} must be a unique non-empty array")
    for platform in value:
        _text(platform, f"{label} value")
    return value


def _validate_transport(source: dict[str, Any], label: str, fetch_url: str | None = None) -> dict[str, Any]:
    transport = _expect_keys(
        source["transport"],
        {"allowedFetchHosts", "allowedContentHosts", "maxResponseBytes", "maxRedirects", "maxItems"},
        f"{label}.transport",
    )
    for field in ("allowedFetchHosts", "allowedContentHosts"):
        hosts = transport[field]
        if not isinstance(hosts, list) or not hosts or len(hosts) != len(set(hosts)):
            raise ContractError(f"{label}.transport.{field} must be a unique non-empty array")
        for host in hosts:
            _expect_hostname(host, f"{label}.transport.{field} host")
    if fetch_url is not None and urlsplit(fetch_url).hostname not in transport["allowedFetchHosts"]:
        raise ContractError(f"{label}.fetchUrl host must be allowed")
    _limit(transport["maxResponseBytes"], f"{label}.transport.maxResponseBytes", 1, 16 * 1024 * 1024)
    _limit(transport["maxRedirects"], f"{label}.transport.maxRedirects", 0, 5)
    _limit(transport["maxItems"], f"{label}.transport.maxItems", 1, 100)
    return transport


def _all_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [*config["sources"], *config["discoveredSources"]]


def validate_config(payload: Any) -> dict[str, Any]:
    config = _expect_keys(payload, {"schemaVersion", "policies", "sources", "discoveredSources"}, "personal feed config")
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
        _validate_platforms(source["platforms"], f"{label}.platforms")
        _validate_transport(source, label, fetch_url)
        _validate_match(source["match"], parser, f"{label}.match")
    if not isinstance(config["discoveredSources"], list) or not config["discoveredSources"]:
        raise ContractError("personal feed discoveredSources must be a non-empty array")
    direct_ids = set(ids)
    discovery_origins: set[str] = set()
    for index, value in enumerate(config["discoveredSources"]):
        label = f"personal feed discoveredSources[{index}]"
        source = _expect_keys(
            value,
            {"id", "name", "classification", "sourceUrl", "parser", "expectedContentTypes", "platforms", "transport", "discovery"},
            label,
        )
        source_id = _expect_identifier(source["id"], f"{label}.id")
        if source_id in ids:
            raise ContractError(f"duplicate personal feed source id: {source_id}")
        ids.add(source_id)
        _text(source["name"], f"{label}.name")
        if source["classification"] != "official":
            raise ContractError(f"{label}.classification must be official")
        if source["parser"] != "meta_business_news_html":
            raise ContractError(f"{label}.parser is unsupported")
        if source["expectedContentTypes"] != CONTENT_TYPES[source["parser"]]:
            raise ContractError(f"{label}.expectedContentTypes must match parser")
        source_url = _expect_https_url(source["sourceUrl"], f"{label}.sourceUrl")
        _validate_platforms(source["platforms"], f"{label}.platforms")
        transport = _validate_transport(source, label)
        if urlsplit(source_url).hostname not in transport["allowedContentHosts"]:
            raise ContractError(f"{label}.sourceUrl host must be allowed")
        discovery = _expect_keys(
            source["discovery"],
            {"fromSourceId", "allowedPathPrefix", "maxLinksPerSourceItem"},
            f"{label}.discovery",
        )
        if discovery["fromSourceId"] not in direct_ids:
            raise ContractError(f"{label}.discovery.fromSourceId must reference a direct source")
        if discovery["fromSourceId"] in discovery_origins:
            raise ContractError(f"{label}.discovery.fromSourceId must be unique")
        discovery_origins.add(discovery["fromSourceId"])
        origin = next(item for item in config["sources"] if item["id"] == discovery["fromSourceId"])
        if origin["parser"] != "rss" or origin["classification"] != "unofficial":
            raise ContractError(f"{label}.discovery.fromSourceId must reference an unofficial RSS source")
        if discovery["allowedPathPrefix"] != "/business/news/":
            raise ContractError(f"{label}.discovery.allowedPathPrefix is unsupported")
        _limit(discovery["maxLinksPerSourceItem"], f"{label}.discovery.maxLinksPerSourceItem", 1, 25)
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


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = next((value for name, value in attrs if name.casefold() == "href"), None)
        if href:
            self.links.append(html.unescape(href).strip())


class _MetaBusinessNewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.text: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if normalized != "meta":
            return
        values = {name.casefold(): value for name, value in attrs if value is not None}
        key = (values.get("property") or values.get("name") or "").casefold()
        content = values.get("content")
        if key and content:
            self.metadata.setdefault(key, _normalise(content))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.text.append(data)


def _canonical_official_news_url(value: str, source: dict[str, Any]) -> str | None:
    canonical = _canonical_url(value)
    parsed = urlsplit(canonical)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port not in {None, 443} or parsed.hostname not in source["transport"]["allowedFetchHosts"] or parsed.query:
        return None
    prefix = source["discovery"]["allowedPathPrefix"]
    if not parsed.path.startswith(prefix):
        return None
    slug = parsed.path[len(prefix):].strip("/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", slug):
        return None
    return urlunsplit(("https", parsed.netloc.lower(), f"{prefix}{slug}", "", ""))


def _official_news_links(markup: str, source: dict[str, Any]) -> tuple[list[str], int]:
    parser = _LinkExtractor()
    parser.feed(markup)
    links: list[str] = []
    seen: set[str] = set()
    for href in parser.links:
        candidate = _canonical_official_news_url(href, source)
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        links.append(candidate)
    maximum = source["discovery"]["maxLinksPerSourceItem"]
    return links[:maximum], max(0, len(links) - maximum)


def _meta_business_news_date(text: str) -> str:
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    match = re.search(
        rf"\[?Announcements?\]?\s*(?:·\s*)?\[?(({months})\s+\d{{1,2}},\s+\d{{4}})\]?",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ContractError("Meta for Business News article is missing its announcement date")
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
    except ValueError as error:
        raise ContractError("Meta for Business News article has an invalid announcement date") from error


def _meta_business_news_item(source: dict[str, Any], url: str, body: str) -> dict[str, Any]:
    parser = _MetaBusinessNewsParser()
    parser.feed(body)
    canonical = _canonical_official_news_url(parser.metadata.get("og:url", ""), source)
    if canonical != url or parser.metadata.get("og:type", "").casefold() != "article":
        raise ContractError("Meta for Business News article metadata does not match its discovered URL")
    title = _text(parser.metadata.get("og:title"), "Meta for Business News article title")[:280]
    description = _text(parser.metadata.get("og:description"), "Meta for Business News article description")[:3500]
    published = _meta_business_news_date(_normalise(" ".join(parser.text)))
    origin_id = source["discovery"]["fromSourceId"]
    return {
        "key": url,
        "url": url,
        "title": title,
        "publishedDate": published,
        "updatedDate": None,
        "matchEvidence": [f"discovered-via:{origin_id}"],
        "sourceContext": description,
        "fingerprint": _fingerprint(url, title, published, description),
    }


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


def _match(source: dict[str, Any], title: str, categories: list[str]) -> tuple[list[str] | None, list[bool]]:
    policy = source["match"]
    if policy["kind"] == "all":
        return [], []
    if policy["kind"] == "rss_category":
        category_set = {item.casefold() for item in categories}
        matched = [item for item in policy["categories"] if item.casefold() in category_set]
        return ([f"category:{item}" for item in matched] or None), []
    terms = [next((candidate for candidate in group if _contains_term(title.casefold(), candidate)), None) for group in policy["groups"]]
    group_matches = [term is not None for term in terms]
    if not all(group_matches):
        return None, group_matches
    evidence: list[str] = []
    for term in terms:
        assert term is not None
        evidence.append(f"keyword:{term}")
    return evidence, group_matches


def _rss_items(
    source: dict[str, Any],
    body: str,
    pipeline: dict[str, Any] | None = None,
    discovery_source: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    try:
        root = SafeElementTree.fromstring(body)
    except (DefusedXmlException, StandardElementTree.ParseError) as error:
        raise ContractError(f"personal feed source {source['id']} returned invalid or unsafe RSS") from error
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "item":
            continue
        if pipeline is not None:
            pipeline["parsedItems"] += 1
        fields: dict[str, list[str]] = {}
        for child in node:
            name = child.tag.rsplit("}", 1)[-1]
            fields.setdefault(name, []).append(_normalise("".join(child.itertext())))
        title = _strip_html((fields.get("title") or [""])[0])
        url = _canonical_url((fields.get("link") or [""])[0])
        parsed = urlsplit(url)
        if not title or parsed.scheme != "https" or parsed.hostname not in source["transport"]["allowedContentHosts"] or url in seen:
            continue
        if pipeline is not None:
            pipeline["validItems"] += 1
        evidence, group_matches = _match(source, title, [item for item in fields.get("category", []) if item])
        if pipeline is not None:
            for index, matched in enumerate(group_matches):
                if matched:
                    pipeline["matchGroupMatches"][index] += 1
        if evidence is None:
            if pipeline is not None:
                pipeline["excludedItems"] += 1
            continue
        if pipeline is not None:
            pipeline["matchedItems"] += 1
        seen.add(url)
        published = _date_from_feed((fields.get("pubDate") or fields.get("published") or [None])[0])
        updated = _date_from_feed((fields.get("updated") or [None])[0])
        source_context_markup = (fields.get("encoded") or fields.get("description") or fields.get("content") or [""])[0]
        source_context = _strip_html(source_context_markup)
        discovered_links, deferred_links = _official_news_links(source_context_markup, discovery_source) if discovery_source else ([], 0)
        items.append({
            "key": url,
            "url": url,
            "title": title[:280],
            "publishedDate": published,
            "updatedDate": updated,
            "matchEvidence": evidence,
            # This value is used only during this run.  It is deliberately not persisted.
            "sourceContext": source_context,
            "discoveredLinks": discovered_links,
            "deferredDiscoveredLinks": deferred_links,
            "fingerprint": _fingerprint(url, title, published or "", updated or "", source_context),
        })
        if len(items) > source["transport"]["maxItems"]:
            raise ContractError(f"personal feed source {source['id']} exceeds its item limit")
    return items


def _github_release_items(source: dict[str, Any], body: str, pipeline: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ContractError(f"personal feed source {source['id']} returned invalid JSON") from error
    if not isinstance(payload, list):
        raise ContractError(f"personal feed source {source['id']} release payload must be an array")
    items: list[dict[str, Any]] = []
    for release in payload:
        if pipeline is not None:
            pipeline["parsedItems"] += 1
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = _strip_html(str(release.get("name") or release.get("tag_name") or ""))
        url = _canonical_url(str(release.get("html_url") or ""))
        parsed = urlsplit(url)
        if not tag or parsed.scheme != "https" or parsed.hostname not in source["transport"]["allowedContentHosts"]:
            continue
        if pipeline is not None:
            pipeline["validItems"] += 1
            pipeline["matchedItems"] += 1
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


def extract_items(
    source: dict[str, Any],
    body: str,
    pipeline: dict[str, Any] | None = None,
    discovery_source: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if source["parser"] == "rss":
        return _rss_items(source, body, pipeline, discovery_source)
    if source["parser"] == "github_releases":
        return _github_release_items(source, body, pipeline)
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
    valid_ids = {source["id"] for source in _all_sources(config)}
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


def _source_descriptor(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in ("id", "name", "classification", "sourceUrl", "platforms")}


def _source_descriptors(config: dict[str, Any], active_discovered_ids: set[str] | None = None) -> list[dict[str, Any]]:
    descriptors = [_source_descriptor(source) for source in config["sources"]]
    if active_discovered_ids:
        descriptors.extend(
            _source_descriptor(source)
            for source in config["discoveredSources"]
            if source["id"] in active_discovered_ids
        )
    return descriptors


def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (item["updatedDate"] or item["publishedDate"] or item["firstObservedAt"], item["id"])


def build_feed(state: dict[str, Any], config: dict[str, Any], generated_at: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    active_discovered_ids = {
        source["id"]
        for source in config["discoveredSources"]
        if state["sources"].get(source["id"], {"items": {}})["items"]
    }
    for source in _all_sources(config):
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
    return {
        "schemaVersion": FEED_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "sources": _source_descriptors(config, active_discovered_ids),
        "items": items[:config["policies"]["maxPublishedItems"]],
    }


def validate_feed(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    feed = _expect_keys(payload, {"schemaVersion", "generatedAt", "sources", "items"}, "personal feed")
    if feed["schemaVersion"] not in {LEGACY_FEED_SCHEMA_VERSION, FEED_SCHEMA_VERSION}:
        raise ContractError(f"personal feed schemaVersion must be {LEGACY_FEED_SCHEMA_VERSION} or {FEED_SCHEMA_VERSION}")
    _timestamp(feed["generatedAt"], "personal feed.generatedAt", nullable=True)
    if not isinstance(feed["sources"], list):
        raise ContractError("personal feed sources must be an array")
    direct_descriptors = _source_descriptors(config)
    optional_descriptors = [_source_descriptor(source) for source in config["discoveredSources"]]
    if feed["sources"][:len(direct_descriptors)] != direct_descriptors:
        raise ContractError("personal feed direct sources must exactly match configured descriptors")
    configured_optional = {value["id"]: value for value in optional_descriptors}
    seen_optional: list[str] = []
    for descriptor in feed["sources"][len(direct_descriptors):]:
        if not isinstance(descriptor, dict) or descriptor.get("id") not in configured_optional:
            raise ContractError("personal feed has an unknown discovered source descriptor")
        if descriptor != configured_optional[descriptor["id"]] or descriptor["id"] in seen_optional:
            raise ContractError("personal feed discovered source descriptor must match its configuration")
        seen_optional.append(descriptor["id"])
    expected_optional_order = [source["id"] for source in config["discoveredSources"] if source["id"] in seen_optional]
    if seen_optional != expected_optional_order:
        raise ContractError("personal feed discovered source descriptors must keep configured order")
    if not isinstance(feed["items"], list) or len(feed["items"]) > config["policies"]["maxPublishedItems"]:
        raise ContractError("personal feed items exceed configured limit")
    known_sources = {source["id"]: source for source in _all_sources(config)}
    descriptor_ids = {descriptor["id"] for descriptor in feed["sources"]}
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
        if entry["sourceId"] not in descriptor_ids:
            raise ContractError("personal feed item source must have a descriptor")
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


def _presentation_request_limit(value: int | None, policy: dict[str, Any]) -> int:
    maximum = policy["maxRequestsPerRun"]
    if value is None:
        return maximum
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ContractError(f"presentation request limit must be an integer from 1 to {maximum}")
    return value


def _presentation_stats(config: dict[str, Any], renderer_enabled: bool, request_limit: int) -> dict[str, Any]:
    return {
        "rendererEnabled": renderer_enabled,
        "requestLimit": request_limit,
        "eligible": 0,
        "attempted": 0,
        "generated": 0,
        "failed": 0,
        "deferred": 0,
        "failureReasons": {},
        "sources": {
            source["id"]: {
                "eligible": 0,
                "attempted": 0,
                "generated": 0,
                "failed": 0,
                "failureReasons": {},
            }
            for source in _all_sources(config)
        },
    }


def _source_pipeline_stats(config: dict[str, Any]) -> dict[str, Any]:
    direct_ids = {source["id"] for source in config["sources"]}
    return {
        "parserVersion": PARSER_VERSION,
        "sources": {
            source["id"]: {
                "mode": "direct" if source["id"] in direct_ids else "discovered_official",
                "fetched": False,
                "responseBytes": 0,
                "parsedItems": 0,
                "validItems": 0,
                "matchedItems": 0,
                "excludedItems": 0,
                "retainedItems": 0,
                "matchGroupMatches": [0 for _group in source.get("match", {}).get("groups", [])],
                "discoveredLinks": 0,
                "attemptedLinks": 0,
                "rejectedLinks": 0,
                "deferredLinks": 0,
            }
            for source in _all_sources(config)
        },
    }


def _write_presentation_stats(target: dict[str, Any] | None, value: dict[str, Any]) -> None:
    if target is not None:
        target.clear()
        target.update(value)


def _write_source_pipeline_stats(target: dict[str, Any] | None, value: dict[str, Any]) -> None:
    if target is not None:
        target.clear()
        target.update(value)


def _presentation_failure_code(error: Exception) -> str:
    if isinstance(error, PresentationError):
        return error.code
    if isinstance(error, KeyError):
        return "response_invalid_shape"
    if isinstance(error, OSError):
        return "network_error"
    if isinstance(error, ValueError):
        return "response_invalid_shape"
    return "unknown"


def _record_presentation_failure(stats: dict[str, Any], source_id: str, code: str) -> None:
    stats["failureReasons"][code] = stats["failureReasons"].get(code, 0) + 1
    source_reasons = stats["sources"][source_id]["failureReasons"]
    source_reasons[code] = source_reasons.get(code, 0) + 1


def _print_presentation_stats(stats: dict[str, Any]) -> None:
    enabled = "true" if stats["rendererEnabled"] else "false"
    print(
        "PRESENTATION: "
        f"renderer_enabled={enabled} eligible={stats['eligible']} limit={stats['requestLimit']} "
        f"attempted={stats['attempted']} generated={stats['generated']} failed={stats['failed']} "
        f"deferred={stats['deferred']}"
    )
    for source_id, counts in stats["sources"].items():
        print(
            "PRESENTATION_SOURCE: "
            f"id={source_id} eligible={counts['eligible']} attempted={counts['attempted']} "
            f"generated={counts['generated']} failed={counts['failed']}"
        )
        for code, count in sorted(counts["failureReasons"].items()):
            print(f"PRESENTATION_SOURCE_FAILURE: id={source_id} code={code} count={count}")
    for code, count in sorted(stats["failureReasons"].items()):
        print(f"PRESENTATION_FAILURE: code={code} count={count}")


def _print_source_pipeline_stats(stats: dict[str, Any]) -> None:
    for source_id, counts in stats["sources"].items():
        print(
            "SOURCE_PIPELINE: "
            f"id={source_id} mode={counts['mode']} parser_version={stats['parserVersion']} "
            f"fetched={'true' if counts['fetched'] else 'false'} "
            f"response_bytes={counts['responseBytes']} parsed={counts['parsedItems']} valid={counts['validItems']} "
            f"matched={counts['matchedItems']} excluded={counts['excludedItems']} retained={counts['retainedItems']} "
            f"discovered_links={counts['discoveredLinks']} attempted_links={counts['attemptedLinks']} "
            f"rejected_links={counts['rejectedLinks']} deferred_links={counts['deferredLinks']}"
        )
        for index, count in enumerate(counts["matchGroupMatches"], start=1):
            print(f"SOURCE_MATCH_GROUP: id={source_id} group={index} matched={count}")


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
    present_item: Callable[[str, str, dict[str, Any]], dict[str, str]] | None = None,
    *,
    presentation_limit: int | None = None,
    presentation_stats: dict[str, Any] | None = None,
    source_pipeline_stats: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_config(config)
    validate_state(state, config)
    generated_at = _now(now)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=config["policies"]["historyRetentionDays"])
    presentation_policy = config["policies"]["japanesePresentation"]
    request_limit = _presentation_request_limit(presentation_limit, presentation_policy)
    stats = _presentation_stats(config, present_item is not None, request_limit)
    pipeline = _source_pipeline_stats(config)

    # Finish all external source collection before any optional model request. A source failure
    # therefore cannot cause paid generation work for a run that will not be published.
    raw_by_source: dict[str, list[dict[str, Any]]] = {}
    discovery_by_origin = {
        source["discovery"]["fromSourceId"]: source
        for source in config["discoveredSources"]
    }
    for source in config["sources"]:
        body, content_type = fetch_body(source, timeout)
        if not isinstance(body, str) or (content_type or "").split(";", 1)[0].strip().lower() not in source["expectedContentTypes"]:
            raise ContractError(f"personal feed source {source['id']} returned an unexpected response")
        source_pipeline = pipeline["sources"][source["id"]]
        source_pipeline["fetched"] = True
        source_pipeline["responseBytes"] = len(body.encode("utf-8"))
        raw_by_source[source["id"]] = extract_items(
            source,
            body,
            source_pipeline,
            discovery_by_origin.get(source["id"]),
        )

    for source in config["discoveredSources"]:
        source_pipeline = pipeline["sources"][source["id"]]
        origin_items = raw_by_source[source["discovery"]["fromSourceId"]]
        candidates: list[str] = []
        seen: set[str] = set()
        per_item_deferred = 0
        for item in origin_items:
            per_item_deferred += item.get("deferredDiscoveredLinks", 0)
            for url in item.get("discoveredLinks", []):
                if url not in seen:
                    seen.add(url)
                    candidates.append(url)
        source_pipeline["discoveredLinks"] = len(candidates) + per_item_deferred
        maximum = source["transport"]["maxItems"]
        source_pipeline["deferredLinks"] = per_item_deferred + max(0, len(candidates) - maximum)
        promoted: list[dict[str, Any]] = []
        for url in candidates[:maximum]:
            source_pipeline["attemptedLinks"] += 1
            request_source = {**source, "fetchUrl": url}
            try:
                body, content_type = fetch_body(request_source, timeout)
                source_pipeline["fetched"] = True
                source_pipeline["responseBytes"] += len(body.encode("utf-8")) if isinstance(body, str) else 0
                normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
                if not isinstance(body, str) or normalized_content_type not in source["expectedContentTypes"]:
                    raise ContractError("Meta for Business News article returned an unexpected response")
                source_pipeline["parsedItems"] += 1
                promoted.append(_meta_business_news_item(source, url, body))
                source_pipeline["validItems"] += 1
                source_pipeline["matchedItems"] += 1
            except (ContractError, OSError, ValueError, urllib.error.URLError):
                # Discovery is optional. Reject only this candidate without logging its URL,
                # response, or exception text, and keep the direct-source collection usable.
                source_pipeline["rejectedLinks"] += 1
        raw_by_source[source["id"]] = promoted

    next_state: dict[str, Any] = {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": generated_at, "sources": {}}
    presentation_candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for source in _all_sources(config):
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
                presentation_candidates.append((source["id"], record, raw))
                stats["eligible"] += 1
                stats["sources"][source["id"]]["eligible"] += 1
        retained: dict[str, Any] = {}
        for key, record in current.items():
            observed = datetime.fromisoformat(record["lastObservedAt"].replace("Z", "+00:00"))
            if observed >= cutoff:
                retained[key] = record
        next_state["sources"][source["id"]] = {"items": retained}
        pipeline["sources"][source["id"]]["retainedItems"] = len(retained)

    presentation_candidates.sort(
        key=lambda pair: (
            pair[1]["updatedDate"] or pair[1]["publishedDate"] or pair[1]["firstObservedAt"],
            pair[1]["url"],
        ),
        reverse=True,
    )
    if present_item is not None:
        for source_id, record, raw in presentation_candidates[:request_limit]:
            stats["attempted"] += 1
            stats["sources"][source_id]["attempted"] += 1
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
                stats["generated"] += 1
                stats["sources"][source_id]["generated"] += 1
            except (KeyError, PresentationError, ValueError, OSError) as error:
                # Optional rendering must not block source collection or expose source bodies.
                record["presentation"] = _pending_presentation(record["fingerprint"])
                stats["failed"] += 1
                stats["sources"][source_id]["failed"] += 1
                _record_presentation_failure(stats, source_id, _presentation_failure_code(error))
    stats["deferred"] = max(0, stats["eligible"] - stats["attempted"])

    feed = build_feed(next_state, config, generated_at)
    validate_state(next_state, config)
    validate_feed(feed, config)
    _write_presentation_stats(presentation_stats, stats)
    _write_source_pipeline_stats(source_pipeline_stats, pipeline)
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
    presentation_limit: int | None = None,
    presentation_stats: dict[str, Any] | None = None,
    source_pipeline_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
    renderer = present_item if present_item is not None else _presentation_from_environment(timeout)
    feed, next_state = collect(
        config,
        state,
        timeout,
        now or datetime.now(timezone.utc),
        fetch_body,
        renderer,
        presentation_limit=presentation_limit,
        presentation_stats=presentation_stats,
        source_pipeline_stats=source_pipeline_stats,
    )
    # Both payloads are fully constructed and validated before either single-file atomic write.
    write_json(output_path, feed)
    write_json(state_path, next_state)
    return feed


def _parse_presentation_limit(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("presentation limit must be a positive integer")
    return int(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--presentation-limit", type=_parse_presentation_limit, default=None)
    args = parser.parse_args()
    try:
        stats: dict[str, Any] = {}
        pipeline: dict[str, Any] = {}
        feed = collect_and_write(
            args.config,
            args.state,
            args.output,
            args.timeout,
            presentation_limit=args.presentation_limit,
            presentation_stats=stats,
            source_pipeline_stats=pipeline,
        )
    except (ContractError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: published {len(feed['items'])} personal feed item(s) from {len(feed['sources'])} source(s)")
    _print_presentation_stats(stats)
    _print_source_pipeline_stats(pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
