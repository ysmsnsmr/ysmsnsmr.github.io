#!/usr/bin/env python3
import argparse
import copy
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_MODEL_PATH = "/tmp/hymt2/Hy-MT2-1.8B-Q4_K_M.gguf"
MODEL_NAME = "tencent/Hy-MT2-1.8B-GGUF:Q4_K_M"
SCHEMA_VERSION = "phase2c.translated_items.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")


TITLE_PROMPT_TEMPLATE = """Translate the following RSS news title into Japanese.
Only output the translated Japanese.
Do not add facts.
Do not summarize.
Keep names, agencies, place names, dates, times, and numbers faithful.
Title:
{text}
"""


DESCRIPTION_PROMPT_TEMPLATE = """Translate the following RSS news description into Japanese.
Only output the translated Japanese.
Only translate the RSS description text.
Do not translate the context title as part of the output.
Do not add facts.
Do not summarize.
Keep names, agencies, place names, dates, times, and numbers faithful.
Context title: {context_title}
Description:
{text}
"""

TITLE_N_PREDICT = "128"
DESCRIPTION_N_PREDICT = "192"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate selected RSS item titles/descriptions with a local Hy-MT2 GGUF model."
    )
    parser.add_argument("--json-input", required=True, help="Path to selected_items.json.")
    parser.add_argument("--output", required=True, help="Path to write translated_items.json.")
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH, help="Path to Hy-MT2 GGUF model.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum number of items to translate.")
    parser.add_argument("--timeout-sec", type=float, default=60.0, help="Timeout per translated field.")
    parser.add_argument("--llama-bin", default="", help="Path to llama-completion. Defaults to PATH lookup.")
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


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def resolve_llama_bin(explicit_path: str) -> str:
    if explicit_path:
        if not Path(explicit_path).exists():
            raise FileNotFoundError(f"llama-completion not found: {explicit_path}")
        return explicit_path
    found = shutil.which("llama-completion")
    if not found:
        raise FileNotFoundError("llama-completion not found in PATH. Pass --llama-bin.")
    return found


def clean_translation_output(output: str, prompt: str) -> str:
    lines: list[str] = []
    prompt_lines = {line.strip() for line in prompt.splitlines() if line.strip()}
    skip_prefixes = (
        "build:",
        "llama_",
        "main:",
        "system_info:",
        "sampling:",
        "generate:",
        "model:",
        "common_",
        "print_info:",
    )

    for raw_line in output.splitlines():
        line = raw_line.replace("\b", "").strip()
        if not line:
            continue
        if line in {"|", "/", "-", "\\"}:
            continue
        if line in prompt_lines:
            continue
        lower = line.lower()
        if lower.startswith(skip_prefixes):
            continue
        if "prompt eval" in lower or "eval time" in lower or "total time" in lower:
            continue
        if line.startswith("[") and ("Prompt:" in line or "Generation:" in line):
            continue
        lines.append(line)

    text = " ".join(lines)
    text = re.sub(r"(?is)^.*?\btranslated text\s*:\s*", "", text)
    text = re.sub(r"(?is)^.*?\btranslation\s*:\s*", "", text)
    text = re.sub(r"(?is)^.*?(?:\bdescription\b|説明)\s*[:：]\s*", "", text)
    text = re.sub(r"\[(?:全文|end of text)\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:タイムアウト|翻訳|訳文|日本語訳)\s*[:：]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def translate_text(
    text: str,
    *,
    llama_bin: str,
    model_path: str,
    timeout_sec: float,
    context_title: str = "",
    n_predict: str = TITLE_N_PREDICT,
) -> tuple[str, str, int]:
    source_text = text.strip()
    if not source_text:
        return "", "empty_output", 0

    if context_title.strip():
        prompt = DESCRIPTION_PROMPT_TEMPLATE.format(
            context_title=context_title.strip(),
            text=source_text,
        )
    else:
        prompt = TITLE_PROMPT_TEMPLATE.format(text=source_text)
    command = [
        llama_bin,
        "-m",
        model_path,
        "-p",
        prompt,
        "-c",
        "2048",
        "-n",
        n_predict,
        "-cnv",
        "--single-turn",
        "--no-display-prompt",
        "--no-warmup",
        "--simple-io",
        "--temp",
        "0.7",
        "--top-p",
        "0.6",
        "--top-k",
        "20",
        "--repeat-penalty",
        "1.05",
    ]

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            timeout=timeout_sec,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return "", "timeout", elapsed_ms
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    combined_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    translated = clean_translation_output(completed.stdout, prompt)

    if completed.returncode != 0:
        return translated, "error", elapsed_ms
    if not translated:
        translated = clean_translation_output(combined_output, prompt)
    if not translated:
        return "", "empty_output", elapsed_ms
    return translated, "ok", elapsed_ms


def combine_status(title_status: str, description_status: str) -> str:
    if title_status == "ok" or description_status == "ok":
        return "ok"
    if title_status == "timeout" or description_status == "timeout":
        return "timeout"
    if title_status == "empty_output" and description_status == "empty_output":
        return "empty_output"
    return "error"


def translated_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if item.get("translation_status") == "ok")


def failed_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if item.get("translation_status") != "ok")


def translate_items(
    input_items: list[Any],
    *,
    limit: int,
    llama_bin: str,
    model_path: str,
    timeout_sec: float,
) -> list[dict[str, Any]]:
    selected = input_items[: max(limit, 0)]
    output_items: list[dict[str, Any]] = []

    print(f"Translating {len(selected)} of {len(input_items)} items...", flush=True)
    for zero_index, raw_item in enumerate(selected):
        item = copy.deepcopy(raw_item) if isinstance(raw_item, dict) else {}
        item["index"] = zero_index + 1

        title = text_value(item.get("title"))
        description = text_value(item.get("description"))

        translated_title, title_status, title_elapsed = translate_text(
            title,
            llama_bin=llama_bin,
            model_path=model_path,
            timeout_sec=timeout_sec,
            n_predict=TITLE_N_PREDICT,
        )
        translated_description, description_status, description_elapsed = translate_text(
            description,
            llama_bin=llama_bin,
            model_path=model_path,
            timeout_sec=timeout_sec,
            context_title=title,
            n_predict=DESCRIPTION_N_PREDICT,
        )

        status = combine_status(title_status, description_status)
        item["translated_title"] = translated_title
        item["translated_description"] = translated_description
        item["translation_elapsed_ms"] = title_elapsed + description_elapsed
        item["translation_status"] = status
        item["translation_field_status"] = {
            "title": title_status,
            "description": description_status,
        }

        print(f"item {zero_index + 1}: {status}", flush=True)
        output_items.append(item)

    return output_items


def build_payload(
    *,
    source_json: str,
    input_count: int,
    model_path: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "translation_engine": "hymt2-local-gguf",
        "model": MODEL_NAME,
        "model_path": model_path,
        "source_json": source_json,
        "counts": {
            "input_items": input_count,
            "translated_items": translated_count(items),
            "failed_items": failed_count(items),
        },
        "items": items,
    }


def main() -> int:
    args = parse_args()
    llama_bin = resolve_llama_bin(args.llama_bin)
    model_path = Path(args.model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"model file not found: {model_path}")

    source = load_json(args.json_input)
    raw_items = source.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("input JSON must contain an items array.")

    items = translate_items(
        raw_items,
        limit=args.limit,
        llama_bin=llama_bin,
        model_path=str(model_path),
        timeout_sec=args.timeout_sec,
    )
    payload = build_payload(
        source_json=args.json_input,
        input_count=len(raw_items),
        model_path=str(model_path),
        items=items,
    )
    write_json(args.output, payload)
    print(f"written: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
