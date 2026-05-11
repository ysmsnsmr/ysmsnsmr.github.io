#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any


CATEGORIES = ["【速報】", "【生活インパクト】", "【知っておくと得】"]


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def summary_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [line for line in (text_value(item).strip() for item in value) if line][:2]
    if isinstance(value, str):
        return [line for line in value.splitlines() if line.strip()][:2]
    return []


def render_item(item: dict[str, Any]) -> list[str]:
    summary = item.get("selected_summary")
    if not isinstance(summary, dict):
        summary = {}
    lines: list[str] = []
    conclusion = text_value(summary.get("conclusion")).strip()
    life_impact = text_value(summary.get("life_impact")).strip()
    next_action = text_value(summary.get("next_action")).strip()
    source = text_value(item.get("source")).strip()
    published_date = text_value(item.get("published_date")).strip()
    link = text_value(item.get("link")).strip()

    lines.append(f"- 結論：{conclusion}")
    for line in summary_lines(summary.get("what_happened")):
        lines.append(f"- 何が起きた：{line}")
    lines.append(f"- 生活への影響：{life_impact}")
    if next_action:
        lines.append(f"- 次アクション：{next_action}")
    lines.append(f"- 出典：{source}（{published_date}）")
    lines.append(f"- 出典元URL：{link}")
    lines.append("")
    return lines


def render(data: dict[str, Any]) -> str:
    raw_items = data.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    counts = data.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    failed_sources = data.get("failed_sources", [])
    if not isinstance(failed_sources, list):
        failed_sources = []

    lines: list[str] = []
    for category in CATEGORIES:
        lines.append(category)
        lines.append("")
        for item in items:
            if item.get("category") == category:
                lines.extend(render_item(item))

    processed = counts.get("processed", 0)
    selected = counts.get("selected", len(items))
    lines.append(f"処理対象件数：{processed}件")
    lines.append(f"要約対象件数：{selected}件")
    failed_text = ", ".join(text_value(source) for source in failed_sources if text_value(source)) or "なし"
    lines.append(f"失敗したソース一覧：{failed_text}")
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read selected Malaysia news items JSON from this path.")
    parser.add_argument("--output", help="Write rendered Markdown to this path. Defaults to stdout.")
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
