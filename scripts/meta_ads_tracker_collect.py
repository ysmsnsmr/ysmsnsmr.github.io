#!/usr/bin/env python3
"""Collect official Meta Ads changes without persisting raw source responses."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_publication import CANDIDATE_SCHEMA_VERSION, validate_candidate, write_json


USER_AGENT = "ysmsnsmr-meta-ads-tracker/1.0 (+https://ysmsnsmr.github.io/meta-ads-updates/)"
MAX_SOURCE_CONTEXT = 3500


def _request(url: str, timeout: float) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        return response.read().decode("utf-8", errors="replace"), content_type


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


def _item_id(source_id: str, key: str) -> str:
    return f"{source_id}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def _base_item(source_id: str, change_type: str, title: str, url: str, announced: str | None, context: str) -> dict[str, Any]:
    return {
        "id": _item_id(source_id, url),
        "changeType": change_type,
        "sourceId": source_id,
        "title": title or "公式更新（タイトル未記載）",
        "officialUrl": url,
        "priority": "standard",
        "announcementDate": {"status": "stated", "value": announced} if announced else {"status": "not_stated", "value": None},
        "effectiveDate": {"status": "not_stated", "value": None},
        "rollout": {"status": "not_stated", "value": None},
        "targets": {"status": "not_stated", "value": None},
        "businessImpact": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "action": {"status": "not_stated", "summary": None, "assessmentSource": None},
        "reviewStatus": "pending",
        "sourceContext": context[:MAX_SOURCE_CONTEXT],
    }


def _parse_rss(body: str, source_id: str) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    items: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "item":
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in node}
        url = fields.get("link", "").strip()
        if not url.startswith("https://"):
            continue
        title = _strip_html(fields.get("title", ""))
        context = _strip_html(fields.get("encoded", "") or fields.get("description", ""))
        announced = _date_from_value(fields.get("pubDate"))
        fingerprint = _fingerprint(url, title, context)
        item = _base_item(source_id, "new_url", title, url, announced, context)
        item["_stateKey"] = url
        item["_fingerprint"] = fingerprint
        items.append(item)
    return items


def _parse_sdk(body: str, source_id: str) -> list[dict[str, Any]]:
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
        title = _strip_html(str(release.get("name") or tag))
        context = _strip_html(str(release.get("body") or ""))
        announced = _date_from_value(str(release.get("published_at") or release.get("created_at") or ""))
        item = _base_item(source_id, "sdk_release", title, url, announced, context)
        item["id"] = _item_id(source_id, tag)
        item["_stateKey"] = tag
        item["_fingerprint"] = _fingerprint(tag, title, context)
        items.append(item)
    return items


def _week(today: date) -> dict[str, str]:
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return {"startDate": start.isoformat(), "endDate": end.isoformat(), "label": f"{start.isoformat()}〜{end.isoformat()}"}


def collect(
    config: dict[str, Any],
    state: dict[str, Any],
    timeout: float,
    now: datetime,
    fetch_body: Callable[[str, float], tuple[str, str]] = _request,
) -> tuple[dict[str, Any], dict[str, Any]]:
    next_state = {"schemaVersion": "meta-ads-tracker-state/v1", "updatedAt": now.isoformat().replace("+00:00", "Z"), "sources": {}}
    changes: list[dict[str, Any]] = []
    for source in config["sources"]:
        if not source["enabled"] or source["access"] != "public":
            continue
        body, _content_type = fetch_body(source["fetchUrl"], timeout)
        parsed = _parse_rss(body, source["id"]) if source["kind"] == "product_news" else _parse_sdk(body, source["id"])
        previous = state.get("sources", {}).get(source["id"], {}).get("items", {})
        current: dict[str, Any] = dict(previous)
        for item in parsed:
            key = item.pop("_stateKey")
            fingerprint = item.pop("_fingerprint")
            prior = previous.get(key)
            change_type = item["changeType"]
            if prior is None:
                change_type = "sdk_release" if source["kind"] == "sdk_release" else "new_url"
            elif prior.get("fingerprint") != fingerprint:
                change_type = "sdk_release" if source["kind"] == "sdk_release" else "content_changed"
            current[key] = {"fingerprint": fingerprint, "lastSeenAt": next_state["updatedAt"]}
            if prior is None or prior.get("fingerprint") != fingerprint:
                item["changeType"] = change_type
                changes.append(item)
        next_state["sources"][source["id"]] = {"items": current}
    candidate = {
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "generatedAt": next_state["updatedAt"],
        "week": _week(now.date()),
        "items": changes,
    }
    validate_candidate(candidate, config)
    return candidate, next_state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/meta_ads_official_sources.json"))
    parser.add_argument("--state", type=Path, default=Path("data/meta_ads_tracker_state.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        config = load_and_validate_source_config(args.config)
        state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {"sources": {}}
        candidate, next_state = collect(config, state, args.timeout, datetime.now(timezone.utc).replace(microsecond=0))
        write_json(args.output, candidate)
        write_json(args.state, next_state)
    except (ContractError, OSError, ValueError, ET.ParseError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: collected {len(candidate['items'])} changed official items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
