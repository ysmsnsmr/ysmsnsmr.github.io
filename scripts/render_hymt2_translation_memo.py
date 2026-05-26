#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_PATTERNS = [
    "gsk_",
    "GROQ_API_KEY",
    "Authorization",
    "Bearer",
    "api_key",
]


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return ""


def safe_text(value: Any, *, empty: str = "") -> str:
    text = re.sub(r"\s+", " ", text_value(value)).strip()
    for pattern in FORBIDDEN_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text or empty


def multiline_text(value: Any, *, empty: str = "（空）") -> str:
    text = text_value(value).strip()
    for pattern in FORBIDDEN_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text or empty


def field_status_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts = []
    for key in ["title", "description"]:
        if key in value:
            parts.append(f"{key}={safe_text(value.get(key))}")
    return ", ".join(parts)


def render_original_translated(label: str, original: Any, translated: Any) -> list[str]:
    return [
        f"### {label}",
        "",
        "Original:",
        "",
        multiline_text(original),
        "",
        "Translated:",
        "",
        multiline_text(translated),
        "",
    ]


def render_item(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"## Item {safe_text(item.get('index'))}")
    lines.append("")
    lines.append(f"- カテゴリ：{safe_text(item.get('category'))}")
    lines.append(f"- 出典：{safe_text(item.get('source'))}（{safe_text(item.get('published_date'))}）")
    lines.append(f"- translation_status：{safe_text(item.get('translation_status'))}")
    lines.append(f"- translation_field_status：{field_status_text(item.get('translation_field_status'))}")
    lines.append(f"- translation_elapsed_ms：{safe_text(item.get('translation_elapsed_ms'))}")
    lines.append(f"- URL：{safe_text(item.get('link'))}")
    lines.append("")
    lines.extend(render_original_translated("Title", item.get("title"), item.get("translated_title")))
    lines.extend(render_original_translated("Description", item.get("description"), item.get("translated_description")))
    lines.extend(
        [
            "### 観察メモ",
            "",
            "- OK: ",
            "- 要注意: ",
            "- NG: ",
            "- 次回確認: ",
            "",
            "見る観点: 数字、地名、機関名、制度名、BM行政文、訳の硬さ、余計な説明の有無。",
            "",
        ]
    )
    return lines


def render(data: dict[str, Any]) -> str:
    counts = data.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}

    raw_items = data.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    lines = [
        "# Hy-MT2翻訳観察メモ",
        "",
        f"- generated_at：{safe_text(data.get('generated_at'))}",
        f"- translation_engine：{safe_text(data.get('translation_engine'))}",
        f"- model：{safe_text(data.get('model'))}",
        f"- source_json：{safe_text(data.get('source_json'))}",
        f"- input_items：{safe_text(counts.get('input_items', 0))}",
        f"- translated_items：{safe_text(counts.get('translated_items', 0))}",
        f"- failed_items：{safe_text(counts.get('failed_items', 0))}",
        f"- items：{len(items)}",
        "",
    ]

    if not items:
        lines.append("翻訳対象itemはありません。")
        return "\n".join(lines).strip()

    for item in items:
        lines.extend(render_item(item))
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read translated Hy-MT2 items JSON from this path.")
    parser.add_argument("--output", help="Write observation memo Markdown to this path. Defaults to stdout.")
    args = parser.parse_args()

    markdown = render(load_json(args.json_input))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
