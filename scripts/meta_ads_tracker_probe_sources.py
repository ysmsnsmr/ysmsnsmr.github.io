#!/usr/bin/env python3
"""Probe official Meta Ads tracker sources without retaining response bodies."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from meta_ads_tracker_contract import ContractError, DEFAULT_SOURCE_CONFIG, load_and_validate_source_config


USER_AGENT = "ysmsnsmr-meta-ads-source-probe/1.0 (+https://github.com/ysmsnsmr/ysmsnsmr.github.io)"
RequestHeaders = Callable[[str, str, float], tuple[int, str, dict[str, str]]]


def request_headers(url: str, method: str, timeout: float) -> tuple[int, str, dict[str, str]]:
    """Request only metadata; GET fallback uses a one-byte range and discards it."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, application/json, text/html;q=0.9, */*;q=0.1",
    }
    if method == "GET":
        headers["Range"] = "bytes=0-0"
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.geturl(), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        return error.code, error.geturl(), dict(error.headers.items()) if error.headers else {}


def _normalise_content_type(headers: dict[str, str]) -> str:
    return next(
        (
            value.split(";", 1)[0].strip().lower()
            for key, value in headers.items()
            if key.lower() == "content-type"
        ),
        "",
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def _matches_expected_content_type(content_type: str, expected_content_types: list[str]) -> bool:
    return any(content_type == expected or content_type.startswith(f"{expected}+") for expected in expected_content_types)


def probe_source(source: dict[str, Any], timeout: float, fetch_headers: RequestHeaders = request_headers) -> dict[str, Any]:
    """Return header-only reachability information for one configured source."""
    requested_method = "HEAD"
    try:
        status, final_url, headers = fetch_headers(source["fetchUrl"], requested_method, timeout)
        if status == 405:
            requested_method = "GET"
            status, final_url, headers = fetch_headers(source["fetchUrl"], requested_method, timeout)
    except (OSError, urllib.error.URLError) as error:
        requires_authentication = source["access"] == "login_required"
        return {
            "id": source["id"],
            "requestedMethod": requested_method,
            "reachable": False,
            "statusCode": None,
            "finalUrl": None,
            "contentType": None,
            "etag": None,
            "lastModified": None,
            "requiresAuthentication": requires_authentication,
            "publicationAction": (
                "disabled_auth_required" if requires_authentication else "keep_published_content_unchanged"
            ),
            "error": str(error),
        }

    content_type = _normalise_content_type(headers)
    expected_content_type = _matches_expected_content_type(content_type, source["expectedContentTypes"])
    reachable = 200 <= status < 300 and expected_content_type
    requires_authentication = source["access"] == "login_required" or "/login" in final_url.lower()
    if source["access"] == "login_required":
        publication_action = "disabled_auth_required"
    elif reachable:
        publication_action = "eligible_for_future_monitoring"
    else:
        publication_action = "keep_published_content_unchanged"

    return {
        "id": source["id"],
        "requestedMethod": requested_method,
        "reachable": reachable,
        "statusCode": status,
        "finalUrl": final_url,
        "contentType": content_type or None,
        "etag": _header(headers, "ETag"),
        "lastModified": _header(headers, "Last-Modified"),
        "requiresAuthentication": requires_authentication,
        "publicationAction": publication_action,
        "error": None if reachable else "unexpected_status_or_content_type",
    }


def probe_sources(config: dict[str, Any], timeout: float, fetch_headers: RequestHeaders = request_headers) -> dict[str, Any]:
    results = [probe_source(source, timeout, fetch_headers) for source in config["sources"]]
    return {
        "schemaVersion": "meta-ads-official-source-probe/v1",
        "probedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "responseBodyStored": False,
        "sources": results,
        "summary": {
            "eligibleSourceIds": [
                result["id"] for result in results if result["publicationAction"] == "eligible_for_future_monitoring"
            ],
            "disabledAuthenticationSourceIds": [
                result["id"] for result in results if result["publicationAction"] == "disabled_auth_required"
            ],
            "failedSourceIds": [result["id"] for result in results if not result["reachable"]],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, help="Optional local JSON report path; response bodies are never written.")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    try:
        report = probe_sources(load_and_validate_source_config(args.config), args.timeout)
    except ContractError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
