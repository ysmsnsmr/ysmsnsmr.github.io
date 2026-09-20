#!/usr/bin/env python3
"""Classify current public Personal Feed items with Jev without production effects."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from experiment_meta_ads_jev_ads_relevance_shadow import (
    JevRequestError,
    MAX_SOURCE_CONTEXT_CHARS,
    QUESTION_SET_VERSION,
    REQUESTED_MODEL_ID,
    build_request,
    extract_answer,
    post_jev_request,
    write_new_artifact,
)


SCHEMA_VERSION = "meta-ads-jev-production-shadow/v1"
SUPPORTED_FEED_SCHEMA = "meta-ads-personal-feed/v5"
DEFAULT_FEED = Path(__file__).resolve().parents[1] / "meta-ads-updates" / "personal-feed.json"
DEFAULT_ARTIFACT_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "artifacts" / "meta_ads_jev_production_shadow"
)
DEFAULT_LIMIT = 15
MAX_LIMIT = 50

PostJson = Callable[..., Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_feed(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    feed = json.loads(raw)
    if not isinstance(feed, dict) or feed.get("schemaVersion") != SUPPORTED_FEED_SCHEMA:
        raise ValueError("feed must use the supported Personal Feed schema")
    if not isinstance(feed.get("generatedAt"), str):
        raise ValueError("feed generatedAt must be a string")
    items = feed.get("items")
    if not isinstance(items, list):
        raise ValueError("feed items must be an array")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("feed item must be an object")
        for field in ("id", "sourceId", "title", "firstObservedAt", "presentation"):
            if field not in item:
                raise ValueError(f"feed item is missing {field}")
        if not all(isinstance(item[field], str) and item[field] for field in ("id", "sourceId", "title", "firstObservedAt")):
            raise ValueError("feed item identity fields must be non-empty strings")
        if item["id"] in seen:
            raise ValueError("feed item IDs must be unique")
        if not isinstance(item["presentation"], dict):
            raise ValueError("feed item presentation must be an object")
        seen.add(item["id"])
    return feed, hashlib.sha256(raw).hexdigest()


def _english_summary(item: dict[str, Any]) -> str:
    presentation = item.get("presentation", {})
    locales = presentation.get("locales", {}) if isinstance(presentation, dict) else {}
    english = locales.get("en", {}) if isinstance(locales, dict) else {}
    if not isinstance(english, dict):
        return ""
    fields = english.get("fields")
    if isinstance(fields, dict):
        summary = fields.get("summary")
        if isinstance(summary, dict) and summary.get("status") in {"machine", "reviewed"}:
            value = summary.get("value")
            return value[:MAX_SOURCE_CONTEXT_CHARS] if isinstance(value, str) else ""
    if english.get("status") in {"machine", "reviewed"}:
        value = english.get("summary")
        return value[:MAX_SOURCE_CONTEXT_CHARS] if isinstance(value, str) else ""
    return ""


def select_items(feed: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

    def sort_key(item: dict[str, Any]) -> tuple[str, str]:
        observed = item.get("updatedDate") or item.get("publishedDate") or item["firstObservedAt"]
        return str(observed), item["id"]

    selected = sorted(feed["items"], key=sort_key, reverse=True)[:limit]
    return [
        {
            "itemId": item["id"],
            "sourceId": item["sourceId"],
            "title": item["title"],
            "sourceContext": _english_summary(item),
        }
        for item in selected
    ]


def run_shadow(
    feed: dict[str, Any],
    feed_sha256: str,
    api_key: str,
    timeout_seconds: float,
    limit: int,
    *,
    post_json: PostJson = post_jev_request,
    generated_at: str | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in select_items(feed, limit):
        started = time.monotonic()
        result_base = {"itemId": item["itemId"], "sourceId": item["sourceId"]}
        try:
            response = post_json(build_request(item), api_key, timeout_seconds)
            answer, provider_model_id = extract_answer(response)
        except JevRequestError as error:
            results.append({**result_base, "outcome": "error", "errorCode": error.code})
            continue
        except Exception:
            results.append({**result_base, "outcome": "error", "errorCode": "transport_error"})
            continue
        results.append(
            {
                **result_base,
                "outcome": "classified",
                "adsRelevance": answer,
                "providerModelId": provider_model_id,
                "latencyMs": round((time.monotonic() - started) * 1000),
            }
        )

    classified = [value for value in results if value["outcome"] == "classified"]
    failed = [value for value in results if value["outcome"] == "error"]
    choices = Counter(value["adsRelevance"]["choice"] for value in classified)
    source_counts = Counter(value["sourceId"] for value in results)
    error_codes = Counter(value["errorCode"] for value in failed)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at or _utc_now(),
        "productionEffect": False,
        "routingEffect": False,
        "sourceFeed": {
            "schemaVersion": feed["schemaVersion"],
            "generatedAt": feed["generatedAt"],
            "sha256": feed_sha256,
            "availableItems": len(feed["items"]),
            "selectedItems": len(results),
        },
        "requestedModelId": REQUESTED_MODEL_ID,
        "questionSetVersion": QUESTION_SET_VERSION,
        "inputPolicy": {
            "sentFields": ["title", "publicEnglishSummary"],
            "maximumSourceContextChars": MAX_SOURCE_CONTEXT_CHARS,
            "rawProviderResponseStored": False,
            "credentialStored": False,
            "urlStored": False,
            "titleStored": False,
            "summaryStored": False,
        },
        "results": results,
        "summary": {
            "classified": len(classified),
            "failed": len(failed),
            "choices": dict(sorted(choices.items())),
            "sources": dict(sorted(source_counts.items())),
            "errorCodes": dict(sorted(error_codes.items())),
        },
    }


def _parse_limit(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("limit must be an integer") from error
    if not 1 <= parsed <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be between 1 and {MAX_LIMIT}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--artifact-directory", type=Path, default=DEFAULT_ARTIFACT_DIRECTORY)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--limit", type=_parse_limit, default=DEFAULT_LIMIT)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--live", action="store_true", help="explicitly allow Jev API calls")
    args = parser.parse_args()

    try:
        feed, feed_sha256 = load_feed(args.feed)
        selected = select_items(feed, args.limit)
        if not args.live:
            print(f"PASS: feed is valid; {len(selected)} item(s) selected; use --live to call Jev")
            return 0
        if not 1 <= args.timeout_seconds <= 60:
            raise ValueError("timeout-seconds must be between 1 and 60")
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            raise ValueError("TYPESAFE_API_KEY is required with --live")
        report = run_shadow(feed, feed_sha256, api_key, args.timeout_seconds, args.limit)
        path = write_new_artifact(report, args.output_name, args.artifact_directory)
    except (OSError, ValueError, json.JSONDecodeError, JevRequestError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    outcome = "PASS" if report["summary"]["failed"] == 0 else "FAIL"
    print(
        f"{outcome}: production shadow artifact written "
        f"({report['summary']['classified']} classified, {report['summary']['failed']} failed): {path}"
    )
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
