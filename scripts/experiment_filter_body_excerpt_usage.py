#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "phase2d.body_excerpt_usage_filter.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
ARTICLE_BODY = "article_body"
RSS_FALLBACK = "rss_fallback"
USE_BODY = "use_body"
RSS_ONLY = "rss_only"
SELECTED_WITH_BODY = "with_body_excerpt"
POLICY_VALUES = {USE_BODY, RSS_ONLY, RSS_FALLBACK}
SELECTED_CONTEXT_VALUES = {RSS_ONLY, SELECTED_WITH_BODY}
FORBIDDEN_PATTERNS = [
    "gsk_",
    "GROQ_API_KEY",
    "Authorization",
    "Bearer",
    "api_key",
]

CRIME_OR_COURT_PHRASES = [
    "court",
    "charged",
    "pleaded",
    "remanded",
    "jail",
    "caning",
    "lawsuit",
    "saman",
    "mahkamah",
    "arrested",
    "police arrested",
    "drug",
    "dadah",
    "molest",
    "sexual misconduct",
    "macc",
    "sprm",
    "probe",
]
INCIDENT_PHRASES = [
    "killed",
    "dies",
    "died",
    "dead",
    "fatal",
    "accident",
    "crash",
    "collision",
    "drowned",
    "lemas",
    "feared drowned",
    "search underway",
]
MARKET_OR_OVERSEAS_PHRASES = [
    "business as usual",
    "counterfeit",
    "job market",
    "work culture",
    "shepherd job",
    "hanoi",
    "vietnam",
    "ringgit",
    "bursa",
    "stock market",
    "forex",
    "currency",
    "greenback",
    "earnings",
    "shares",
    "equities",
]
COST_OR_SUBSIDY_PHRASES = [
    "ron95",
    "ron97",
    "diesel",
    "fuel prices",
    "petrol",
    "price",
    "prices",
    "tariff",
    "fare",
    "subsidy",
    "subsidised",
    "budi95",
    "rahmah",
    "kos sara hidup",
    "cost of living",
]
PUBLIC_SERVICE_PHRASES = [
    "ministry",
    "mof",
    "jpj",
    "myjpj",
    "mykad",
    "immigration",
    "application",
    "counter",
    "public service",
    "government",
    "dbkl",
    "mbpj",
    "mcmc",
]
TRANSPORT_OR_INFRA_PHRASES = [
    "road",
    "jalan",
    "traffic",
    "closure",
    "closed",
    "train",
    "bus",
    "mrt",
    "lrt",
    "ktmb",
    "public transport",
    "airport",
    "stadium",
    "facilities",
    "venue",
    "venues",
    "infrastructure",
    "concert",
]
CONSUMER_OR_CROSSBORDER_SERVICE_PHRASES = [
    "payment",
    "payments",
    "paypal",
    "wechat pay",
    "alipay",
    "qr-code",
    "qr code",
    "e-wallet",
    "ewallet",
    "bank card",
    "foreign bank cards",
    "card",
    "mobile payments",
    "ecommerce",
    "e-commerce",
    "platform",
    "app",
]
VEHICLE_OR_TRANSPORT_SERVICE_PHRASES = [
    "vehicle",
    "vehicles",
    "car",
    "cars",
    "connected vehicles",
    "ev",
    "airline",
    "airport",
    "travel",
    "visa",
]
HEALTH_OR_EDUCATION_PHRASES = [
    "health",
    "medical",
    "hospital",
    "moh",
    "disease",
    "infection",
    "school",
    "education",
    "student",
    "university",
    "spm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter which article-body excerpts should be used in experiments.")
    parser.add_argument("--json-input", required=True, help="Path to Phase 2D.2 RSS vs body context JSON.")
    parser.add_argument(
        "--output",
        default="/tmp/body_excerpt_usage_filtered.json",
        help="Path to write filtered body excerpt usage JSON.",
    )
    parser.add_argument(
        "--memo-output",
        default="/tmp/body_excerpt_usage_filtered_memo.md",
        help="Path to write Markdown observation memo.",
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + "\n", encoding="utf-8")


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def redacted(text: str) -> str:
    result = text
    for pattern in FORBIDDEN_PATTERNS:
        result = result.replace(pattern, "[redacted]")
    return result


def safe_text(value: Any, *, empty: str = "") -> str:
    return redacted(clean_text(value)) or empty


def block_text(value: Any, *, empty: str = "（空）") -> str:
    return redacted(text_value(value).strip()) or empty


def normalized_blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("title"),
        item.get("rss_only"),
        item.get("with_body_excerpt"),
    ]
    return clean_text(" ".join(text_value(part) for part in parts)).lower()


def has_phrase(text: str, phrase: str) -> bool:
    normalized = re.sub(r"\s+", " ", phrase.strip().lower())
    if not normalized:
        return False
    if re.search(r"[a-z0-9]", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None
    return normalized in text


def has_any(text: str, phrases: list[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def classify_article_body_item(item: dict[str, Any]) -> tuple[str, str]:
    text = normalized_blob(item)

    if has_any(text, CRIME_OR_COURT_PHRASES):
        return RSS_ONLY, "blocked_crime_or_court"
    if has_any(text, INCIDENT_PHRASES):
        return RSS_ONLY, "blocked_incident"
    if has_any(text, COST_OR_SUBSIDY_PHRASES):
        return USE_BODY, "allowed_cost_or_subsidy"
    if has_any(text, CONSUMER_OR_CROSSBORDER_SERVICE_PHRASES):
        return USE_BODY, "allowed_consumer_or_crossborder_service"
    if has_any(text, VEHICLE_OR_TRANSPORT_SERVICE_PHRASES):
        return USE_BODY, "allowed_vehicle_or_transport_service"
    if has_any(text, TRANSPORT_OR_INFRA_PHRASES):
        return USE_BODY, "allowed_transport_or_infra"
    if has_any(text, PUBLIC_SERVICE_PHRASES):
        return USE_BODY, "allowed_public_service"
    if has_any(text, MARKET_OR_OVERSEAS_PHRASES):
        return RSS_ONLY, "blocked_market_or_overseas"
    if has_any(text, HEALTH_OR_EDUCATION_PHRASES):
        return USE_BODY, "allowed_health_or_education"
    return RSS_ONLY, "fallback_uncertain"


def classify_item(item: dict[str, Any]) -> tuple[str, str]:
    content_source = clean_text(item.get("content_source"))
    if content_source == RSS_FALLBACK:
        return RSS_FALLBACK, "rss_fallback"
    if content_source != ARTICLE_BODY:
        raise ValueError(f"Invalid content_source: {content_source!r}")
    return classify_article_body_item(item)


def filtered_item(item: dict[str, Any]) -> dict[str, Any]:
    output = dict(item)
    policy, reason = classify_item(item)
    selected_context = SELECTED_WITH_BODY if policy == USE_BODY else RSS_ONLY
    output["body_excerpt_policy"] = policy
    output["body_excerpt_reason"] = reason
    output["selected_context"] = selected_context
    output["body_excerpt_used"] = selected_context == SELECTED_WITH_BODY
    return output


def input_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("Input JSON must contain an items array.")
    if not all(isinstance(item, dict) for item in raw_items):
        raise ValueError("Input JSON items must be objects.")
    return raw_items


def validate_output_items(items: list[dict[str, Any]]) -> None:
    for item in items:
        policy = item.get("body_excerpt_policy")
        selected_context = item.get("selected_context")
        if policy not in POLICY_VALUES:
            raise ValueError(f"Invalid body_excerpt_policy: {policy!r}")
        if selected_context not in SELECTED_CONTEXT_VALUES:
            raise ValueError(f"Invalid selected_context: {selected_context!r}")
        if item.get("body_excerpt_used") != (selected_context == SELECTED_WITH_BODY):
            raise ValueError("body_excerpt_used does not match selected_context.")
        if item.get("content_source") == RSS_FALLBACK and (
            policy != RSS_FALLBACK or item.get("body_excerpt_used") or selected_context != RSS_ONLY
        ):
            raise ValueError("rss_fallback item has invalid body excerpt policy.")


def build_payload(source_data: dict[str, Any], source_json: str) -> dict[str, Any]:
    items = [filtered_item(item) for item in input_items(source_data)]
    validate_output_items(items)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "source_json": source_json,
        "counts": {
            "items": len(items),
            "use_body": sum(1 for item in items if item.get("body_excerpt_policy") == USE_BODY),
            "rss_only": sum(1 for item in items if item.get("body_excerpt_policy") == RSS_ONLY),
            "rss_fallback": sum(1 for item in items if item.get("body_excerpt_policy") == RSS_FALLBACK),
        },
        "items": items,
    }


def render_item(item: dict[str, Any]) -> list[str]:
    selected_text = item.get("with_body_excerpt") if item.get("selected_context") == SELECTED_WITH_BODY else item.get("rss_only")
    return [
        f"## Item {safe_text(item.get('index'))}",
        "",
        f"- source：{safe_text(item.get('source'))}",
        f"- feed：{safe_text(item.get('feed'))}",
        f"- published：{safe_text(item.get('published'))}",
        f"- content_source：{safe_text(item.get('content_source'))}",
        f"- body_excerpt_policy：{safe_text(item.get('body_excerpt_policy'))}",
        f"- body_excerpt_used：{safe_text(item.get('body_excerpt_used'))}",
        f"- body_excerpt_reason：{safe_text(item.get('body_excerpt_reason'))}",
        f"- selected_context：{safe_text(item.get('selected_context'))}",
        f"- URL：{safe_text(item.get('url'))}",
        "",
        "### 選択された入力文脈",
        "",
        block_text(selected_text),
        "",
        "### 観察メモ",
        "",
        "- OK: ",
        "- 要注意: ",
        "- NG: ",
        "- 次回確認: ",
        "",
        "見る観点: use_body判定が妥当か、RSSのみで十分か、本文excerptが事件詳細や海外市場ノイズを増やしていないか。",
        "",
    ]


def render_memo(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    raw_items = payload.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    lines = [
        "# 本文excerpt使用制限 観察メモ",
        "",
        f"- generated_at：{safe_text(payload.get('generated_at'))}",
        f"- source_json：{safe_text(payload.get('source_json'))}",
        f"- items：{safe_text(counts.get('items', len(items)))}",
        f"- use_body：{safe_text(counts.get('use_body', 0))}",
        f"- rss_only：{safe_text(counts.get('rss_only', 0))}",
        f"- rss_fallback：{safe_text(counts.get('rss_fallback', 0))}",
        "",
    ]

    if not items:
        lines.append("判定対象itemはありません。")
        return "\n".join(lines).strip()

    for item in items:
        lines.extend(render_item(item))
    return "\n".join(lines).strip()


def main() -> int:
    args = parse_args()
    payload = build_payload(load_json(args.json_input), args.json_input)
    write_json(args.output, payload)
    write_text(args.memo_output, render_memo(payload))
    print(f"written: {args.output}")
    print(f"written: {args.memo_output}")
    print(
        "body excerpt policy: "
        f"use_body={payload['counts']['use_body']}, "
        f"rss_only={payload['counts']['rss_only']}, "
        f"rss_fallback={payload['counts']['rss_fallback']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
