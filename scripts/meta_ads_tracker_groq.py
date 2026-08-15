#!/usr/bin/env python3
"""Create review-only Japanese drafts for Meta Ads candidates with Groq.

The output is never a public report. Every field remains subject to a human
decision and the publication validator before it can reach Pages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meta_ads_tracker_publication import load_json, validate_candidate, write_json


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OUTPUT_SCHEMA_VERSION = "meta-ads-tracker-groq/v1"
ACTION_STATUSES = {"action_required", "review_required", "not_required", "not_stated"}


def _schema_error(value: Any) -> str:
    if not isinstance(value, dict) or set(value) != {"businessImpactSummary", "actionStatus", "actionSummary", "effectiveDate", "rollout", "targets"}:
        return "root_shape"
    if not isinstance(value["businessImpactSummary"], str) or not isinstance(value["actionSummary"], str):
        return "summary_type"
    if value["actionStatus"] not in ACTION_STATUSES:
        return "action_status"
    for key in ("effectiveDate", "rollout", "targets"):
        if value[key] is not None and not isinstance(value[key], str):
            return f"{key}_type"
    return ""


def _prompt(item: dict[str, Any]) -> list[dict[str, str]]:
    context = item.get("sourceContext") or "(本文抜粋なし)"
    return [
        {
            "role": "system",
            "content": (
                "あなたはMeta広告公式発表のレビュー補助です。入力は公式URLと本文抜粋です。"
                "本文に明記されない適用日、rollout、対象、業務影響を推測しないでください。"
                "不明な値はnullまたはnot_statedにしてください。出力は指定JSONだけです。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "title": item["title"],
                    "officialUrl": item["officialUrl"],
                    "changeType": item["changeType"],
                    "sourceTextExcerpt": context,
                    "outputContract": {
                        "businessImpactSummary": "日本語の補助案。推測できない場合は空文字列。",
                        "actionStatus": sorted(ACTION_STATUSES),
                        "actionSummary": "日本語の補助案。根拠がなければ空文字列。",
                        "effectiveDate": "本文に明記されたYYYY-MM-DDのみ、それ以外はnull",
                        "rollout": "本文に明記された事実のみ、それ以外はnull",
                        "targets": "本文に明記された対象のみ、それ以外はnull",
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def request_draft(api_key: str, model: str, item: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": _prompt(item),
        "temperature": 0,
        "max_tokens": 500,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "ysmsnsmr-meta-ads-tracker/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read(50000).decode("utf-8", errors="replace"))
    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Groq response content is empty")
    value = json.loads(content)
    error = _schema_error(value)
    if error:
        raise ValueError(f"Groq draft violates output contract: {error}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        candidate = load_json(args.input)
        validate_candidate(candidate)
        items = candidate["items"]
        if not items:
            drafts: list[dict[str, Any]] = []
        else:
            api_key = os.environ.get("GROQ_API_KEY", "").strip()
            if not api_key:
                raise ValueError("GROQ_API_KEY is required when changed items need Groq drafts")
            drafts = []
            for item in items:
                draft = request_draft(api_key, args.model, item, args.timeout)
                drafts.append({"itemId": item["id"], **draft})
                time.sleep(0.1)
        output = {
            "schemaVersion": OUTPUT_SCHEMA_VERSION,
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "candidateGeneratedAt": candidate["generatedAt"],
            "model": args.model,
            "items": drafts,
        }
        write_json(args.output, output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: generated {len(output['items'])} review-only Groq drafts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
