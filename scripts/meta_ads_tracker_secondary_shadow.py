#!/usr/bin/env python3
"""Collect non-official Meta Ads signals into an isolated, non-public shadow queue.

This module is intentionally not an adapter for the official tracker.  It never
writes official candidates, weekly artifacts, decisions, public reports, or UI
files.  It retains URL/title metadata and fingerprints only; response bodies
and excerpts are discarded before the result is returned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from meta_ads_tracker_collect import _request as bounded_request
from meta_ads_tracker_contract import ContractError, _expect_hostname, _expect_https_url, _expect_identifier
from meta_ads_tracker_publication import write_json


SHADOW_SOURCE_SCHEMA_VERSION = "meta-ads-secondary-shadow-sources/v1"
SHADOW_STATE_SCHEMA_VERSION = "meta-ads-secondary-shadow-state/v1"
SHADOW_REPORT_SCHEMA_VERSION = "meta-ads-secondary-shadow-observation/v1"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/meta_ads_secondary_shadow_sources.json"
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
HASH_RE = re.compile(r"^[a-f0-9]{64}$")


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ContractError(f"{label} keys must be exactly {', '.join(sorted(expected))}")
    return value


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value.strip()


def _expect_limit(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContractError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def validate_config(payload: Any) -> dict[str, Any]:
    config = _expect_keys(payload, {"schemaVersion", "policies", "sources"}, "secondary shadow config")
    if config["schemaVersion"] != SHADOW_SOURCE_SCHEMA_VERSION:
        raise ContractError(f"secondary shadow config schemaVersion must be {SHADOW_SOURCE_SCHEMA_VERSION}")
    policies = _expect_keys(
        config["policies"],
        {"publicationEligible", "officialCandidateIntegration", "persistRawResponseBody", "requireHumanOfficialVerification", "stateBranch"},
        "secondary shadow policies",
    )
    if policies["publicationEligible"] is not False or policies["officialCandidateIntegration"] is not False:
        raise ContractError("secondary shadow signals must never be public or official candidates")
    if policies["persistRawResponseBody"] is not False or policies["requireHumanOfficialVerification"] is not True:
        raise ContractError("secondary shadow policies must remain body-free and human-verified")
    if policies["stateBranch"] != "automation/meta-ads-shadow-state":
        raise ContractError("secondary shadow stateBranch must be the dedicated automation branch")

    sources = config["sources"]
    if not isinstance(sources, list) or not sources:
        raise ContractError("secondary shadow sources must be a non-empty array")
    ids: set[str] = set()
    automatic_count = 0
    for index, value in enumerate(sources):
        source = _expect_keys(
            value,
            {"id", "name", "kind", "sourceUrl", "fetchUrl", "enabled", "collectionMode", "expectedContentTypes", "transport", "matchKeywords", "rationale"},
            f"secondary shadow sources[{index}]",
        )
        source_id = _expect_identifier(source["id"], f"secondary shadow sources[{index}].id")
        if source_id in ids:
            raise ContractError(f"duplicate secondary shadow source id: {source_id}")
        ids.add(source_id)
        _expect_string(source["name"], f"secondary shadow sources[{index}].name")
        _expect_string(source["rationale"], f"secondary shadow sources[{index}].rationale")
        if source["kind"] != "secondary_signal":
            raise ContractError(f"secondary shadow sources[{index}].kind must be secondary_signal")
        fetch_url = _expect_https_url(source["fetchUrl"], f"secondary shadow sources[{index}].fetchUrl")
        _expect_https_url(source["sourceUrl"], f"secondary shadow sources[{index}].sourceUrl")
        parsed = urlsplit(fetch_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ContractError(f"secondary shadow sources[{index}].fetchUrl has an invalid port") from error
        if parsed.username or parsed.password or port not in {None, 443}:
            raise ContractError(f"secondary shadow sources[{index}].fetchUrl must use credential-free standard HTTPS")
        if not isinstance(source["enabled"], bool):
            raise ContractError(f"secondary shadow sources[{index}].enabled must be boolean")
        expected_mode = "automatic_shadow" if source["enabled"] else "manual_only"
        if source["collectionMode"] != expected_mode:
            raise ContractError(f"secondary shadow sources[{index}].collectionMode must match enabled state")
        if source["enabled"]:
            automatic_count += 1
        if source["expectedContentTypes"] != ["text/html"]:
            raise ContractError(f"secondary shadow sources[{index}] must accept only text/html")
        transport = _expect_keys(
            source["transport"],
            {"allowedFetchHosts", "allowedContentHosts", "maxResponseBytes", "maxRedirects", "maxItems"},
            f"secondary shadow sources[{index}].transport",
        )
        for name in ("allowedFetchHosts", "allowedContentHosts"):
            hosts = transport[name]
            if not isinstance(hosts, list) or not hosts:
                raise ContractError(f"secondary shadow sources[{index}].transport.{name} must be a non-empty array")
            if len(hosts) != len(set(hosts)):
                raise ContractError(f"secondary shadow sources[{index}].transport.{name} must not contain duplicates")
            for host_index, host in enumerate(hosts):
                _expect_hostname(host, f"secondary shadow sources[{index}].transport.{name}[{host_index}]")
        if parsed.hostname not in transport["allowedFetchHosts"]:
            raise ContractError(f"secondary shadow sources[{index}].fetchUrl host must be allowed")
        _expect_limit(transport["maxResponseBytes"], f"secondary shadow sources[{index}].transport.maxResponseBytes", 1, 16 * 1024 * 1024)
        _expect_limit(transport["maxRedirects"], f"secondary shadow sources[{index}].transport.maxRedirects", 0, 5)
        _expect_limit(transport["maxItems"], f"secondary shadow sources[{index}].transport.maxItems", 1, 100)
        keywords = source["matchKeywords"]
        if not isinstance(keywords, list) or not keywords or len(keywords) != len(set(keywords)):
            raise ContractError(f"secondary shadow sources[{index}].matchKeywords must be a unique non-empty array")
        for keyword_index, keyword in enumerate(keywords):
            _expect_string(keyword, f"secondary shadow sources[{index}].matchKeywords[{keyword_index}]")
    if automatic_count == 0:
        raise ContractError("secondary shadow config must contain at least one automatic shadow source")
    return config


def load_and_validate_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as error:
        raise ContractError(f"missing secondary shadow config: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid secondary shadow config JSON: {path}") from error


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(pairs), ""))


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._parts = [attributes.get("title") or ""]

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, _normalise_text(" ".join(self._parts))))
            self._href = None
            self._parts = []


def extract_signals(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    """Extract bounded metadata from same-site anchor text, then discard HTML."""
    parser = _LinkCollector()
    parser.feed(body)
    parser.close()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    keywords = {keyword.casefold(): keyword for keyword in source["matchKeywords"]}
    for href, title in parser.links:
        if not title:
            continue
        url = _canonical_url(urljoin(source["fetchUrl"], href))
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in source["transport"]["allowedContentHosts"]:
            continue
        title = title[:280]
        lowered = title.casefold()
        matched = [original for normalised, original in keywords.items() if normalised in lowered]
        if not matched or url in seen:
            continue
        seen.add(url)
        fingerprint = hashlib.sha256(f"{url}\n{title}".encode("utf-8")).hexdigest()
        signals.append({"url": url, "title": title, "matchedKeywords": matched, "fingerprint": fingerprint})
        if len(signals) > source["transport"]["maxItems"]:
            raise ContractError(f"secondary shadow source {source['id']} exceeds its item limit")
    return signals


def _timestamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ContractError("secondary shadow now must include a timezone")
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_timestamp(value: Any, label: str) -> str:
    text = _expect_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include a timezone")
    return text


def validate_state(state: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Reject malformed isolated state before network access or any write."""
    if state == {"sources": {}}:
        return state
    payload = _expect_keys(state, {"schemaVersion", "updatedAt", "baselineCutoffAt", "sources"}, "secondary shadow state")
    if payload["schemaVersion"] != SHADOW_STATE_SCHEMA_VERSION:
        raise ContractError(f"secondary shadow state schemaVersion must be {SHADOW_STATE_SCHEMA_VERSION}")
    _validate_timestamp(payload["updatedAt"], "secondary shadow state.updatedAt")
    _validate_timestamp(payload["baselineCutoffAt"], "secondary shadow state.baselineCutoffAt")
    if not isinstance(payload["sources"], dict):
        raise ContractError("secondary shadow state.sources must be an object")
    automatic_ids = {source["id"] for source in config["sources"] if source["enabled"]}
    if set(payload["sources"]) - automatic_ids:
        raise ContractError("secondary shadow state must not contain unknown or manual-only sources")
    for source_id, source_state in payload["sources"].items():
        source_object = _expect_keys(source_state, {"items"}, f"secondary shadow state.sources.{source_id}")
        if not isinstance(source_object["items"], dict):
            raise ContractError(f"secondary shadow state.sources.{source_id}.items must be an object")
        for url, item in source_object["items"].items():
            _expect_https_url(url, f"secondary shadow state.sources.{source_id}.items URL")
            item_object = _expect_keys(item, {"fingerprint", "lastSeenAt"}, f"secondary shadow state.sources.{source_id}.items item")
            if not isinstance(item_object["fingerprint"], str) or not HASH_RE.fullmatch(item_object["fingerprint"]):
                raise ContractError(f"secondary shadow state.sources.{source_id}.items fingerprint must be SHA-256")
            _validate_timestamp(item_object["lastSeenAt"], f"secondary shadow state.sources.{source_id}.items lastSeenAt")
    return payload


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = _timestamp(now)
    state = validate_state(state, config)
    prior_sources = state.get("sources", {})
    baseline_mode = "active" if isinstance(state.get("baselineCutoffAt"), str) and state["baselineCutoffAt"] else "seeded"
    cutoff = state.get("baselineCutoffAt") if baseline_mode == "active" else generated_at
    next_state: dict[str, Any] = {"schemaVersion": SHADOW_STATE_SCHEMA_VERSION, "updatedAt": generated_at, "baselineCutoffAt": cutoff, "sources": {}}
    runs: list[dict[str, Any]] = []
    observed: list[dict[str, Any]] = []
    for source in (item for item in config["sources"] if item["enabled"]):
        body, content_type = fetch_body(source, timeout)
        if not isinstance(body, str) or (content_type or "").split(";", 1)[0].strip().lower() not in source["expectedContentTypes"]:
            raise ContractError(f"secondary shadow source {source['id']} returned an unexpected response")
        extracted = extract_signals(source, body)
        previous = prior_sources.get(source["id"], {}).get("items", {})
        items = dict(previous)
        new_count = 0
        unchanged = 0
        for signal in extracted:
            prior = previous.get(signal["url"])
            items[signal["url"]] = {"fingerprint": signal["fingerprint"], "lastSeenAt": generated_at}
            if baseline_mode == "active" and (prior is None or prior.get("fingerprint") != signal["fingerprint"]):
                new_count += 1
                observed.append({
                    "signalId": f"{source['id']}-{signal['fingerprint'][:20]}",
                    "sourceId": source["id"],
                    "observedAt": generated_at,
                    "title": signal["title"],
                    "url": signal["url"],
                    "matchedKeywords": signal["matchedKeywords"],
                    "fingerprint": signal["fingerprint"],
                    "verificationStatus": "unverified",
                    "publicationEligible": False,
                })
            else:
                unchanged += 1
        next_state["sources"][source["id"]] = {"items": items}
        runs.append({"sourceId": source["id"], "status": "success", "extractedItems": len(extracted), "newSignals": new_count, "unchangedItems": unchanged})
    report = {
        "schemaVersion": SHADOW_REPORT_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "baseline": {"mode": baseline_mode, "cutoffAt": cutoff},
        "publicationEligible": False,
        "officialCandidateIntegration": False,
        "requireHumanOfficialVerification": True,
        "responseBodyStored": False,
        "sourceRuns": runs,
        "summary": {"sources": len(runs), "signals": len(observed)},
        "signals": observed,
    }
    return report, next_state


def collect_and_write(
    config_path: Path,
    state_path: Path,
    output_path: Path,
    timeout: float,
    *,
    now: datetime | None = None,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = bounded_request,
) -> dict[str, Any]:
    config = load_and_validate_config(config_path)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"sources": {}}
    validate_state(state, config)
    report, next_state = collect(config, state, timeout, now or datetime.now(timezone.utc), fetch_body)
    # Both writes happen only after every fetch and parse succeeds.
    write_json(output_path, report)
    write_json(state_path, next_state)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        report = collect_and_write(args.config, args.state, args.output, args.timeout)
    except (ContractError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: collected {report['summary']['signals']} unverified secondary signals ({report['baseline']['mode']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
