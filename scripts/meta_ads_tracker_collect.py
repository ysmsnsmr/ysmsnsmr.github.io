#!/usr/bin/env python3
"""Collect official changes; the first complete run seeds a zero-change baseline."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from meta_ads_tracker_contract import (
    ContractError,
    DEFAULT_SOURCE_GOVERNANCE,
    governed_automated_sources,
    load_and_validate_source_config,
    load_and_validate_source_governance,
)
from meta_ads_tracker_publication import (
    CANDIDATE_SCHEMA_VERSION,
    KUALA_LUMPUR,
    canonical_hash,
    make_event_id,
    make_subject_id,
    validate_candidate,
    write_json,
)


USER_AGENT = "ysmsnsmr-meta-ads-tracker/1.0 (+https://ysmsnsmr.github.io/meta-ads-updates/)"
MAX_SOURCE_CONTEXT = 3500
STATE_SCHEMA_VERSION = "meta-ads-tracker-state/v3"
READ_CHUNK_SIZE = 64 * 1024
MAX_FETCH_ATTEMPTS = 2
RETRYABLE_HTTP_STATUSES = frozenset({408, 415, 429, 500, 502, 503, 504})
MAX_RETRY_DELAY_SECONDS = 30


class SourceFetchError(ContractError):
    """Safe direct-source failure metadata; never retain a response body."""

    def __init__(self, source_id: str, reason: str, attempts: int) -> None:
        self.source_id = source_id
        self.reason = reason
        self.attempts = attempts
        super().__init__(f"source {source_id} fetch failed ({reason}; attempts={attempts})")


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow only a bounded number of HTTPS redirects within a source allowlist."""

    # Run before urllib's default redirect handler, so an unvalidated redirect
    # cannot be followed by a second handler in the same opener.
    handler_order = 100

    def __init__(self, source: dict[str, Any], resolver: Callable[..., Any]) -> None:
        super().__init__()
        self.source = source
        self.resolver = resolver
        self.redirects = 0

    def redirect_request(self, request: Any, fp: Any, code: int, message: str, headers: Any, newurl: str) -> Any:
        if self.redirects >= self.source["transport"]["maxRedirects"]:
            raise ContractError(f"source {self.source['id']} exceeded its redirect limit")
        destination = urljoin(request.full_url, newurl)
        _validate_transport_url(destination, self.source, self.resolver)
        self.redirects += 1
        return super().redirect_request(request, fp, code, message, headers, destination)


def _validate_transport_url(
    url: str,
    source: dict[str, Any],
    resolver: Callable[..., Any] | None = None,
) -> None:
    """Reject destinations that are outside a configured public HTTPS boundary."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ContractError(f"source {source['id']} must use an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ContractError(f"source {source['id']} URL must not contain credentials")
    try:
        port = parsed.port
    except ValueError as error:
        raise ContractError(f"source {source['id']} URL has an invalid port") from error
    if port not in {None, 443}:
        raise ContractError(f"source {source['id']} URL must use the standard HTTPS port")
    hostname = parsed.hostname.lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ContractError(f"source {source['id']} URL must not use an IP address")
    if hostname not in source["transport"]["allowedFetchHosts"]:
        raise ContractError(f"source {source['id']} URL host is not allowed")
    try:
        resolved = (resolver or socket.getaddrinfo)(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ContractError(f"source {source['id']} hostname could not be resolved") from error
    if not resolved:
        raise ContractError(f"source {source['id']} hostname did not resolve to an address")
    for record in resolved:
        address = record[4][0]
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError as error:
            raise ContractError(f"source {source['id']} hostname resolved to an invalid address") from error
        if not ip_address.is_global:
            raise ContractError(f"source {source['id']} hostname resolved to a non-global address")


def _normalise_content_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _read_limited(response: Any, maximum_bytes: int, source_id: str) -> bytes:
    header = response.headers.get("Content-Length")
    if header:
        try:
            declared_size = int(header)
        except ValueError as error:
            raise ContractError(f"source {source_id} sent an invalid Content-Length") from error
        if declared_size < 0 or declared_size > maximum_bytes:
            raise ContractError(f"source {source_id} response exceeds its byte limit")

    body = bytearray()
    while True:
        remaining = maximum_bytes - len(body)
        chunk = response.read(min(READ_CHUNK_SIZE, remaining + 1))
        if not chunk:
            return bytes(body)
        if len(chunk) > remaining:
            raise ContractError(f"source {source_id} response exceeds its byte limit")
        body.extend(chunk)


def _retry_delay(headers: Any, attempt: int) -> float:
    """Return a bounded retry delay without exposing response content."""
    value = headers.get("Retry-After") if headers is not None else None
    if isinstance(value, str) and value.strip().isdigit():
        return min(float(value.strip()), MAX_RETRY_DELAY_SECONDS)
    return min(float(2 ** (attempt - 1)), MAX_RETRY_DELAY_SECONDS)


def _request(
    source: dict[str, Any],
    timeout: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Fetch an enabled source without proxies, raw persistence, or unbounded reads."""
    _validate_transport_url(source["fetchUrl"], source)
    request = urllib.request.Request(
        source["fetchUrl"],
        headers={"User-Agent": USER_AGENT, "Accept": ", ".join(source["expectedContentTypes"])},
    )
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        redirect_handler = _RestrictedRedirectHandler(source, socket.getaddrinfo)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), redirect_handler)
        try:
            with opener.open(request, timeout=timeout) as response:
                _validate_transport_url(response.geturl(), source)
                content_type = _normalise_content_type(response.headers.get("Content-Type"))
                if content_type not in source["expectedContentTypes"]:
                    raise ContractError(f"source {source['id']} returned an unexpected Content-Type")
                body = _read_limited(response, source["transport"]["maxResponseBytes"], source["id"])
                return body.decode("utf-8", errors="replace"), content_type
        except urllib.error.HTTPError as error:
            reason = f"http_status={error.code}"
            if error.code not in RETRYABLE_HTTP_STATUSES or attempt == MAX_FETCH_ATTEMPTS:
                raise SourceFetchError(source["id"], reason, attempt) from error
            sleep(_retry_delay(error.headers, attempt))
        except urllib.error.URLError as error:
            if attempt == MAX_FETCH_ATTEMPTS:
                raise SourceFetchError(source["id"], "network_error", attempt) from error
            sleep(_retry_delay(None, attempt))
    raise AssertionError("bounded source request exhausted without a result")


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _date_from_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return value[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value) else None


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _parse_rss(body: str, maximum_items: int) -> list[dict[str, Any]]:
    root = SafeElementTree.fromstring(body)
    items: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "item":
            continue
        if len(items) >= maximum_items:
            raise ContractError("RSS response exceeds its item limit")
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in node}
        url = fields.get("link", "").strip()
        if not url.startswith("https://"):
            continue
        title = _strip_html(fields.get("title", ""))
        context = _strip_html(fields.get("encoded", "") or fields.get("description", ""))
        items.append(
            {
                "stateKey": url,
                "fingerprint": _fingerprint(url, title, context),
                "title": title,
                "url": url,
                "announced": _date_from_value(fields.get("pubDate")),
                "context": context,
            }
        )
    return items


def _parse_sdk(body: str, maximum_items: int) -> list[dict[str, Any]]:
    payload = json.loads(body)
    if not isinstance(payload, list):
        raise ContractError("SDK release response must be an array")
    items: list[dict[str, Any]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        url = str(release.get("html_url") or "").strip()
        if not tag or not url.startswith("https://"):
            continue
        if len(items) >= maximum_items:
            raise ContractError("SDK release response exceeds its item limit")
        items.append(
            {
                "stateKey": tag,
                "fingerprint": _fingerprint(tag, _strip_html(str(release.get("name") or tag)), _strip_html(str(release.get("body") or ""))),
                "title": _strip_html(str(release.get("name") or tag)),
                "url": url,
                "announced": _date_from_value(str(release.get("published_at") or release.get("created_at") or "")),
                "context": _strip_html(str(release.get("body") or "")),
            }
        )
    return items


def _week(today: date) -> dict[str, str]:
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return {"startDate": start.isoformat(), "endDate": end.isoformat(), "label": f"{start.isoformat()}〜{end.isoformat()}"}


def _event(source_id: str, source_kind: str, raw: dict[str, Any], change_type: str, detected_at: str) -> dict[str, Any]:
    subject_id = make_subject_id(source_id, raw["url"])
    fingerprint = raw["fingerprint"]
    event_id = make_event_id(source_id, subject_id, fingerprint)
    announced = raw["announced"]
    return {
        "id": event_id,
        "eventId": event_id,
        "subjectId": subject_id,
        "revision": fingerprint,
        "sourceFingerprint": fingerprint,
        "detectedAt": detected_at,
        "changeType": "sdk_release" if source_kind == "sdk_release" else change_type,
        "sourceId": source_id,
        "title": raw["title"] or "公式更新（タイトル未記載）",
        "officialUrl": raw["url"],
        "priority": "standard",
        "announcementDate": {"status": "stated", "value": announced} if announced else {"status": "not_stated", "value": None},
        "effectiveDate": {"status": "not_stated", "value": None},
        "rollout": {"status": "not_stated", "value": None},
        "targets": {"status": "not_stated", "value": None},
        "businessImpact": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "action": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "reviewStatus": "pending",
        "sourceContext": raw["context"][:MAX_SOURCE_CONTEXT],
    }


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = _request,
    governance: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if now.tzinfo is None:
        raise ContractError("collector now must include a timezone")
    generated_at = now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing_cutoff = state.get("baselineCutoffAt")
    baseline_mode = "active" if isinstance(existing_cutoff, str) and existing_cutoff else "seeded"
    baseline_cutoff = existing_cutoff if baseline_mode == "active" else generated_at
    epoch_id = f"epoch-{now.astimezone(timezone.utc).strftime('%Y%m%dt%H%M%sz')}"
    next_state = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "updatedAt": generated_at,
        "baselineCutoffAt": baseline_cutoff,
        "sources": {},
    }
    changes: list[dict[str, Any]] = []
    source_runs: list[dict[str, Any]] = []
    governance = governance or load_and_validate_source_governance(source_config=config)
    automated_sources = governed_automated_sources(config, governance, now.astimezone(KUALA_LUMPUR).date())

    for source in automated_sources:
        body, _content_type = fetch_body(source, timeout)
        parsed = (
            _parse_rss(body, source["transport"]["maxItems"])
            if source["kind"] == "product_news"
            else _parse_sdk(body, source["transport"]["maxItems"])
        )
        previous = state.get("sources", {}).get(source["id"], {}).get("items", {})
        current: dict[str, Any] = dict(previous)
        seen: set[str] = set()
        counts = {"parsedItems": len(parsed), "newEvents": 0, "changedEvents": 0, "unchangedItems": 0, "tombstonedItems": 0}
        for raw in parsed:
            key = raw["stateKey"]
            seen.add(key)
            fingerprint = raw["fingerprint"]
            prior = previous.get(key)
            current[key] = {"fingerprint": fingerprint, "lastSeenAt": generated_at}
            if baseline_mode == "seeded":
                continue
            if prior is None:
                changes.append(_event(source["id"], source["kind"], raw, "new_url", generated_at))
                counts["newEvents"] += 1
            elif prior.get("fingerprint") != fingerprint:
                changes.append(_event(source["id"], source["kind"], raw, "content_changed", generated_at))
                counts["changedEvents"] += 1
            else:
                counts["unchangedItems"] += 1
        for key, prior in previous.items():
            if key not in seen:
                current[key] = {**prior, "tombstonedAt": prior.get("tombstonedAt") or generated_at}
                counts["tombstonedItems"] += 1
        next_state["sources"][source["id"]] = {"items": current}
        source_runs.append({"sourceId": source["id"], "status": "success", "startedAt": generated_at, "completedAt": generated_at, **counts})

    summary = {key: sum(run[key] for run in source_runs) for key in ("parsedItems", "newEvents", "changedEvents", "unchangedItems", "tombstonedItems")}

    candidate = {
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "candidateHash": "",
        "generatedAt": generated_at,
        "baseline": {"mode": baseline_mode, "cutoffAt": baseline_cutoff},
        "week": _week(now.astimezone(KUALA_LUMPUR).date()),
        "processingEpoch": {"id": epoch_id, "startedAt": generated_at, "completedAt": generated_at, "status": "completed"},
        "sourceRuns": source_runs,
        "summary": summary,
        "items": changes,
    }
    candidate["candidateHash"] = canonical_hash(candidate, "candidateHash")
    validate_candidate(candidate, config)
    return candidate, next_state


def collect_and_write(
    config_path: Path,
    state_path: Path,
    output_path: Path,
    timeout: float,
    *,
    governance_path: Path = DEFAULT_SOURCE_GOVERNANCE,
    now: datetime | None = None,
    fetch_body: Callable[[dict[str, Any], float], tuple[str, str]] = _request,
) -> dict[str, Any]:
    """Collect completely before atomically replacing either persisted output file."""
    config = load_and_validate_source_config(config_path)
    governance = load_and_validate_source_governance(governance_path, config)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"sources": {}}
    candidate, next_state = collect(
        config,
        state,
        timeout,
        now or datetime.now(timezone.utc).replace(microsecond=0),
        fetch_body,
        governance,
    )
    write_json(output_path, candidate)
    write_json(state_path, next_state)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/meta_ads_official_sources.json"))
    parser.add_argument("--governance", type=Path, default=DEFAULT_SOURCE_GOVERNANCE)
    parser.add_argument("--state", type=Path, default=Path("data/meta_ads_tracker_state.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        candidate = collect_and_write(
            args.config,
            args.state,
            args.output,
            args.timeout,
            governance_path=args.governance,
        )
    except (ContractError, DefusedXmlException, ET.ParseError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: collected {len(candidate['items'])} changed official events ({candidate['baseline']['mode']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
