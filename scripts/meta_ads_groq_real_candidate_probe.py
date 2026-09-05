#!/usr/bin/env python3
"""Run one bilingual Groq request using one current Personal Feed candidate.

The candidate title and source context are read only for this request.  Raw
source content, the model response, exceptions, feed, and state are never
printed or persisted.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from meta_ads_personal_feed import _all_sources, extract_items, load_config
from meta_ads_personal_feed_presentation import PresentationError, request_bilingual_presentation
from meta_ads_tracker_collect import SourceFetchError, _request as bounded_request


DEFAULT_FEED = Path("meta-ads-updates/personal-feed.json")
DEFAULT_POLICY = Path("config/meta_ads_personal_feed_sources.json")
DEFAULT_SOURCE_ID = "jon-loomer-meta-ads"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _candidate(
    feed: dict[str, Any],
    source_id: str,
    require_missing: bool = False,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    values = [item for item in feed.get("items", []) if isinstance(item, dict) and item.get("sourceId") == source_id]
    if candidate_id:
        values = [item for item in values if item.get("id") == candidate_id]
    if require_missing:
        values = [
            item
            for item in values
            if item.get("presentation", {}).get("locales", {}).get("en", {}).get("status") == "missing"
        ]
    if not values:
        raise ValueError("no current candidate for source")
    values.sort(key=lambda item: (item.get("updatedDate") or item.get("publishedDate") or "", item.get("id", "")), reverse=True)
    selected = values[0]
    if not isinstance(selected.get("url"), str) or not isinstance(selected.get("title"), str):
        raise ValueError("candidate lacks safe title or URL")
    return selected


def _source(config: dict[str, Any], source_id: str) -> dict[str, Any]:
    for source in _all_sources(config):
        if source.get("id") == source_id:
            return source
    raise ValueError("source is not configured")


def run_probe(
    *,
    api_key: str,
    model: str,
    source_id: str,
    feed_path: Path = DEFAULT_FEED,
    config_path: Path = DEFAULT_POLICY,
    timeout: float = 30.0,
    max_input_chars: int | None = None,
    require_missing: bool = False,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    if not api_key.strip():
        raise PresentationError("api_key_unavailable")
    config = load_config(config_path)
    feed = _read_json(feed_path)
    candidate = _candidate(
        feed,
        source_id,
        require_missing=require_missing,
        candidate_id=candidate_id,
    )
    source = _source(config, source_id)
    body, _content_type = bounded_request(source, timeout)
    parsed = extract_items(source, body)
    matching = next((item for item in parsed if item.get("url") == candidate["url"]), None)
    if not isinstance(matching, dict) or not isinstance(matching.get("sourceContext"), str):
        raise ValueError("candidate was not present in the current source response")
    policy = config["policies"]["bilingualPresentation"]
    # Exactly one request: retries are disabled for this diagnostic.
    source_context = matching["sourceContext"]
    if max_input_chars is not None:
        source_context = source_context[:max_input_chars] if max_input_chars > 0 else ""
    generated = request_bilingual_presentation(
        api_key=api_key,
        model=model,
        title=matching["title"],
        source_context=source_context,
        short_headline_max_chars=policy["shortHeadlineMaxChars"],
        summary_max_chars=policy["summaryMaxChars"],
        timeout=timeout,
        max_attempts=1,
    )
    # Keep the result deliberately minimal; generated text is discarded.
    return {
        "sourceId": source_id,
        "candidateFound": True,
        "contextLimit": max_input_chars if max_input_chars is not None else policy["maxInputChars"],
        "status": "success",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--max-input-chars", type=int, choices=(0, 1000, 2000, 4000))
    parser.add_argument("--require-missing", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    model = os.environ.get("META_ADS_PERSONAL_FEED_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"
    try:
        result = run_probe(
            api_key=os.environ.get("GROQ_API_KEY", ""),
            model=model,
            source_id=args.source_id,
            timeout=args.timeout,
            max_input_chars=args.max_input_chars,
            require_missing=args.require_missing,
            candidate_id=args.candidate_id,
        )
    except PresentationError as error:
        provider_type = error.provider_error_type or "none"
        provider_code = error.provider_error_code or "none"
        print(
            "GROQ_REAL_CANDIDATE_PROBE: "
            f"source_id={args.source_id} context_limit={args.max_input_chars if args.max_input_chars is not None else 'policy'} "
            f"model={model} status=failed "
            f"failure_code={error.code} error_type={provider_type} "
            f"error_code={provider_code} attempts={error.attempts}"
        )
        return 1
    except SourceFetchError as error:
        print(
            "GROQ_REAL_CANDIDATE_PROBE: "
            f"source_id={args.source_id} model={model} status=failed "
            f"failure_code=source_fetch_{error.reason}"
        )
        return 1
    except (OSError, ValueError):
        # Do not print exception text: it could contain source content.
        print(
            "GROQ_REAL_CANDIDATE_PROBE: "
            f"source_id={args.source_id} context_limit={args.max_input_chars if args.max_input_chars is not None else 'policy'} "
            f"model={model} status=failed failure_code=local_error"
        )
        return 1
    print(
        "GROQ_REAL_CANDIDATE_PROBE: "
        f"source_id={result['sourceId']} context_limit={result['contextLimit']} model={model} "
        f"candidate_found={str(result['candidateFound']).lower()} status={result['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
