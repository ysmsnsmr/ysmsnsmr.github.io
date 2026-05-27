#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "phase2d.rss_vs_body_context.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
ARTICLE_BODY = "article_body"
RSS_FALLBACK = "rss_fallback"
ALLOWED_CONTENT_SOURCES = {ARTICLE_BODY, RSS_FALLBACK}
FORBIDDEN_PATTERNS = [
    "gsk_",
    "GROQ_API_KEY",
    "Authorization",
    "Bearer",
    "api_key",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare RSS-only context with Malay Mail article-body excerpt context."
    )
    parser.add_argument("--json-input", required=True, help="Path to Phase 2D.1 body_enriched_items JSON.")
    parser.add_argument(
        "--output",
        default="/tmp/rss_vs_body_context_comparison.json",
        help="Path to write comparison JSON.",
    )
    parser.add_argument(
        "--memo-output",
        default="/tmp/rss_vs_body_context_memo.md",
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


def safe_text(value: Any, *, empty: str = "") -> str:
    text = clean_text(value)
    for pattern in FORBIDDEN_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text or empty


def block_text(value: Any, *, empty: str = "（空）") -> str:
    text = text_value(value).strip()
    for pattern in FORBIDDEN_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text or empty


def item_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("Input JSON must contain an items array.")
    if not all(isinstance(item, dict) for item in raw_items):
        raise ValueError("Input JSON items must be objects.")
    return raw_items


def validate_content_source(value: Any, index: int) -> str:
    content_source = text_value(value).strip()
    if content_source not in ALLOWED_CONTENT_SOURCES:
        raise ValueError(
            f"Item {index} has invalid content_source {content_source!r}; "
            f"expected {sorted(ALLOWED_CONTENT_SOURCES)}."
        )
    return content_source


def build_rss_only_context(item: dict[str, Any]) -> str:
    parts = [
        f"Title: {clean_text(item.get('title'))}",
        f"RSS summary: {clean_text(item.get('rss_summary'))}",
    ]
    return "\n".join(part for part in parts if part.split(": ", 1)[-1])


def build_body_context(item: dict[str, Any], rss_only: str, content_source: str) -> str:
    if content_source != ARTICLE_BODY:
        return rss_only
    body_excerpt = clean_text(item.get("body_excerpt"))
    if not body_excerpt:
        return rss_only
    return f"{rss_only}\nArticle body excerpt: {body_excerpt}"


def build_comparison_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    content_source = validate_content_source(item.get("content_source"), index)
    rss_only = build_rss_only_context(item)
    with_body_excerpt = build_body_context(item, rss_only, content_source)
    same_as_rss_only = with_body_excerpt == rss_only

    return {
        "index": index,
        "source": item.get("source", ""),
        "feed": item.get("feed", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published": item.get("published", ""),
        "content_source": content_source,
        "rss_only": rss_only,
        "with_body_excerpt": with_body_excerpt,
        "delta": {
            "added_chars": max(0, len(with_body_excerpt) - len(rss_only)),
            "body_text_length": item.get("body_text_length", 0),
            "has_body_excerpt": bool(clean_text(item.get("body_excerpt"))),
            "same_as_rss_only": same_as_rss_only,
        },
    }


def build_payload(source_data: dict[str, Any], source_json: str) -> dict[str, Any]:
    items = [build_comparison_item(item, index) for index, item in enumerate(item_list(source_data), start=1)]
    article_body_items = sum(1 for item in items if item["content_source"] == ARTICLE_BODY)
    rss_fallback_items = sum(1 for item in items if item["content_source"] == RSS_FALLBACK)
    body_context_changed = sum(1 for item in items if not item["delta"]["same_as_rss_only"])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "source_json": source_json,
        "counts": {
            "items": len(items),
            "article_body": article_body_items,
            "rss_fallback": rss_fallback_items,
            "body_context_changed": body_context_changed,
        },
        "items": items,
    }


def render_item(item: dict[str, Any]) -> list[str]:
    delta = item.get("delta", {})
    if not isinstance(delta, dict):
        delta = {}

    return [
        f"## Item {safe_text(item.get('index'))}",
        "",
        f"- source：{safe_text(item.get('source'))}",
        f"- feed：{safe_text(item.get('feed'))}",
        f"- published：{safe_text(item.get('published'))}",
        f"- content_source：{safe_text(item.get('content_source'))}",
        f"- added_chars：{safe_text(delta.get('added_chars', 0))}",
        f"- body_text_length：{safe_text(delta.get('body_text_length', 0))}",
        f"- same_as_rss_only：{safe_text(delta.get('same_as_rss_only', False))}",
        f"- URL：{safe_text(item.get('url'))}",
        "",
        "### RSS summaryのみ",
        "",
        block_text(item.get("rss_only")),
        "",
        "### 本文excerptあり",
        "",
        block_text(item.get("with_body_excerpt")),
        "",
        "### 観察メモ",
        "",
        "- OK: ",
        "- 要注意: ",
        "- NG: ",
        "- 次回確認: ",
        "",
        "見る観点: RSSだけでは欠ける具体情報、本文excerptで増える事実、長すぎる、事件詳細が増えすぎる、生活者向け価値が増えないケース。",
        "",
    ]


def render_memo(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    raw_items = payload.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    lines = [
        "# RSS summaryのみ vs Malay Mail本文excerptあり 観察メモ",
        "",
        f"- generated_at：{safe_text(payload.get('generated_at'))}",
        f"- source_json：{safe_text(payload.get('source_json'))}",
        f"- items：{safe_text(counts.get('items', len(items)))}",
        f"- article_body：{safe_text(counts.get('article_body', 0))}",
        f"- rss_fallback：{safe_text(counts.get('rss_fallback', 0))}",
        f"- body_context_changed：{safe_text(counts.get('body_context_changed', 0))}",
        "",
    ]

    if not items:
        lines.append("比較対象itemはありません。")
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
        "comparison: "
        f"items={payload['counts']['items']}, "
        f"article_body={payload['counts']['article_body']}, "
        f"rss_fallback={payload['counts']['rss_fallback']}, "
        f"body_context_changed={payload['counts']['body_context_changed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
