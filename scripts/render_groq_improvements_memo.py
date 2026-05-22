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


def safe_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", text_value(value)).strip()
    for pattern in FORBIDDEN_PATTERNS:
        text = text.replace(pattern, "[redacted]")
    return text


def summary_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [safe_text(item) for item in value if safe_text(item)][:2]
    if isinstance(value, str):
        return [safe_text(line) for line in value.splitlines() if safe_text(line)][:2]
    return []


def normalize_summary(value: Any) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    return {
        "conclusion": safe_text(summary.get("conclusion")),
        "what_happened": summary_lines(summary.get("what_happened")),
        "life_impact": safe_text(summary.get("life_impact")),
        "next_action": safe_text(summary.get("next_action")) or "なし",
    }


def render_summary(label: str, summary: Any) -> list[str]:
    normalized = normalize_summary(summary)
    lines = [f"#### {label}"]
    lines.append(f"- 結論：{normalized['conclusion']}")
    if normalized["what_happened"]:
        for line in normalized["what_happened"]:
            lines.append(f"- 何が起きた：{line}")
    else:
        lines.append("- 何が起きた：")
    lines.append(f"- 生活への影響：{normalized['life_impact']}")
    lines.append(f"- 次アクション：{normalized['next_action']}")
    lines.append("")
    return lines


def render_item(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"### Item {safe_text(item.get('index'))}")
    lines.append(f"- カテゴリ：{safe_text(item.get('category'))}")
    lines.append(f"- 出典：{safe_text(item.get('source'))}（{safe_text(item.get('published_date'))}）")
    lines.append(f"- タイトル：{safe_text(item.get('title'))}")
    lines.append(f"- URL：{safe_text(item.get('link'))}")
    lines.append("")
    lines.extend(render_summary("Original", item.get("original_summary")))
    lines.extend(render_summary("Improved", item.get("improved_summary")))
    lines.extend(
        [
            "#### 観察メモ",
            "- OK: ",
            "- 要注意: ",
            "- NG: ",
            "- 次回確認: ",
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
        "# Groq改善観察メモ",
        "",
        f"- generated_at：{safe_text(data.get('generated_at'))}",
        f"- model：{safe_text(data.get('model'))}",
        f"- requested：{counts.get('requested', 0)}",
        f"- accepted：{counts.get('accepted', 0)}",
        f"- fallback：{counts.get('fallback', 0)}",
        f"- items：{len(items)}",
        "",
    ]

    if not items:
        lines.append("acceptedされた改善はありません。")
        return "\n".join(lines).strip()

    for item in items:
        lines.extend(render_item(item))
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read improved Groq items JSON from this path.")
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
