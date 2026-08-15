#!/usr/bin/env python3
"""Create evidence-bound Japanese review drafts from an immutable weekly artifact."""

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

from meta_ads_tracker_publication import load_json, validate_weekly_candidate, write_json


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OUTPUT_SCHEMA_VERSION = "meta-ads-tracker-groq-review/v2"
FACT_FIELDS = ("effectiveDate", "rollout", "targets")


def _normalise(value: str) -> str:
    return " ".join(value.split())


def _schema_error(value: Any, source_text: str) -> str:
    if not isinstance(value, dict) or set(value) != {"summaryJa", "summaryEvidence", *FACT_FIELDS}:
        return "root_shape"
    if not isinstance(value["summaryJa"], str) or not value["summaryJa"].strip():
        return "summary_type"
    if not isinstance(value["summaryEvidence"], str) or not value["summaryEvidence"].strip():
        return "summary_evidence"
    for key in FACT_FIELDS:
        fact = value[key]
        if not isinstance(fact, dict) or set(fact) != {"value", "evidenceExcerpt"}:
            return f"{key}_shape"
        if fact["value"] is None:
            if fact["evidenceExcerpt"] is not None:
                return f"{key}_unexpected_evidence"
        elif not isinstance(fact["value"], str) or not fact["value"].strip():
            return f"{key}_value"
        elif not isinstance(fact["evidenceExcerpt"], str) or not fact["evidenceExcerpt"].strip():
            return f"{key}_evidence"
    normalised_source = _normalise(source_text)
    evidence_values = [value["summaryEvidence"], *(value[key]["evidenceExcerpt"] for key in FACT_FIELDS)]
    for evidence in evidence_values:
        if evidence is not None and (_normalise(evidence) not in normalised_source or len(evidence) > 400):
            return "evidence_not_in_source"
    return ""


def _prompt(item: dict[str, Any]) -> list[dict[str, str]]:
    source_text = f"{item['title']}\n{item.get('sourceContext') or ''}".strip()
    return [
        {
            "role": "system",
            "content": (
                "あなたはMeta広告公式発表の事実抽出補助です。入力本文に明記された事実だけを抽出し、"
                "短い日本語要約を作成してください。適用日、rollout、対象、業務影響、対応要否を推測しません。"
                "evidenceExcerptは入力からの完全一致抜粋にし、明記がなければvalueとevidenceExcerptをnullにします。"
                "業務影響や対応判断は出力しません。指定JSONだけを返してください。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "officialUrl": item["officialUrl"],
                    "sourceText": source_text,
                    "outputContract": {
                        "summaryJa": "入力に忠実な短い日本語要約",
                        "summaryEvidence": "要約根拠となる入力内の完全一致抜粋（400文字以内）",
                        "effectiveDate": {"value": "本文に明記された値またはnull", "evidenceExcerpt": "完全一致抜粋またはnull"},
                        "rollout": {"value": "本文に明記された値またはnull", "evidenceExcerpt": "完全一致抜粋またはnull"},
                        "targets": {"value": "本文に明記された値またはnull", "evidenceExcerpt": "完全一致抜粋またはnull"},
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
        "max_tokens": 700,
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
    source_text = f"{item['title']}\n{item.get('sourceContext') or ''}".strip()
    error = _schema_error(value, source_text)
    if error:
        raise ValueError(f"Groq draft violates evidence contract: {error}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        weekly = load_json(args.input)
        validate_weekly_candidate(weekly)
        if weekly["items"]:
            api_key = os.environ.get("GROQ_API_KEY", "").strip()
            if not api_key:
                raise ValueError("GROQ_API_KEY is required when weekly events need review drafts")
        else:
            api_key = ""
        drafts: list[dict[str, Any]] = []
        for item in weekly["items"]:
            draft = request_draft(api_key, args.model, item, args.timeout)
            drafts.append(
                {
                    "eventId": item["eventId"],
                    "revision": item["revision"],
                    "sourceFingerprint": item["sourceFingerprint"],
                    "originCandidateHash": item["originCandidateHash"],
                    "weeklyHash": weekly["weeklyHash"],
                    "officialUrl": item["officialUrl"],
                    "draft": draft,
                }
            )
            time.sleep(0.1)
        output = {
            "schemaVersion": OUTPUT_SCHEMA_VERSION,
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "weeklyHash": weekly["weeklyHash"],
            "model": args.model,
            "items": drafts,
        }
        write_json(args.output, output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: generated {len(output['items'])} evidence-bound review drafts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
