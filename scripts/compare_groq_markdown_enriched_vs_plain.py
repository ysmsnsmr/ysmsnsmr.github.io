#!/usr/bin/env python3
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


FORBIDDEN_PATTERNS = [
    "gsk_",
    "GROQ_API_KEY",
    "Authorization",
    "Bearer",
    "api_key",
    "body_excerpt",
    "score",
    "tags",
    "flags",
    "reasons",
    "penalties",
    "background_value",
    "selection_summary",
    "::inbox-item",
]
DIFF_MAX_LINES = 160


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Groq rendered Markdown with and without enriched body excerpts.")
    parser.add_argument("--selected-json", required=True, help="Plain selected_items.json input.")
    parser.add_argument("--enriched-json", required=True, help="Enriched selected_items JSON input.")
    parser.add_argument("--plain-output", required=True, help="Path to write plain Markdown.")
    parser.add_argument("--enriched-output", required=True, help="Path to write enriched Markdown.")
    parser.add_argument("--memo-output", required=True, help="Path to write comparison memo.")
    parser.add_argument("--model", help="Groq model passed to renderer.")
    parser.add_argument("--force-all", action="store_true", help="Pass --force-all to renderer.")
    parser.add_argument("--debug-groq", action="store_true", help="Pass --debug-groq to renderer.")
    return parser.parse_args()


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def redact(text: str) -> str:
    redacted = text
    for pattern in FORBIDDEN_PATTERNS:
        redacted = redacted.replace(pattern, "[redacted]")
    return redacted


def safe_text(value: Any) -> str:
    return redact(clean_text(value))


def load_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + "\n", encoding="utf-8")


def renderer_path() -> Path:
    return Path(__file__).resolve().parent / "render_malaysia_news_with_groq.py"


def run_renderer(json_input: str, output: str, args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-B",
        str(renderer_path()),
        "--json-input",
        json_input,
        "--output",
        output,
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.force_all:
        command.append("--force-all")
    if args.debug_groq:
        command.append("--debug-groq")
    return subprocess.run(command, check=True, text=True, capture_output=True)


def render_plain_without_enriched(args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="malaysia-plain-render-") as temp_dir:
        plain_json = Path(temp_dir) / "selected_items.json"
        shutil.copyfile(args.selected_json, plain_json)
        return run_renderer(str(plain_json), args.plain_output, args)


def render_enriched(args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    return run_renderer(args.enriched_json, args.enriched_output, args)


def markdown_signature(path: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    category = ""
    source = ""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped in {"【速報】", "【生活インパクト】", "【知っておくと得】"}:
            category = stripped
        elif stripped.startswith("- 出典："):
            source = stripped.removeprefix("- 出典：")
        elif stripped.startswith("- 出典元URL："):
            url = stripped.removeprefix("- 出典元URL：")
            rows.append((category, source, url))
            source = ""
    return rows


def use_body_items(enriched_json: str) -> list[dict[str, Any]]:
    data = load_json(enriched_json)
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        if item.get("body_excerpt_policy") != "use_body":
            continue
        result.append(
            {
                "index": index,
                "category": item.get("category", ""),
                "source": item.get("source", ""),
                "published_date": item.get("published_date", ""),
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "reason": item.get("body_excerpt_reason", ""),
            }
        )
    return result


def short_stderr(process: subprocess.CompletedProcess[str]) -> str:
    lines = [redact(line.strip()) for line in process.stderr.splitlines() if line.strip()]
    safe_lines = [line for line in lines if not any(pattern in line for pattern in FORBIDDEN_PATTERNS)]
    return "\n".join(safe_lines[-8:])


def diff_excerpt(plain_path: str, enriched_path: str) -> list[str]:
    plain_lines = Path(plain_path).read_text(encoding="utf-8").splitlines()
    enriched_lines = Path(enriched_path).read_text(encoding="utf-8").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            plain_lines,
            enriched_lines,
            fromfile="plain",
            tofile="enriched",
            lineterm="",
            n=3,
        )
    )
    return [redact(line) for line in diff_lines[:DIFF_MAX_LINES]]


def render_memo(
    args: argparse.Namespace,
    plain_process: subprocess.CompletedProcess[str],
    enriched_process: subprocess.CompletedProcess[str],
) -> str:
    plain_sig = markdown_signature(args.plain_output)
    enriched_sig = markdown_signature(args.enriched_output)
    uses_body = use_body_items(args.enriched_json)
    diff_lines = diff_excerpt(args.plain_output, args.enriched_output)

    lines = [
        "# Groq Markdown enriched/plain比較メモ",
        "",
        f"- selected_json：{safe_text(args.selected_json)}",
        f"- enriched_json：{safe_text(args.enriched_json)}",
        f"- plain_output：{safe_text(args.plain_output)}",
        f"- enriched_output：{safe_text(args.enriched_output)}",
        f"- plain_items：{len(plain_sig)}",
        f"- enriched_items：{len(enriched_sig)}",
        f"- signature_match：{'OK' if plain_sig == enriched_sig else 'NG'}",
        f"- use_body_items：{len(uses_body)}",
        "",
    ]

    if uses_body:
        lines.append("## use_body Items")
        lines.append("")
        for item in uses_body:
            lines.append(
                "- "
                f"item {safe_text(item.get('index'))}: "
                f"{safe_text(item.get('source'))} / "
                f"{safe_text(item.get('reason'))} / "
                f"{safe_text(item.get('title'))}"
            )
        lines.append("")

    plain_stderr = short_stderr(plain_process)
    enriched_stderr = short_stderr(enriched_process)
    if plain_stderr or enriched_stderr:
        lines.extend(["## Renderer Stderr Summary", ""])
        if plain_stderr:
            lines.extend(["### Plain", "```text", plain_stderr, "```", ""])
        if enriched_stderr:
            lines.extend(["### Enriched", "```text", enriched_stderr, "```", ""])

    lines.extend(["## Diff Excerpt", ""])
    if diff_lines:
        lines.extend(["```diff", *diff_lines, "```", ""])
    else:
        lines.append("差分はありません。")
        lines.append("")

    lines.extend(
        [
            "## 観察欄",
            "",
            "- OK: ",
            "- 要注意: ",
            "- NG: ",
            "- 次回確認: ",
        ]
    )
    return "\n".join(lines).strip()


def assert_no_forbidden_output(paths: list[str]) -> None:
    pattern = re.compile("|".join(re.escape(pattern) for pattern in FORBIDDEN_PATTERNS))
    violations: list[str] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        match = pattern.search(text)
        if match:
            violations.append(f"{path}: {match.group(0)}")
    if violations:
        raise ValueError("Forbidden output detected: " + "; ".join(violations))


def main() -> int:
    args = parse_args()
    plain_process = render_plain_without_enriched(args)
    enriched_process = render_enriched(args)
    memo = render_memo(args, plain_process, enriched_process)
    write_text(args.memo_output, memo)
    assert_no_forbidden_output([args.plain_output, args.enriched_output, args.memo_output])
    print(f"written: {args.plain_output}")
    print(f"written: {args.enriched_output}")
    print(f"written: {args.memo_output}")
    print(
        "comparison: "
        f"plain_items={len(markdown_signature(args.plain_output))}, "
        f"enriched_items={len(markdown_signature(args.enriched_output))}, "
        f"signature_match={markdown_signature(args.plain_output) == markdown_signature(args.enriched_output)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
