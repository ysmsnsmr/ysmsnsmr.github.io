#!/usr/bin/env python3
"""Build the personal Meta Ads feed from configured public sources.

The feed intentionally records source provenance rather than trying to decide
whether a reader should act. Direct RSS/API sources must all fetch, parse, and
validate before either the state or public feed file is replaced. Optional
official pages discovered inside a direct source are rejected independently.
"""

from __future__ import annotations

import argparse
import copy
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import xml.etree.ElementTree as StandardElementTree
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from meta_ads_tracker_collect import SourceFetchError, _request as bounded_request
from meta_ads_tracker_contract import ContractError, _expect_hostname, _expect_https_url, _expect_identifier
from meta_ads_tracker_publication import write_json
from meta_ads_personal_feed_presentation import PresentationError, request_bilingual_presentation, request_english_presentation, request_presentation


SOURCE_SCHEMA_VERSION = "meta-ads-personal-feed-sources/v5"
STATE_SCHEMA_VERSION = "meta-ads-personal-feed-state/v2"
LEGACY_STATE_SCHEMA_VERSION = "meta-ads-personal-feed-state/v1"
STATE_V3_SCHEMA_VERSION = "meta-ads-personal-feed-state/v3"
FEED_SCHEMA_VERSION = "meta-ads-personal-feed/v2"
LEGACY_FEED_SCHEMA_VERSION = "meta-ads-personal-feed/v1"
FEED_V3_SCHEMA_VERSION = "meta-ads-personal-feed/v3"
PRESENTATION_SCHEMA_VERSION = "meta-ads-personal-feed-presentation/v1"
BILINGUAL_PRESENTATION_SCHEMA_VERSION = "meta-ads-personal-feed-presentation/v2"
DEFAULT_PRESENTATION_GENERATOR_REVISION = "bilingual-v1"
LEGACY_RELEVANCE_REVISION = "legacy-v2"
DEFAULT_V3_SCHEMA = Path(__file__).resolve().parent / "schemas/meta_ads_personal_feed_v3.schema.json"
DEFAULT_CONFIG = Path("config/meta_ads_personal_feed_sources.json")
DEFAULT_STATE = Path("data/meta_ads_personal_feed_state.json")
DEFAULT_OUTPUT = Path("meta-ads-updates/personal-feed.json")
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
RSS_BLOCK_TAG = re.compile(r"</?(?:article|blockquote|br|div|h[1-6]|li|ol|p|section|ul)\b[^>]*>", flags=re.IGNORECASE)
RSS_TAG = re.compile(r"<[^>]+>")
RSS_NONCONTENT_TAG = re.compile(r"<(?:noscript|script|style)\b[^>]*>.*?</(?:noscript|script|style)\s*>", flags=re.IGNORECASE | re.DOTALL)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")
PARSER_TYPES = {"rss", "github_releases"}
CONTENT_TYPES = {
    "rss": ["application/rss+xml", "application/xml", "text/xml"],
    "github_releases": ["application/json"],
    "meta_business_news_html": ["text/html"],
}
PRESENTATION_STATUSES = {"generated", "pending"}
BILINGUAL_PRESENTATION_STATUSES = {"machine", "missing", "reviewed"}
SUPPORTED_LOCALES = ("en", "ja")
PRESENTATION_RETRY_QUEUE_SCHEMA_VERSION = "meta-ads-personal-feed-presentation-retry/v1"
PRESENTATION_RETRY_MAX_FAILURES = 5
PRESENTATION_RETRY_BASE_DELAY_SECONDS = 3600
PRESENTATION_RETRY_MAX_DELAY_SECONDS = 7 * 24 * 3600
PLATFORM_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
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
    if kind == "any_terms":
        payload = _expect_keys(value, {"kind", "terms"}, label)
        terms = payload["terms"]
        if not isinstance(terms, list) or not terms or len(terms) != len(set(terms)):
            raise ContractError(f"{label}.terms must be a unique non-empty array")
        for term in terms:
            _text(term, f"{label}.terms value")
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


def _validate_platform_ids(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) != len(set(value)):
        raise ContractError(f"{label} must be a unique non-empty array")
    for platform_id in value:
        if not isinstance(platform_id, str) or not PLATFORM_ID_RE.fullmatch(platform_id):
            raise ContractError(f"{label} values must be lowercase hyphenated identifiers")
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
    policies = _expect_keys(
        config["policies"],
        {"persistRawResponseBody", "historyRetentionDays", "maxPublishedItems", "freshness", "bilingualPresentation"},
        "personal feed policies",
    )
    if policies["persistRawResponseBody"] is not False:
        raise ContractError("personal feed must not persist raw response bodies")
    _limit(policies["historyRetentionDays"], "personal feed policies.historyRetentionDays", 1, 730)
    _limit(policies["maxPublishedItems"], "personal feed policies.maxPublishedItems", 1, 500)
    freshness = _expect_keys(policies["freshness"], {"maxItemAgeDays"}, "personal feed policies.freshness")
    _limit(freshness["maxItemAgeDays"], "personal feed policies.freshness.maxItemAgeDays", 1, 3650)
    presentation = _expect_keys(
        policies["bilingualPresentation"],
        {
            "maxRequestsPerRun",
            "maxInputChars",
            "shortHeadlineMaxChars",
            "summaryMaxChars",
            "minRequestIntervalSeconds",
            "maxAttempts",
            "maxRetryDelaySeconds",
        },
        "personal feed policies.bilingualPresentation",
    )
    _limit(presentation["maxRequestsPerRun"], "personal feed policies.bilingualPresentation.maxRequestsPerRun", 1, 50)
    _limit(presentation["maxInputChars"], "personal feed policies.bilingualPresentation.maxInputChars", 100, 12_000)
    _limit(presentation["shortHeadlineMaxChars"], "personal feed policies.bilingualPresentation.shortHeadlineMaxChars", 10, 240)
    _limit(presentation["summaryMaxChars"], "personal feed policies.bilingualPresentation.summaryMaxChars", 40, 1600)
    _limit(presentation["minRequestIntervalSeconds"], "personal feed policies.bilingualPresentation.minRequestIntervalSeconds", 1, 120)
    _limit(presentation["maxAttempts"], "personal feed policies.bilingualPresentation.maxAttempts", 1, 5)
    _limit(presentation["maxRetryDelaySeconds"], "personal feed policies.bilingualPresentation.maxRetryDelaySeconds", 1, 120)
    if not isinstance(config["sources"], list) or not config["sources"]:
        raise ContractError("personal feed sources must be a non-empty array")
    ids: set[str] = set()
    for index, value in enumerate(config["sources"]):
        label = f"personal feed sources[{index}]"
        source = _expect_keys(value, {"id", "name", "classification", "sourceUrl", "fetchUrl", "parser", "expectedContentTypes", "contentLanguage", "platforms", "platformIds", "transport", "relevanceRevision", "match"}, label)
        source_id = _expect_identifier(source["id"], f"{label}.id")
        if source_id in ids:
            raise ContractError(f"duplicate personal feed source id: {source_id}")
        ids.add(source_id)
        _text(source["name"], f"{label}.name")
        _expect_identifier(source["relevanceRevision"], f"{label}.relevanceRevision")
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
        if source["contentLanguage"] != "en":
            raise ContractError(f"{label}.contentLanguage must be en")
        _validate_platform_ids(source["platformIds"], f"{label}.platformIds")
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
            {"id", "name", "classification", "sourceUrl", "parser", "expectedContentTypes", "contentLanguage", "platforms", "platformIds", "transport", "relevanceRevision", "discovery"},
            label,
        )
        source_id = _expect_identifier(source["id"], f"{label}.id")
        if source_id in ids:
            raise ContractError(f"duplicate personal feed source id: {source_id}")
        ids.add(source_id)
        _text(source["name"], f"{label}.name")
        _expect_identifier(source["relevanceRevision"], f"{label}.relevanceRevision")
        if source["classification"] != "official":
            raise ContractError(f"{label}.classification must be official")
        if source["parser"] != "meta_business_news_html":
            raise ContractError(f"{label}.parser is unsupported")
        if source["expectedContentTypes"] != CONTENT_TYPES[source["parser"]]:
            raise ContractError(f"{label}.expectedContentTypes must match parser")
        source_url = _expect_https_url(source["sourceUrl"], f"{label}.sourceUrl")
        _validate_platforms(source["platforms"], f"{label}.platforms")
        if source["contentLanguage"] != "en":
            raise ContractError(f"{label}.contentLanguage must be en")
        _validate_platform_ids(source["platformIds"], f"{label}.platformIds")
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


def _rss_presentation_text(value: str) -> str:
    """Keep RSS block and sentence boundaries for transient model input only."""
    decoded = html.unescape(value or "")
    marked = RSS_BLOCK_TAG.sub("\n", RSS_NONCONTENT_TAG.sub(" ", decoded))
    text = RSS_TAG.sub(" ", marked)
    return "\n\n".join(_normalise(paragraph) for paragraph in text.splitlines() if _normalise(paragraph))


def _shorten_rss_presentation_context(value: str, maximum: int) -> str:
    """Fit complete RSS paragraphs or sentences within ``maximum`` characters.

    The input is never persisted.  The function deliberately never cuts a
    sentence mid-way: if the leading semantic unit cannot fit, the title alone
    remains available to the presentation request.
    """
    if len(value) <= maximum:
        return value
    selected: list[str] = []
    for paragraph in value.split("\n\n"):
        units = [unit.strip() for unit in SENTENCE_BOUNDARY.split(paragraph) if unit.strip()]
        for unit in units:
            candidate = "\n\n".join([*selected, unit])
            if len(candidate) > maximum:
                return "\n\n".join(selected)
            selected.append(unit)
    return "\n\n".join(selected)


def _presentation_context_for_model(raw: dict[str, Any], policy: dict[str, Any]) -> str:
    context = raw.get("presentationContext", raw["sourceContext"])
    if raw.get("presentationContextKind") == "rss":
        return _shorten_rss_presentation_context(context, policy["maxInputChars"])
    return context[: policy["maxInputChars"]]


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
        "presentationContext": description,
        "presentationContextKind": "plain",
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


def _match(
    source: dict[str, Any],
    title: str,
    source_context: str,
    categories: list[str],
) -> tuple[list[str] | None, list[bool]]:
    policy = source["match"]
    if policy["kind"] == "all":
        return [], []
    if policy["kind"] == "any_terms":
        searchable = "\n".join([title, source_context, *categories]).casefold()
        matched = next((term for term in policy["terms"] if _contains_term(searchable, term)), None)
        return ([f"keyword:{matched}"] if matched else None), []
    if policy["kind"] == "rss_category":
        category_set = {item.casefold() for item in categories}
        matched = [item for item in policy["categories"] if item.casefold() in category_set]
        return ([f"category:{item}" for item in matched] or None), []
    # Existing two-group sources keep their title-only contract.  Product News
    # uses any_terms, which intentionally also considers RSS descriptions and
    # categories under its separately versioned relevance rule.
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
        seen.add(url)
        published = _date_from_feed((fields.get("pubDate") or fields.get("published") or [None])[0])
        updated = _date_from_feed((fields.get("updated") or [None])[0])
        source_context_markup = (fields.get("encoded") or fields.get("description") or fields.get("content") or [""])[0]
        source_context = _strip_html(source_context_markup)
        items.append({
            "key": url,
            "url": url,
            "title": title[:280],
            "publishedDate": published,
            "updatedDate": updated,
            "matchEvidence": [],
            # This value is used only during this run.  It is deliberately not persisted.
            "sourceContext": source_context,
            "presentationContext": _rss_presentation_text(source_context_markup),
            "presentationContextKind": "rss",
            "categories": [item for item in fields.get("category", []) if item],
            "sourceContextMarkup": source_context_markup if discovery_source else "",
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
            "presentationContext": source_context,
            "presentationContextKind": "plain",
            "categories": [],
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


def _freshness_date(raw: dict[str, Any], first_observed_at: str) -> str:
    """Return the source's newest known date, falling back only to observation.

    lastObservedAt intentionally does not participate: repeatedly seeing an old
    article must not keep it in the public feed forever.
    """
    dates = [value for value in (raw.get("publishedDate"), raw.get("updatedDate")) if value is not None]
    if dates:
        return max(dates)
    return datetime.fromisoformat(first_observed_at.replace("Z", "+00:00")).date().isoformat()


def _is_fresh(raw: dict[str, Any], first_observed_at: str, now: datetime, policy: dict[str, Any]) -> bool:
    cutoff = now.astimezone(timezone.utc).date() - timedelta(days=policy["maxItemAgeDays"])
    return _freshness_date(raw, first_observed_at) >= cutoff.isoformat()


def _filter_items(
    source: dict[str, Any],
    raw_items: list[dict[str, Any]],
    prior: dict[str, Any],
    generated_at: str,
    now: datetime,
    freshness_policy: dict[str, Any],
    pipeline: dict[str, Any],
    discovery_source: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Apply freshness then source relevance without retaining source bodies."""
    accepted: list[dict[str, Any]] = []
    rejected_keys: set[str] = set()
    for raw in raw_items:
        existing = prior.get(raw["key"])
        first_observed_at = existing["firstObservedAt"] if existing else generated_at
        if not _is_fresh(raw, first_observed_at, now, freshness_policy):
            pipeline["freshnessExcludedItems"] += 1
            pipeline["excludedItems"] += 1
            rejected_keys.add(raw["key"])
            continue
        if "match" in source:
            evidence, group_matches = _match(source, raw["title"], raw["sourceContext"], raw["categories"])
        else:
            evidence, group_matches = raw["matchEvidence"], []
        for index, matched in enumerate(group_matches):
            if matched:
                pipeline["matchGroupMatches"][index] += 1
        if evidence is None:
            pipeline["relevanceExcludedItems"] += 1
            pipeline["excludedItems"] += 1
            rejected_keys.add(raw["key"])
            continue
        raw["matchEvidence"] = evidence
        if discovery_source is not None:
            links, deferred = _official_news_links(raw.pop("sourceContextMarkup", ""), discovery_source)
            raw["discoveredLinks"] = links
            raw["deferredDiscoveredLinks"] = deferred
        else:
            raw.pop("sourceContextMarkup", None)
        pipeline["matchedItems"] += 1
        accepted.append(raw)
    return accepted, rejected_keys


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


def _sha256_text(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _missing_bilingual_presentation(fingerprint: str, generator_revision: str) -> dict[str, Any]:
    english_input_hash = _sha256_text(fingerprint, generator_revision)
    japanese_input_hash = _sha256_text("missing", "missing", generator_revision)
    return {
        "schemaVersion": BILINGUAL_PRESENTATION_SCHEMA_VERSION,
        "sourceFingerprint": fingerprint,
        "generatorRevision": generator_revision,
        "locales": {
            "en": {
                "status": "missing",
                "shortHeadline": None,
                "summary": None,
                "inputHash": english_input_hash,
                "generatedAt": None,
                "reviewedAt": None,
            },
            "ja": {
                "status": "missing",
                "shortHeadline": None,
                "summary": None,
                "inputHash": japanese_input_hash,
                "generatedAt": None,
                "reviewedAt": None,
            },
        },
    }


def _validate_bilingual_locale(
    value: Any,
    label: str,
    *,
    expected_input_hash: str | None = None,
) -> dict[str, Any]:
    locale = _expect_keys(
        value,
        {"status", "shortHeadline", "summary", "inputHash", "generatedAt", "reviewedAt"},
        label,
    )
    if locale["status"] not in BILINGUAL_PRESENTATION_STATUSES:
        raise ContractError(f"{label}.status is unsupported")
    if not isinstance(locale["inputHash"], str) or not re.fullmatch(r"[a-f0-9]{64}", locale["inputHash"]):
        raise ContractError(f"{label}.inputHash must be a SHA-256 hash")
    if expected_input_hash is not None and locale["inputHash"] != expected_input_hash:
        raise ContractError(f"{label}.inputHash does not match its immutable input")
    status = locale["status"]
    if status == "missing":
        if locale["shortHeadline"] is not None or locale["summary"] is not None:
            raise ContractError(f"{label} missing values must not contain generated text")
        if locale["generatedAt"] is not None or locale["reviewedAt"] is not None:
            raise ContractError(f"{label} missing values must not have timestamps")
        return locale
    for field, maximum in (("shortHeadline", 240), ("summary", 1600)):
        if len(_text(locale[field], f"{label}.{field}")) > maximum:
            raise ContractError(f"{label}.{field} exceeds its maximum length")
    _timestamp(locale["generatedAt"], f"{label}.generatedAt")
    if status == "machine":
        if locale["reviewedAt"] is not None:
            raise ContractError(f"{label}.reviewedAt must be null for machine output")
    else:
        _timestamp(locale["reviewedAt"], f"{label}.reviewedAt")
    return locale


def _validate_bilingual_presentation(value: Any, fingerprint: str | None, label: str) -> dict[str, Any]:
    presentation = _expect_keys(
        value,
        {"schemaVersion", "sourceFingerprint", "generatorRevision", "locales"},
        label,
    )
    if presentation["schemaVersion"] != BILINGUAL_PRESENTATION_SCHEMA_VERSION:
        raise ContractError(f"{label}.schemaVersion must be {BILINGUAL_PRESENTATION_SCHEMA_VERSION}")
    if not isinstance(presentation["sourceFingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", presentation["sourceFingerprint"]):
        raise ContractError(f"{label}.sourceFingerprint must be a SHA-256 hash")
    if fingerprint is not None and presentation["sourceFingerprint"] != fingerprint:
        raise ContractError(f"{label}.sourceFingerprint must match the item fingerprint")
    generator_revision = _expect_identifier(presentation["generatorRevision"], f"{label}.generatorRevision")
    locales = _expect_keys(presentation["locales"], set(SUPPORTED_LOCALES), f"{label}.locales")
    english_expected = _sha256_text(presentation["sourceFingerprint"], generator_revision)
    english = _validate_bilingual_locale(locales["en"], f"{label}.locales.en", expected_input_hash=english_expected)
    japanese_expected = _sha256_text(
        english["shortHeadline"] or "missing",
        english["summary"] or "missing",
        generator_revision,
    )
    _validate_bilingual_locale(locales["ja"], f"{label}.locales.ja", expected_input_hash=japanese_expected)
    return presentation


def validate_v3_json_schema(payload: Any, schema_path: Path = DEFAULT_V3_SCHEMA) -> None:
    """Execute the versioned JSON Schema independently of Python shape checks."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as error:
        raise ContractError("Personal Feed v3 JSON Schema validation requires jsonschema") from error
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"unable to load Personal Feed v3 JSON Schema: {schema_path}") from error
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        raise ContractError(f"personal feed v3 violates JSON Schema at {location}: {error.message}")


def _empty_presentation_retry_queue() -> dict[str, Any]:
    return {"schemaVersion": PRESENTATION_RETRY_QUEUE_SCHEMA_VERSION, "entries": []}


def _retry_queue_key(source_id: str, item_key: str, locale: str) -> tuple[str, str, str]:
    return source_id, item_key, locale


def _retry_queue_map(queue: dict[str, Any] | None) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not queue:
        return {}
    return {
        _retry_queue_key(entry["sourceId"], entry["itemKey"], entry["locale"]): entry
        for entry in queue["entries"]
    }


def _retry_queue_payload(entries: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": PRESENTATION_RETRY_QUEUE_SCHEMA_VERSION,
        "entries": [entries[key] for key in sorted(entries)],
    }


def _validate_presentation_retry_queue(
    value: Any,
    config: dict[str, Any],
    sources: dict[str, Any],
) -> dict[str, Any]:
    queue = _expect_keys(value, {"schemaVersion", "entries"}, "personal feed presentationRetryQueue")
    if queue["schemaVersion"] != PRESENTATION_RETRY_QUEUE_SCHEMA_VERSION:
        raise ContractError("personal feed presentationRetryQueue schemaVersion is unsupported")
    if not isinstance(queue["entries"], list):
        raise ContractError("personal feed presentationRetryQueue.entries must be an array")
    seen: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(queue["entries"]):
        label = f"personal feed presentationRetryQueue.entries[{index}]"
        entry = _expect_keys(
            entry,
            {"sourceId", "itemKey", "fingerprint", "locale", "failureCount", "lastFailureAt", "nextRetryAt", "lastFailureCode", "quarantined"},
            label,
        )
        source_id = _expect_identifier(entry["sourceId"], f"{label}.sourceId")
        if source_id not in sources:
            raise ContractError(f"{label}.sourceId is unknown")
        item_key = _text(entry["itemKey"], f"{label}.itemKey")
        locale = entry["locale"]
        if locale not in SUPPORTED_LOCALES:
            raise ContractError(f"{label}.locale is unsupported")
        key = _retry_queue_key(source_id, item_key, locale)
        if key in seen:
            raise ContractError(f"{label} duplicates another queue entry")
        seen.add(key)
        if not isinstance(entry["fingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", entry["fingerprint"]):
            raise ContractError(f"{label}.fingerprint must be a SHA-256 hash")
        _limit(entry["failureCount"], f"{label}.failureCount", 1, PRESENTATION_RETRY_MAX_FAILURES)
        _timestamp(entry["lastFailureAt"], f"{label}.lastFailureAt")
        _timestamp(entry["nextRetryAt"], f"{label}.nextRetryAt", nullable=True)
        if not isinstance(entry["lastFailureCode"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,63}", entry["lastFailureCode"]):
            raise ContractError(f"{label}.lastFailureCode must be a safe reason code")
        if not isinstance(entry["quarantined"], bool):
            raise ContractError(f"{label}.quarantined must be a boolean")
        if entry["quarantined"] and entry["nextRetryAt"] is not None:
            raise ContractError(f"{label}.nextRetryAt must be null while quarantined")
        if not entry["quarantined"] and entry["nextRetryAt"] is None:
            raise ContractError(f"{label}.nextRetryAt is required before quarantine")
        item = sources[source_id]["items"].get(item_key)
        if item is None:
            raise ContractError(f"{label}.itemKey does not reference a retained item")
        if item["fingerprint"] != entry["fingerprint"]:
            raise ContractError(f"{label}.fingerprint must match the retained item")
        if item["presentation"]["locales"][locale]["status"] in {"machine", "reviewed"}:
            raise ContractError(f"{label} cannot queue a completed locale")
    return queue


def _retry_is_due(entry: dict[str, Any] | None, now: datetime) -> bool:
    if entry is None:
        return True
    if entry["quarantined"] or entry["nextRetryAt"] is None:
        return False
    retry_at = datetime.fromisoformat(entry["nextRetryAt"].replace("Z", "+00:00"))
    return retry_at <= now.astimezone(timezone.utc)


def _record_retry_failure(
    queue: dict[tuple[str, str, str], dict[str, Any]],
    source_id: str,
    item_key: str,
    fingerprint: str,
    locale: str,
    code: str,
    now: str,
) -> None:
    key = _retry_queue_key(source_id, item_key, locale)
    previous = queue.get(key)
    failure_count = (previous["failureCount"] if previous else 0) + 1
    failure_count = min(failure_count, PRESENTATION_RETRY_MAX_FAILURES)
    quarantined = failure_count >= PRESENTATION_RETRY_MAX_FAILURES
    next_retry_at = None
    if not quarantined:
        delay = min(
            PRESENTATION_RETRY_BASE_DELAY_SECONDS * (2 ** (failure_count - 1)),
            PRESENTATION_RETRY_MAX_DELAY_SECONDS,
        )
        retry_at = datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=delay)
        next_retry_at = _now(retry_at)
    queue[key] = {
        "sourceId": source_id,
        "itemKey": item_key,
        "fingerprint": fingerprint,
        "locale": locale,
        "failureCount": failure_count,
        "lastFailureAt": now,
        "nextRetryAt": next_retry_at,
        "lastFailureCode": code,
        "quarantined": quarantined,
    }


def validate_state(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("personal feed state must be an object")
    expected_state_keys = {"schemaVersion", "updatedAt", "sources"}
    if "presentationRetryQueue" in payload:
        expected_state_keys.add("presentationRetryQueue")
    state = _expect_keys(payload, expected_state_keys, "personal feed state")
    if state["schemaVersion"] not in {LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION, STATE_V3_SCHEMA_VERSION}:
        raise ContractError(f"personal feed state schemaVersion must be {LEGACY_STATE_SCHEMA_VERSION}, {STATE_SCHEMA_VERSION}, or {STATE_V3_SCHEMA_VERSION}")
    if "presentationRetryQueue" in payload and state["schemaVersion"] != STATE_V3_SCHEMA_VERSION:
        raise ContractError("personal feed presentationRetryQueue requires the v3 state schema")
    _timestamp(state["updatedAt"], "personal feed state.updatedAt", nullable=True)
    if not isinstance(state["sources"], dict):
        raise ContractError("personal feed state.sources must be an object")
    valid_ids = {source["id"] for source in _all_sources(config)}
    if set(state["sources"]) - valid_ids:
        raise ContractError("personal feed state has an unknown source")
    for source_id, source_state in state["sources"].items():
        expected_source_keys = {"items"}
        if state["schemaVersion"] == STATE_V3_SCHEMA_VERSION:
            expected_source_keys.add("relevanceRevision")
        source_payload = _expect_keys(source_state, expected_source_keys, f"personal feed state.sources.{source_id}")
        if state["schemaVersion"] == STATE_V3_SCHEMA_VERSION:
            _expect_identifier(source_payload["relevanceRevision"], f"personal feed state.sources.{source_id}.relevanceRevision")
        if not isinstance(source_payload["items"], dict):
            raise ContractError(f"personal feed state.sources.{source_id}.items must be an object")
        for key, item in source_payload["items"].items():
            _text(key, f"personal feed state.sources.{source_id} key")
            expected = {"url", "title", "publishedDate", "updatedDate", "matchEvidence", "fingerprint", "firstObservedAt", "lastObservedAt"}
            if state["schemaVersion"] in {STATE_SCHEMA_VERSION, STATE_V3_SCHEMA_VERSION}:
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
                    config["policies"]["bilingualPresentation"],
                )
            elif state["schemaVersion"] == STATE_V3_SCHEMA_VERSION:
                _validate_bilingual_presentation(
                    entry["presentation"],
                    entry["fingerprint"],
                    "personal feed state item.presentation",
                )
    queue = state.get("presentationRetryQueue", _empty_presentation_retry_queue())
    _validate_presentation_retry_queue(queue, config, state["sources"])
    return state


def _now(now: datetime) -> str:
    if now.tzinfo is None:
        raise ContractError("personal feed now must include a timezone")
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_descriptor(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in ("id", "name", "classification", "sourceUrl", "platforms")}


def _source_descriptor_v3(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in ("id", "name", "classification", "sourceUrl", "contentLanguage", "platformIds")}


def _source_descriptors(config: dict[str, Any], active_discovered_ids: set[str] | None = None) -> list[dict[str, Any]]:
    descriptors = [_source_descriptor(source) for source in config["sources"]]
    if active_discovered_ids:
        descriptors.extend(
            _source_descriptor(source)
            for source in config["discoveredSources"]
            if source["id"] in active_discovered_ids
        )
    return descriptors


def _source_descriptors_v3(config: dict[str, Any], active_discovered_ids: set[str] | None = None) -> list[dict[str, Any]]:
    descriptors = [_source_descriptor_v3(source) for source in config["sources"]]
    if active_discovered_ids:
        descriptors.extend(
            _source_descriptor_v3(source)
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
                "platformIds": source["platformIds"],
                "matchEvidence": record["matchEvidence"],
                "presentation": record["presentation"],
            })
    items.sort(key=_sort_key, reverse=True)
    return {
        "schemaVersion": FEED_V3_SCHEMA_VERSION,
        "defaultLocale": "en",
        "availableLocales": list(SUPPORTED_LOCALES),
        "generatedAt": generated_at,
        "sources": _source_descriptors_v3(config, active_discovered_ids),
        "items": items[:config["policies"]["maxPublishedItems"]],
    }


def _legacy_feed_fingerprint(item: dict[str, Any]) -> str:
    """Create a deterministic v3 migration fingerprint for a v1 feed item.

    v1 public feeds predate presentation fingerprints.  This value marks the
    exact legacy item that was migrated; it is not a claim that source text was
    re-fetched or revalidated.
    """
    canonical = json.dumps(
        {
            key: item[key]
            for key in ("title", "url", "publishedDate", "updatedDate", "firstObservedAt", "lastObservedAt", "matchEvidence")
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def migrate_state_v2_to_v3(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    generator_revision: str = DEFAULT_PRESENTATION_GENERATOR_REVISION,
) -> dict[str, Any]:
    """Return a one-way v2/v1 state migration without inventing translations.

    Existing Japanese v1 presentation text is deliberately discarded.  PR 2
    will generate both locales from source-language inputs; carrying legacy
    Japanese text into an English-canonical contract would reverse-translate
    and silently change its provenance.
    """
    if state.get("schemaVersion") not in {LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION}:
        raise ContractError("state migration accepts only Personal Feed state v1 or v2")
    validate_state(state, config)
    revision = _expect_identifier(generator_revision, "generator_revision")
    sources: dict[str, dict[str, Any]] = {}
    for source_id, source_state in state["sources"].items():
        records: dict[str, dict[str, Any]] = {}
        for key, record in source_state["items"].items():
            records[key] = {
                field: record[field]
                for field in ("url", "title", "publishedDate", "updatedDate", "matchEvidence", "fingerprint", "firstObservedAt", "lastObservedAt")
            }
            records[key]["presentation"] = _missing_bilingual_presentation(record["fingerprint"], revision)
        # v1/v2 stored no relevance revision.  Preserve that fact rather than
        # pretending its entries were evaluated with a newer rule.  A source
        # whose config revision changed is therefore required to be reseeded.
        sources[source_id] = {"relevanceRevision": LEGACY_RELEVANCE_REVISION, "items": records}
    migrated = {"schemaVersion": STATE_V3_SCHEMA_VERSION, "updatedAt": state["updatedAt"], "sources": sources}
    validate_state(migrated, config)
    return migrated


def migrate_feed_v2_to_v3(
    feed: dict[str, Any],
    config: dict[str, Any],
    *,
    generator_revision: str = DEFAULT_PRESENTATION_GENERATOR_REVISION,
) -> dict[str, Any]:
    """Return a one-way v2/v1 public-feed migration with bilingual missing values."""
    if feed.get("schemaVersion") not in {LEGACY_FEED_SCHEMA_VERSION, FEED_SCHEMA_VERSION}:
        raise ContractError("feed migration accepts only Personal Feed feed v1 or v2")
    validate_feed(feed, config)
    revision = _expect_identifier(generator_revision, "generator_revision")
    active_discovered_ids = {
        item["sourceId"]
        for item in feed["items"]
        if item["sourceId"] in {source["id"] for source in config["discoveredSources"]}
    }
    sources_by_id = {source["id"]: source for source in _all_sources(config)}
    migrated_items: list[dict[str, Any]] = []
    for item in feed["items"]:
        source = sources_by_id[item["sourceId"]]
        legacy_presentation = item.get("presentation")
        fingerprint = (
            legacy_presentation["sourceFingerprint"]
            if isinstance(legacy_presentation, dict) and isinstance(legacy_presentation.get("sourceFingerprint"), str)
            else _legacy_feed_fingerprint(item)
        )
        migrated_items.append({
            key: item[key]
            for key in ("id", "sourceId", "title", "url", "publishedDate", "updatedDate", "firstObservedAt", "lastObservedAt", "matchEvidence")
        } | {
            "platformIds": source["platformIds"],
            "presentation": _missing_bilingual_presentation(fingerprint, revision),
        })
    migrated = {
        "schemaVersion": FEED_V3_SCHEMA_VERSION,
        "defaultLocale": "en",
        "availableLocales": list(SUPPORTED_LOCALES),
        "generatedAt": feed["generatedAt"],
        "sources": _source_descriptors_v3(config, active_discovered_ids),
        "items": migrated_items,
    }
    validate_feed(migrated, config)
    return migrated


def _validate_v3_sources(feed: dict[str, Any], config: dict[str, Any]) -> set[str]:
    if not isinstance(feed["sources"], list):
        raise ContractError("personal feed sources must be an array")
    direct_descriptors = _source_descriptors_v3(config)
    optional_descriptors = [_source_descriptor_v3(source) for source in config["discoveredSources"]]
    if feed["sources"][:len(direct_descriptors)] != direct_descriptors:
        raise ContractError("personal feed v3 direct sources must exactly match configured descriptors")
    configured_optional = {value["id"]: value for value in optional_descriptors}
    seen_optional: list[str] = []
    for descriptor in feed["sources"][len(direct_descriptors):]:
        if not isinstance(descriptor, dict) or descriptor.get("id") not in configured_optional:
            raise ContractError("personal feed v3 has an unknown discovered source descriptor")
        if descriptor != configured_optional[descriptor["id"]] or descriptor["id"] in seen_optional:
            raise ContractError("personal feed v3 discovered source descriptor must match its configuration")
        seen_optional.append(descriptor["id"])
    expected_optional_order = [source["id"] for source in config["discoveredSources"] if source["id"] in seen_optional]
    if seen_optional != expected_optional_order:
        raise ContractError("personal feed v3 discovered source descriptors must keep configured order")
    return {descriptor["id"] for descriptor in feed["sources"]}


def _validate_feed_v3(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    validate_v3_json_schema(payload)
    feed = _expect_keys(payload, {"schemaVersion", "defaultLocale", "availableLocales", "generatedAt", "sources", "items"}, "personal feed v3")
    if feed["schemaVersion"] != FEED_V3_SCHEMA_VERSION:
        raise ContractError(f"personal feed v3 schemaVersion must be {FEED_V3_SCHEMA_VERSION}")
    if feed["defaultLocale"] != "en" or feed["availableLocales"] != list(SUPPORTED_LOCALES):
        raise ContractError("personal feed v3 locales must be default en with en and ja overlays")
    _timestamp(feed["generatedAt"], "personal feed v3.generatedAt", nullable=True)
    descriptor_ids = _validate_v3_sources(feed, config)
    if not isinstance(feed["items"], list) or len(feed["items"]) > config["policies"]["maxPublishedItems"]:
        raise ContractError("personal feed v3 items exceed configured limit")
    known_sources = {source["id"]: source for source in _all_sources(config)}
    ids: set[str] = set()
    for index, item in enumerate(feed["items"]):
        entry = _expect_keys(
            item,
            {"id", "sourceId", "title", "url", "publishedDate", "updatedDate", "firstObservedAt", "lastObservedAt", "platformIds", "matchEvidence", "presentation"},
            f"personal feed v3.items[{index}]",
        )
        item_id = _expect_identifier(entry["id"], f"personal feed v3.items[{index}].id")
        if item_id in ids:
            raise ContractError("personal feed v3 item IDs must be unique")
        ids.add(item_id)
        source = known_sources.get(entry["sourceId"])
        if source is None or entry["sourceId"] not in descriptor_ids:
            raise ContractError("personal feed v3 item references an unavailable source")
        _text(entry["title"], "personal feed v3 item.title")
        url = _expect_https_url(entry["url"], "personal feed v3 item.url")
        if urlsplit(url).hostname not in source["transport"]["allowedContentHosts"]:
            raise ContractError("personal feed v3 item URL must stay on its configured content host")
        _date(entry["publishedDate"], "personal feed v3 item.publishedDate", nullable=True)
        _date(entry["updatedDate"], "personal feed v3 item.updatedDate", nullable=True)
        _timestamp(entry["firstObservedAt"], "personal feed v3 item.firstObservedAt")
        _timestamp(entry["lastObservedAt"], "personal feed v3 item.lastObservedAt")
        if entry["platformIds"] != source["platformIds"]:
            raise ContractError("personal feed v3 item platformIds must match its source")
        if not isinstance(entry["matchEvidence"], list) or not all(isinstance(value, str) for value in entry["matchEvidence"]):
            raise ContractError("personal feed v3 item.matchEvidence must be a string array")
        _validate_bilingual_presentation(entry["presentation"], None, f"personal feed v3.items[{index}].presentation")
    return feed


def validate_feed(payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("schemaVersion") == FEED_V3_SCHEMA_VERSION:
        return _validate_feed_v3(payload, config)
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
                config["policies"]["bilingualPresentation"],
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


def _bilingual_presentation_from_environment(timeout: float) -> Callable[[str, str, dict[str, Any]], dict[str, str]] | None:
    """Return the one-request English-plus-Japanese presenter when enabled."""
    setting = os.environ.get("META_ADS_PERSONAL_FEED_JA_ENABLED", "").strip().lower() or "true"
    if setting not in {"true", "false"}:
        raise ContractError("META_ADS_PERSONAL_FEED_JA_ENABLED must be true, false, or unset")
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if setting == "false" or not api_key:
        return None
    model = os.environ.get("META_ADS_PERSONAL_FEED_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"
    next_request_at = 0.0

    def present(title: str, source_context: str, policy: dict[str, Any]) -> dict[str, str]:
        nonlocal next_request_at
        delay = max(0.0, next_request_at - time.monotonic())
        if delay:
            time.sleep(delay)
        try:
            return request_bilingual_presentation(
                api_key=api_key,
                model=model,
                title=title,
                source_context=source_context[:policy["maxInputChars"]],
                short_headline_max_chars=policy["shortHeadlineMaxChars"],
                summary_max_chars=policy["summaryMaxChars"],
                timeout=timeout,
                max_attempts=policy["maxAttempts"],
                max_retry_delay_seconds=policy["maxRetryDelaySeconds"],
            )
        finally:
            # This is deliberately applied after both success and failure so a
            # bad batch cannot turn into a tight retry loop across items.
            next_request_at = time.monotonic() + policy["minRequestIntervalSeconds"]

    return present


def _locale_presentation_from_environment(
    timeout: float,
) -> Callable[[str, str, dict[str, Any], str], dict[str, str]] | None:
    """Return an independent two-field presenter for one locale."""
    setting = os.environ.get("META_ADS_PERSONAL_FEED_JA_ENABLED", "").strip().lower() or "true"
    if setting not in {"true", "false"}:
        raise ContractError("META_ADS_PERSONAL_FEED_JA_ENABLED must be true, false, or unset")
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if setting == "false" or not api_key:
        return None
    model = os.environ.get("META_ADS_PERSONAL_FEED_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"
    next_request_at = 0.0

    def present(title: str, source_context: str, policy: dict[str, Any], locale: str) -> dict[str, str]:
        nonlocal next_request_at
        if locale not in SUPPORTED_LOCALES:
            raise PresentationError("response_invalid_shape")
        delay = max(0.0, next_request_at - time.monotonic())
        if delay:
            time.sleep(delay)
        try:
            if locale == "en":
                return request_english_presentation(
                    api_key=api_key,
                    model=model,
                    title=title,
                    source_context=source_context[:policy["maxInputChars"]],
                    short_headline_max_chars=policy["shortHeadlineMaxChars"],
                    summary_max_chars=policy["summaryMaxChars"],
                    timeout=timeout,
                    max_attempts=policy["maxAttempts"],
                    max_retry_delay_seconds=policy["maxRetryDelaySeconds"],
                )
            return request_presentation(
                api_key=api_key,
                model=model,
                title=title,
                source_context=source_context[:policy["maxInputChars"]],
                short_headline_max_chars=policy["shortHeadlineMaxChars"],
                summary_max_chars=policy["summaryMaxChars"],
                timeout=timeout,
                max_attempts=policy["maxAttempts"],
                max_retry_delay_seconds=policy["maxRetryDelaySeconds"],
            )
        finally:
            next_request_at = time.monotonic() + policy["minRequestIntervalSeconds"]

    return present


def _bilingual_fallback_from_environment(
    timeout: float,
) -> Callable[[str, str, dict[str, Any]], tuple[dict[str, str], dict[str, Exception]]] | None:
    """Return bounded English-then-Japanese fallback requests.

    Each locale gets at most one request after the four-field request fails.
    The returned error map contains exception objects only in memory so the
    collector can record safe reason codes without exposing response content.
    """
    setting = os.environ.get("META_ADS_PERSONAL_FEED_JA_ENABLED", "").strip().lower() or "true"
    if setting not in {"true", "false"}:
        raise ContractError("META_ADS_PERSONAL_FEED_JA_ENABLED must be true, false, or unset")
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if setting == "false" or not api_key:
        return None
    model = os.environ.get("META_ADS_PERSONAL_FEED_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"

    def fallback(title: str, source_context: str, policy: dict[str, Any]) -> tuple[dict[str, str], dict[str, Exception]]:
        generated: dict[str, str] = {}
        failures: dict[str, Exception] = {}
        try:
            for locale in ("en", "ja"):
                # Keep a full policy interval between the primary request and
                # each fallback request, and between the two locale requests.
                time.sleep(policy["minRequestIntervalSeconds"])
                try:
                    if locale == "en":
                        generated.update(
                            request_english_presentation(
                                api_key=api_key,
                                model=model,
                                title=title,
                                source_context=source_context[:policy["maxInputChars"]],
                                short_headline_max_chars=policy["shortHeadlineMaxChars"],
                                summary_max_chars=policy["summaryMaxChars"],
                                timeout=timeout,
                                max_attempts=1,
                            )
                        )
                    else:
                        generated.update(
                            request_presentation(
                                api_key=api_key,
                                model=model,
                                title=title,
                                source_context=source_context[:policy["maxInputChars"]],
                                short_headline_max_chars=policy["shortHeadlineMaxChars"],
                                summary_max_chars=policy["summaryMaxChars"],
                                timeout=timeout,
                                max_attempts=1,
                            )
                        )
                except (PresentationError, OSError, ValueError) as error:
                    failures[locale] = error
        finally:
            # The primary presenter owns its own rate gate. Leave one full
            # interval after the last fallback request before the next item can
            # start, so the two independent callbacks cannot make a tight loop.
            time.sleep(policy["minRequestIntervalSeconds"])
        return generated, failures

    return fallback


def _presentation_request_limit(value: int | None, policy: dict[str, Any]) -> int:
    maximum = policy["maxRequestsPerRun"]
    if value is None:
        return maximum
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ContractError(f"presentation request limit must be an integer from 1 to {maximum}")
    return value


def _presentation_stats(
    config: dict[str, Any],
    renderer_enabled: bool,
    request_limit: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "rendererEnabled": renderer_enabled,
        "requestLimit": request_limit,
        "minRequestIntervalSeconds": policy["minRequestIntervalSeconds"],
        "maxAttempts": policy["maxAttempts"],
        "eligible": 0,
        "attempted": 0,
        "localeAttempted": 0,
        "generated": 0,
        "localeGenerated": 0,
        "failed": 0,
        "localeFailed": 0,
        "fallbackAttempts": 0,
        "fallbackGeneratedLocales": 0,
        "fallbackFailedLocales": 0,
        "deferred": 0,
        "retryDeferred": 0,
        "retryQuarantined": 0,
        "failureReasons": {},
        "fallbackFailureReasons": {},
        "providerErrorTypes": {},
        "providerErrorCodes": {},
        "sources": {
            source["id"]: {
                "eligible": 0,
                "attempted": 0,
                "localeAttempted": 0,
                "generated": 0,
                "localeGenerated": 0,
                "failed": 0,
                "localeFailed": 0,
                "fallbackAttempts": 0,
                "fallbackGeneratedLocales": 0,
                "fallbackFailedLocales": 0,
                "retryDeferred": 0,
                "retryQuarantined": 0,
                "failureReasons": {},
                "fallbackFailureReasons": {},
                "providerErrorTypes": {},
                "providerErrorCodes": {},
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
                "freshnessExcludedItems": 0,
                "relevanceExcludedItems": 0,
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


def _record_presentation_failure(
    stats: dict[str, Any],
    source_id: str,
    code: str,
    error: Exception | None = None,
) -> None:
    stats["failureReasons"][code] = stats["failureReasons"].get(code, 0) + 1
    source_reasons = stats["sources"][source_id]["failureReasons"]
    source_reasons[code] = source_reasons.get(code, 0) + 1
    provider_error_type = getattr(error, "provider_error_type", None)
    provider_error_code = getattr(error, "provider_error_code", None)
    if provider_error_type:
        stats["providerErrorTypes"][provider_error_type] = stats["providerErrorTypes"].get(provider_error_type, 0) + 1
        source_types = stats["sources"][source_id]["providerErrorTypes"]
        source_types[provider_error_type] = source_types.get(provider_error_type, 0) + 1
    if provider_error_code:
        stats["providerErrorCodes"][provider_error_code] = stats["providerErrorCodes"].get(provider_error_code, 0) + 1
        source_codes = stats["sources"][source_id]["providerErrorCodes"]
        source_codes[provider_error_code] = source_codes.get(provider_error_code, 0) + 1


def _record_fallback_failure(
    stats: dict[str, Any],
    source_id: str,
    locale: str,
    code: str,
) -> None:
    key = f"{locale}:{code}"
    stats["fallbackFailureReasons"][key] = stats["fallbackFailureReasons"].get(key, 0) + 1
    source_reasons = stats["sources"][source_id]["fallbackFailureReasons"]
    source_reasons[key] = source_reasons.get(key, 0) + 1


def _print_presentation_stats(stats: dict[str, Any]) -> None:
    enabled = "true" if stats["rendererEnabled"] else "false"
    print(
        "PRESENTATION: "
        f"renderer_enabled={enabled} eligible={stats['eligible']} limit={stats['requestLimit']} "
        f"min_interval_seconds={stats['minRequestIntervalSeconds']} max_attempts={stats['maxAttempts']} "
        f"attempted={stats['attempted']} locale_attempted={stats['localeAttempted']} "
        f"generated={stats['generated']} locale_generated={stats['localeGenerated']} "
        f"failed={stats['failed']} locale_failed={stats['localeFailed']} "
        f"deferred={stats['deferred']} fallback_attempts={stats['fallbackAttempts']} "
        f"fallback_generated_locales={stats['fallbackGeneratedLocales']} "
        f"fallback_failed_locales={stats['fallbackFailedLocales']} "
        f"retry_deferred={stats['retryDeferred']} retry_quarantined={stats['retryQuarantined']}"
    )
    for source_id, counts in stats["sources"].items():
        print(
            "PRESENTATION_SOURCE: "
            f"id={source_id} eligible={counts['eligible']} attempted={counts['attempted']} "
            f"locale_attempted={counts['localeAttempted']} generated={counts['generated']} "
            f"locale_generated={counts['localeGenerated']} failed={counts['failed']} "
            f"locale_failed={counts['localeFailed']} "
            f"fallback_attempts={counts['fallbackAttempts']} "
            f"fallback_generated_locales={counts['fallbackGeneratedLocales']} "
            f"fallback_failed_locales={counts['fallbackFailedLocales']}"
            f" retry_deferred={counts['retryDeferred']} retry_quarantined={counts['retryQuarantined']}"
        )
        for code, count in sorted(counts["failureReasons"].items()):
            print(f"PRESENTATION_SOURCE_FAILURE: id={source_id} code={code} count={count}")
        for key, count in sorted(counts["fallbackFailureReasons"].items()):
            locale, code = key.split(":", 1)
            print(f"PRESENTATION_SOURCE_FALLBACK_FAILURE: id={source_id} locale={locale} code={code} count={count}")
        for error_type, count in sorted(counts["providerErrorTypes"].items()):
            print(f"PRESENTATION_SOURCE_ERROR_TYPE: id={source_id} error_type={error_type} count={count}")
        for error_code, count in sorted(counts["providerErrorCodes"].items()):
            print(f"PRESENTATION_SOURCE_ERROR_CODE: id={source_id} error_code={error_code} count={count}")
    for code, count in sorted(stats["failureReasons"].items()):
        print(f"PRESENTATION_FAILURE: code={code} count={count}")
    for key, count in sorted(stats["fallbackFailureReasons"].items()):
        locale, code = key.split(":", 1)
        print(f"PRESENTATION_FALLBACK_FAILURE: locale={locale} code={code} count={count}")
    for error_type, count in sorted(stats["providerErrorTypes"].items()):
        print(f"PRESENTATION_ERROR_TYPE: error_type={error_type} count={count}")
    for error_code, count in sorted(stats["providerErrorCodes"].items()):
        print(f"PRESENTATION_ERROR_CODE: error_code={error_code} count={count}")


def _print_source_pipeline_stats(stats: dict[str, Any]) -> None:
    for source_id, counts in stats["sources"].items():
        print(
            "SOURCE_PIPELINE: "
            f"id={source_id} mode={counts['mode']} parser_version={stats['parserVersion']} "
            f"fetched={'true' if counts['fetched'] else 'false'} "
            f"response_bytes={counts['responseBytes']} parsed={counts['parsedItems']} valid={counts['validItems']} "
            f"matched={counts['matchedItems']} expired={counts['freshnessExcludedItems']} "
            f"relevance_excluded={counts['relevanceExcludedItems']} excluded={counts['excludedItems']} "
            f"retained={counts['retainedItems']} "
            f"discovered_links={counts['discoveredLinks']} attempted_links={counts['attemptedLinks']} "
            f"rejected_links={counts['rejectedLinks']} deferred_links={counts['deferredLinks']}"
        )
        for index, count in enumerate(counts["matchGroupMatches"], start=1):
            print(f"SOURCE_MATCH_GROUP: id={source_id} group={index} matched={count}")


def _machine_bilingual_presentation(
    fingerprint: str,
    generated: dict[str, Any],
    generated_at: str,
    generator_revision: str = DEFAULT_PRESENTATION_GENERATOR_REVISION,
) -> dict[str, Any]:
    """Build one validated bilingual cache entry from one model response."""
    try:
        revision = _expect_identifier(generator_revision, "generator_revision")
        english_headline = _text(generated["shortHeadlineEn"], "english short headline")
        english_summary = _text(generated["summaryEn"], "english summary")
        japanese_headline = _text(generated["shortHeadlineJa"], "Japanese short headline")
        japanese_summary = _text(generated["summaryJa"], "Japanese summary")
    except (ContractError, KeyError) as error:
        raise PresentationError("response_invalid_shape") from error
    if len(english_headline) > 240 or len(japanese_headline) > 240:
        raise PresentationError("short_headline_invalid")
    if len(english_summary) > 1600 or len(japanese_summary) > 1600:
        raise PresentationError("summary_invalid")
    english_input_hash = _sha256_text(fingerprint, revision)
    japanese_input_hash = _sha256_text(english_headline, english_summary, revision)
    return {
        "schemaVersion": BILINGUAL_PRESENTATION_SCHEMA_VERSION,
        "sourceFingerprint": fingerprint,
        "generatorRevision": revision,
        "locales": {
            "en": {
                "status": "machine",
                "shortHeadline": english_headline,
                "summary": english_summary,
                "inputHash": english_input_hash,
                "generatedAt": generated_at,
                "reviewedAt": None,
            },
            "ja": {
                "status": "machine",
                "shortHeadline": japanese_headline,
                "summary": japanese_summary,
                "inputHash": japanese_input_hash,
                "generatedAt": generated_at,
                "reviewedAt": None,
            },
        },
    }


def _partial_bilingual_presentation(
    fingerprint: str,
    generated: dict[str, Any],
    generated_at: str,
    generator_revision: str = DEFAULT_PRESENTATION_GENERATOR_REVISION,
) -> dict[str, Any]:
    """Build a valid bilingual entry when fallback generated one locale only."""
    revision = _expect_identifier(generator_revision, "generator_revision")
    locale_values: dict[str, tuple[str, str]] = {
        "en": ("shortHeadlineEn", "summaryEn"),
        "ja": ("shortHeadlineJa", "summaryJa"),
    }
    locales: dict[str, dict[str, Any]] = {}
    for locale, (headline_key, summary_key) in locale_values.items():
        headline = generated.get(headline_key)
        summary = generated.get(summary_key)
        if headline is None and summary is None:
            japanese_input = (
                generated.get("shortHeadlineEn") or "missing",
                generated.get("summaryEn") or "missing",
            )
            locales[locale] = {
                "status": "missing",
                "shortHeadline": None,
                "summary": None,
                "inputHash": _sha256_text(*japanese_input, revision) if locale == "ja" else _sha256_text(fingerprint, revision),
                "generatedAt": None,
                "reviewedAt": None,
            }
            continue
        if not isinstance(headline, str) or not isinstance(summary, str):
            raise PresentationError("response_invalid_shape")
        headline = _text(headline, f"{locale} short headline")
        summary = _text(summary, f"{locale} summary")
        if len(headline) > 240:
            raise PresentationError("short_headline_invalid")
        if len(summary) > 1600:
            raise PresentationError("summary_invalid")
        locales[locale] = {
            "status": "machine",
            "shortHeadline": headline,
            "summary": summary,
            "inputHash": _sha256_text(fingerprint, revision)
            if locale == "en"
            else _sha256_text(
                generated.get("shortHeadlineEn") or "missing",
                generated.get("summaryEn") or "missing",
                revision,
            ),
            "generatedAt": generated_at,
            "reviewedAt": None,
        }
    return {
        "schemaVersion": BILINGUAL_PRESENTATION_SCHEMA_VERSION,
        "sourceFingerprint": fingerprint,
        "generatorRevision": revision,
        "locales": locales,
    }


def _pending_presentation_locales(presentation: dict[str, Any]) -> list[str]:
    """Return locales that still need display text, preserving locale independence."""
    return [
        locale
        for locale in SUPPORTED_LOCALES
        if presentation["locales"][locale]["status"] not in {"machine", "reviewed"}
    ]


def _merge_locale_presentation(
    existing: dict[str, Any],
    fingerprint: str,
    locale: str,
    generated: dict[str, Any],
    generated_at: str,
    generator_revision: str = DEFAULT_PRESENTATION_GENERATOR_REVISION,
) -> dict[str, Any]:
    """Persist one locale without incorrectly claiming the other is generated.

    Japanese text is derived from the English fields.  Therefore a newly
    generated English locale invalidates any older Japanese locale and leaves
    it explicitly ``missing`` until it is regenerated from the new English.
    """
    if locale not in SUPPORTED_LOCALES:
        raise PresentationError("response_invalid_shape")
    revision = _expect_identifier(generator_revision, "generator_revision")
    headline_key = "shortHeadlineEn" if locale == "en" else "shortHeadlineJa"
    summary_key = "summaryEn" if locale == "en" else "summaryJa"
    try:
        headline = _text(generated[headline_key], f"{locale} short headline")
        summary = _text(generated[summary_key], f"{locale} summary")
    except (ContractError, KeyError) as error:
        raise PresentationError("response_invalid_shape") from error
    if len(headline) > 240:
        raise PresentationError("short_headline_invalid")
    if len(summary) > 1600:
        raise PresentationError("summary_invalid")

    presentation = copy.deepcopy(existing)
    presentation["schemaVersion"] = BILINGUAL_PRESENTATION_SCHEMA_VERSION
    presentation["sourceFingerprint"] = fingerprint
    presentation["generatorRevision"] = revision
    english = presentation["locales"]["en"]
    japanese = presentation["locales"]["ja"]
    if locale == "en":
        english = {
            "status": "machine",
            "shortHeadline": headline,
            "summary": summary,
            "inputHash": _sha256_text(fingerprint, revision),
            "generatedAt": generated_at,
            "reviewedAt": None,
        }
        # The Japanese input hash is tied to the English text.  Do not retain
        # a translation that was produced from an earlier/missing English value.
        japanese = {
            "status": "missing",
            "shortHeadline": None,
            "summary": None,
            "inputHash": _sha256_text(headline, summary, revision),
            "generatedAt": None,
            "reviewedAt": None,
        }
    else:
        english_values = (
            english.get("shortHeadline") or "missing",
            english.get("summary") or "missing",
        )
        japanese = {
            "status": "machine",
            "shortHeadline": headline,
            "summary": summary,
            "inputHash": _sha256_text(*english_values, revision),
            "generatedAt": generated_at,
            "reviewedAt": None,
        }
    presentation["locales"] = {"en": english, "ja": japanese}
    return presentation


def _reseed_source(config: dict[str, Any], value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    source_id = _expect_identifier(value.strip(), "reseed source ID")
    if source_id not in {source["id"] for source in _all_sources(config)}:
        raise ContractError("reseed source ID must name a configured source")
    return source_id


def _assert_relevance_reseed(state: dict[str, Any], config: dict[str, Any], reseed_source_id: str | None) -> None:
    for source in _all_sources(config):
        source_state = state["sources"].get(source["id"])
        if source_state is None:
            continue
        if source_state["relevanceRevision"] != source["relevanceRevision"] and reseed_source_id != source["id"]:
            raise ContractError(
                f"personal feed source {source['id']} relevance revision changed; rerun with --reseed-source {source['id']}"
            )


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
    present_item: Callable[[str, str, dict[str, Any]], dict[str, str]] | None = None,
    fallback_item: Callable[[str, str, dict[str, Any]], tuple[dict[str, str], dict[str, Exception]]] | None = None,
    *,
    locale_item: Callable[[str, str, dict[str, Any], str], dict[str, str]] | None = None,
    presentation_limit: int | None = None,
    presentation_stats: dict[str, Any] | None = None,
    source_pipeline_stats: dict[str, Any] | None = None,
    reseed_source_id: str | None = None,
    retry_failed: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_config(config)
    validate_state(state, config)
    if state["schemaVersion"] != STATE_V3_SCHEMA_VERSION:
        state = migrate_state_v2_to_v3(state, config)
    retry_queue = _retry_queue_map(state.get("presentationRetryQueue"))
    if retry_failed:
        retry_queue.clear()
    reseed_source_id = _reseed_source(config, reseed_source_id)
    _assert_relevance_reseed(state, config, reseed_source_id)
    generated_at = _now(now)
    history_cutoff = now.astimezone(timezone.utc) - timedelta(days=config["policies"]["historyRetentionDays"])
    presentation_policy = config["policies"]["bilingualPresentation"]
    request_limit = _presentation_request_limit(presentation_limit, presentation_policy)
    stats = _presentation_stats(config, present_item is not None or locale_item is not None, request_limit, presentation_policy)
    pipeline = _source_pipeline_stats(config)

    # First complete safe fetch, format validation and parsing for every direct
    # source.  No model request or persistent output is produced before all of
    # those fail-closed boundaries have passed.
    parsed_by_source: dict[str, list[dict[str, Any]]] = {}
    raw_by_source: dict[str, list[dict[str, Any]]] = {}
    rejected_by_source: dict[str, set[str]] = {}
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
        parsed_by_source[source["id"]] = extract_items(
            source,
            body,
            source_pipeline,
            discovery_by_origin.get(source["id"]),
        )

    # Freshness and relevance use only successfully parsed candidates.  This
    # phase remains before state construction and before every model request.
    for source in config["sources"]:
        source_pipeline = pipeline["sources"][source["id"]]
        prior = state["sources"].get(source["id"], {"items": {}})["items"]
        raw_by_source[source["id"]], rejected_by_source[source["id"]] = _filter_items(
            source,
            parsed_by_source[source["id"]],
            prior,
            generated_at,
            now,
            config["policies"]["freshness"],
            source_pipeline,
            discovery_by_origin.get(source["id"]),
        )

    # A discovered official source is deliberately independent: an inaccessible
    # article rejects that article only, never a successfully collected direct
    # source.  It still passes freshness before becoming state or model input.
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
            except (ContractError, OSError, ValueError, urllib.error.URLError):
                # Discovery is optional. Reject only this candidate without logging its URL,
                # response, or exception text, and keep the direct-source collection usable.
                source_pipeline["rejectedLinks"] += 1
        prior = state["sources"].get(source["id"], {"items": {}})["items"]
        raw_by_source[source["id"]], rejected_by_source[source["id"]] = _filter_items(
            source,
            promoted,
            prior,
            generated_at,
            now,
            config["policies"]["freshness"],
            source_pipeline,
        )

    # Build state only after every candidate has been parsed and screened.
    # sourceContext, release notes, markup, and any model response remain local
    # variables and are deliberately excluded from this structure.
    next_state: dict[str, Any] = {"schemaVersion": STATE_V3_SCHEMA_VERSION, "updatedAt": generated_at, "sources": {}}
    presentation_candidates: list[tuple[str, dict[str, Any], dict[str, Any], list[str]]] = []
    for source in _all_sources(config):
        prior = state["sources"].get(source["id"], {"items": {}})["items"]
        current: dict[str, Any] = {}
        if source["id"] != reseed_source_id:
            for key, record in prior.items():
                if _is_fresh(record, record["firstObservedAt"], now, config["policies"]["freshness"]):
                    current[key] = {
                        "url": record["url"],
                        "title": record["title"],
                        "publishedDate": record["publishedDate"],
                        "updatedDate": record["updatedDate"],
                        "matchEvidence": record["matchEvidence"],
                        "fingerprint": record["fingerprint"],
                        "firstObservedAt": record["firstObservedAt"],
                        "lastObservedAt": record["lastObservedAt"],
                        "presentation": record["presentation"],
                    }
        for key in rejected_by_source[source["id"]]:
            current.pop(key, None)
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
                "presentation": cached or _missing_bilingual_presentation(raw["fingerprint"], DEFAULT_PRESENTATION_GENERATOR_REVISION),
            }
            current[raw["key"]] = record
            pending_locales = _pending_presentation_locales(record["presentation"])
            due_locales = [
                locale
                for locale in pending_locales
                if _retry_is_due(retry_queue.get(_retry_queue_key(source["id"], raw["key"], locale)), now)
            ]
            if due_locales:
                presentation_candidates.append((source["id"], record, raw, due_locales))
                stats["eligible"] += 1
                stats["sources"][source["id"]]["eligible"] += 1
            elif pending_locales:
                stats["retryDeferred"] += 1
                stats["sources"][source["id"]]["retryDeferred"] += 1
                if any(
                    retry_queue.get(_retry_queue_key(source["id"], raw["key"], locale), {}).get("quarantined", False)
                    for locale in pending_locales
                ):
                    stats["retryQuarantined"] += 1
                    stats["sources"][source["id"]]["retryQuarantined"] += 1
        retained: dict[str, Any] = {}
        for key, record in current.items():
            observed = datetime.fromisoformat(record["lastObservedAt"].replace("Z", "+00:00"))
            if observed >= history_cutoff:
                retained[key] = record
        next_state["sources"][source["id"]] = {"relevanceRevision": source["relevanceRevision"], "items": retained}
        pipeline["sources"][source["id"]]["retainedItems"] = len(retained)

    # Remove queue entries for expired, replaced, or successfully completed
    # records before the next state is validated and persisted.
    for queue_key, entry in list(retry_queue.items()):
        source_id, item_key, locale = queue_key
        record = next_state["sources"].get(source_id, {"items": {}})["items"].get(item_key)
        if record is None or record["fingerprint"] != entry["fingerprint"] or record["presentation"]["locales"][locale]["status"] in {"machine", "reviewed"}:
            del retry_queue[queue_key]

    presentation_candidates.sort(
        key=lambda pair: (
            pair[1]["updatedDate"] or pair[1]["publishedDate"] or pair[1]["firstObservedAt"],
            pair[1]["url"],
        ),
        reverse=True,
    )
    if present_item is not None or locale_item is not None:
        for source_id, record, raw, due_locales in presentation_candidates[:request_limit]:
            stats["attempted"] += 1
            stats["sources"][source_id]["attempted"] += 1
            pending = _pending_presentation_locales(record["presentation"])
            initial_statuses = {
                locale: record["presentation"]["locales"][locale]["status"]
                for locale in SUPPORTED_LOCALES
            }
            full_attempt = (
                present_item is not None
                and len(pending) == len(SUPPORTED_LOCALES)
                and set(due_locales) == set(SUPPORTED_LOCALES)
            )
            if full_attempt:
                stats["localeAttempted"] += len(SUPPORTED_LOCALES)
                stats["sources"][source_id]["localeAttempted"] += len(SUPPORTED_LOCALES)
                try:
                    generated = present_item(record["title"], _presentation_context_for_model(raw, presentation_policy), presentation_policy)
                    record["presentation"] = _machine_bilingual_presentation(record["fingerprint"], generated, generated_at)
                    for locale in SUPPORTED_LOCALES:
                        retry_queue.pop(_retry_queue_key(source_id, raw["key"], locale), None)
                    stats["localeGenerated"] += len(SUPPORTED_LOCALES)
                    stats["sources"][source_id]["localeGenerated"] += len(SUPPORTED_LOCALES)
                except (KeyError, PresentationError, ValueError, OSError) as error:
                    failure_code = _presentation_failure_code(error)
                    _record_presentation_failure(stats, source_id, failure_code, error)
                    fallback_generated: dict[str, str] = {}
                    fallback_failures: dict[str, Exception] = {}
                    if fallback_item is not None:
                        stats["fallbackAttempts"] += 1
                        stats["sources"][source_id]["fallbackAttempts"] += 1
                        try:
                            fallback_generated, fallback_failures = fallback_item(
                                record["title"],
                                _presentation_context_for_model(raw, presentation_policy),
                                presentation_policy,
                            )
                        except (KeyError, PresentationError, ValueError, OSError) as fallback_error:
                            fallback_failures = {"unknown": fallback_error}
                        for locale, fallback_error in fallback_failures.items():
                            code = _presentation_failure_code(fallback_error)
                            _record_fallback_failure(stats, source_id, locale, code)

                    complete_locales = {
                        locale
                        for locale, (headline_key, summary_key) in {
                            "en": ("shortHeadlineEn", "summaryEn"),
                            "ja": ("shortHeadlineJa", "summaryJa"),
                        }.items()
                        if isinstance(fallback_generated.get(headline_key), str)
                        and isinstance(fallback_generated.get(summary_key), str)
                    }
                    if fallback_generated:
                        try:
                            record["presentation"] = _partial_bilingual_presentation(
                                record["fingerprint"], fallback_generated, generated_at
                            )
                        except (KeyError, PresentationError, ValueError) as fallback_error:
                            _record_fallback_failure(stats, source_id, "presentation", _presentation_failure_code(fallback_error))
                            complete_locales = set()
                            record["presentation"] = _missing_bilingual_presentation(record["fingerprint"], DEFAULT_PRESENTATION_GENERATOR_REVISION)
                    else:
                        # Model errors must not block publication. The source title
                        # remains available while both generated locales stay missing.
                        record["presentation"] = _missing_bilingual_presentation(record["fingerprint"], DEFAULT_PRESENTATION_GENERATOR_REVISION)

                    generated_locales = len(complete_locales)
                    fallback_failed_locales = len(set(SUPPORTED_LOCALES) - complete_locales)
                    if fallback_item is not None:
                        stats["fallbackGeneratedLocales"] += generated_locales
                        stats["fallbackFailedLocales"] += fallback_failed_locales
                        stats["localeGenerated"] += generated_locales
                        stats["localeFailed"] += fallback_failed_locales
                        stats["sources"][source_id]["fallbackGeneratedLocales"] += generated_locales
                        stats["sources"][source_id]["fallbackFailedLocales"] += fallback_failed_locales
                        stats["sources"][source_id]["localeGenerated"] += generated_locales
                        stats["sources"][source_id]["localeFailed"] += fallback_failed_locales
                    for locale in due_locales:
                        if locale in complete_locales:
                            retry_queue.pop(_retry_queue_key(source_id, raw["key"], locale), None)
                        else:
                            code = _presentation_failure_code(fallback_failures.get(locale, error))
                            _record_retry_failure(
                                retry_queue,
                                source_id,
                                raw["key"],
                                record["fingerprint"],
                                locale,
                                code,
                                generated_at,
                            )
            elif locale_item is not None:
                # A previously successful locale is never regenerated merely
                # because its sibling is missing. Each locale has its own
                # lifecycle and can recover on a later run independently.
                locales_to_attempt = list(due_locales)
                # If English was pending and regenerating it invalidates a
                # previously successful Japanese overlay, refresh that overlay
                # immediately. A Japanese locale already deferred by the queue
                # remains deferred and is not silently retried.
                if (
                    "en" in locales_to_attempt
                    and initial_statuses.get("ja") in {"machine", "reviewed"}
                    and "ja" not in locales_to_attempt
                ):
                    locales_to_attempt.append("ja")
                for locale in locales_to_attempt:
                    if locale not in _pending_presentation_locales(record["presentation"]):
                        continue
                    stats["localeAttempted"] += 1
                    stats["sources"][source_id]["localeAttempted"] += 1
                    try:
                        generated = locale_item(
                            record["title"],
                            _presentation_context_for_model(raw, presentation_policy),
                            presentation_policy,
                            locale,
                        )
                        record["presentation"] = _merge_locale_presentation(
                            record["presentation"], record["fingerprint"], locale, generated, generated_at
                        )
                        retry_queue.pop(_retry_queue_key(source_id, raw["key"], locale), None)
                        stats["localeGenerated"] += 1
                        stats["sources"][source_id]["localeGenerated"] += 1
                    except (KeyError, PresentationError, ValueError, OSError) as error:
                        code = _presentation_failure_code(error)
                        _record_presentation_failure(stats, source_id, code, error)
                        _record_retry_failure(
                            retry_queue,
                            source_id,
                            raw["key"],
                            record["fingerprint"],
                            locale,
                            code,
                            generated_at,
                        )
                        stats["localeFailed"] += 1
                        stats["sources"][source_id]["localeFailed"] += 1
            if any(locale["status"] in {"machine", "reviewed"} for locale in record["presentation"]["locales"].values()):
                stats["generated"] += 1
                stats["sources"][source_id]["generated"] += 1
            else:
                stats["failed"] += 1
                stats["sources"][source_id]["failed"] += 1
    next_state["presentationRetryQueue"] = _retry_queue_payload(retry_queue)
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
    fallback_item: Callable[[str, str, dict[str, Any]], tuple[dict[str, str], dict[str, Exception]]] | None = None,
    locale_item: Callable[[str, str, dict[str, Any], str], dict[str, str]] | None = None,
    presentation_limit: int | None = None,
    presentation_stats: dict[str, Any] | None = None,
    source_pipeline_stats: dict[str, Any] | None = None,
    reseed_source_id: str | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"schemaVersion": STATE_SCHEMA_VERSION, "updatedAt": None, "sources": {}}
    renderer = present_item if present_item is not None else _bilingual_presentation_from_environment(timeout)
    fallback_renderer = fallback_item if fallback_item is not None else _bilingual_fallback_from_environment(timeout)
    locale_renderer = locale_item if locale_item is not None else _locale_presentation_from_environment(timeout)
    feed, next_state = collect(
        config,
        state,
        timeout,
        now or datetime.now(timezone.utc),
        fetch_body,
        renderer,
        fallback_renderer,
        locale_item=locale_renderer,
        presentation_limit=presentation_limit,
        presentation_stats=presentation_stats,
        source_pipeline_stats=source_pipeline_stats,
        reseed_source_id=reseed_source_id,
        retry_failed=retry_failed,
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
    parser.add_argument("--reseed-source", default=None, help="re-evaluate one configured source under its current relevance revision")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="clear the isolated presentation retry queue before this run",
    )
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
            reseed_source_id=args.reseed_source,
            retry_failed=args.retry_failed,
        )
    except SourceFetchError as error:
        print(
            f"SOURCE_FETCH_FAILURE: id={error.source_id} code={error.reason} attempts={error.attempts}",
            file=sys.stderr,
        )
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    except (ContractError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: published {len(feed['items'])} personal feed item(s) from {len(feed['sources'])} source(s)")
    _print_presentation_stats(stats)
    _print_source_pipeline_stats(pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
