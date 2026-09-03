#!/usr/bin/env python3
"""Validate the single Editorial Entry v3 production candidate."""

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from malaysia_groq_output_contract import EDITORIAL_ENTRY_FORBIDDEN_PATTERNS


SCHEMA_VERSION = "malaysia-groq-editorial-entry-validator/v3"
CATEGORY_HEADERS = ["【速報】", "【生活インパクト】", "【知っておくと得】"]
REQUIRED_LINES = {
    "has_processed_count": "処理対象件数：",
    "has_selected_count": "要約対象件数：",
    "has_failed_sources_line": "失敗したソース一覧：",
}
FORBIDDEN_PATTERNS = EDITORIAL_ENTRY_FORBIDDEN_PATTERNS
URL_RE = re.compile(r"出典元URL：(\S+)")


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as error:
        return "", f"{path}: {error}"


def read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    text, error = read_text(path)
    if error:
        return {}, error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return {}, f"{path}: {error}"
    return (value, None) if isinstance(value, dict) else ({}, f"{path}: top-level JSON is not an object")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def selected_urls(value: dict[str, Any]) -> list[str]:
    return [
        item["link"]
        for item in value.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("link"), str) and item["link"]
    ] if isinstance(value.get("items"), list) else []


def count_duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_improved_counts(value: dict[str, Any]) -> tuple[dict[str, int | None], list[str]]:
    counts = value.get("counts")
    parsed = {"requested": None, "accepted": None, "fallback": None}
    if not isinstance(counts, dict):
        return parsed, ["improved-items JSON does not contain a counts object"]
    failures: list[str] = []
    for key in parsed:
        parsed[key] = optional_int(counts.get(key))
        if parsed[key] is None:
            failures.append(f"improved-items counts.{key} is not an integer")
    return parsed, failures


def parse_observation_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    diagnostics = value.get("diagnostics")
    result: dict[str, Any] = {
        "selected_count": None,
        "groq_accepted_count": None,
        "groq_repaired_count": None,
        "source_display_count": None,
        "rss_fallback_count": None,
        "rss_fallback_source_link_only_count": None,
        "request_cap_skipped_count": None,
        "hard_safety_rejection_reason_counts": {},
        "transport_status_counts": {},
        "json_contract_status_counts": {},
        "json_contract_reason_counts": {},
        "repair_attempted_count": None,
        "repair_accepted_count": None,
        "repair_transport_status_counts": {},
        "repair_json_contract_status_counts": {},
        "repair_json_contract_reason_counts": {},
        "primary_call_outcome_counts": {},
        "repair_call_outcome_counts": {},
        "entry_provenance_line_counts": {},
    }
    if not isinstance(diagnostics, dict):
        return result
    entries = diagnostics.get("editorial_entry_counts")
    if isinstance(entries, dict):
        for key in (
            "selected_count",
            "groq_accepted_count",
            "groq_repaired_count",
            "source_display_count",
            "rss_fallback_count",
            "rss_fallback_source_link_only_count",
            "request_cap_skipped_count",
        ):
            result[key] = optional_int(entries.get(key))
    for key in (
        "hard_safety_rejection_reason_counts",
        "transport_status_counts",
        "json_contract_status_counts",
        "json_contract_reason_counts",
    ):
        raw = diagnostics.get(key)
        if isinstance(raw, dict):
            result[key] = raw
    for key in ("repair_attempted_count", "repair_accepted_count"):
        result[key] = optional_int(diagnostics.get(key))
    for key in (
        "repair_transport_status_counts",
        "repair_json_contract_status_counts",
        "repair_json_contract_reason_counts",
        "primary_call_outcome_counts",
        "repair_call_outcome_counts",
    ):
        raw = diagnostics.get(key)
        if isinstance(raw, dict):
            result[key] = raw
    provenance = diagnostics.get("editorial_entry_provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("line_counts"), dict):
        result["entry_provenance_line_counts"] = provenance["line_counts"]
    return result


def candidate_blocks_by_url(candidate: str) -> dict[str, str]:
    """Split the renderer's stable item blocks without interpreting article text."""
    blocks: dict[str, str] = {}
    current: list[str] = []
    for line in candidate.splitlines():
        current.append(line)
        if line.startswith("- 出典元URL："):
            link = line.partition("：")[2].strip()
            if link:
                blocks[link] = "\n".join(current)
            current = []
    return blocks


def source_display_links(improved: dict[str, Any]) -> set[str]:
    diagnostics = improved.get("diagnostics")
    records = diagnostics.get("decision_records") if isinstance(diagnostics, dict) else []
    if not isinstance(records, list):
        return set()
    return {
        record["link"]
        for record in records if isinstance(record, dict)
        and record.get("render_source_kind") == "source_display"
        and isinstance(record.get("link"), str) and record["link"]
    }


def forbidden_matches_by_provenance(candidate: str, improved: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Apply generated-text leakage checks only to model-generated item blocks.

    A source display intentionally preserves the publisher's title and
    description. Those fields are not generated claims, so dateline-style
    tokens there are observable source text rather than model leakage.
    """
    blocks = candidate_blocks_by_url(candidate)
    source_links = source_display_links(improved)
    remainder = candidate
    for block in blocks.values():
        remainder = remainder.replace(block, "", 1)
    matches = {pattern for pattern in FORBIDDEN_PATTERNS if pattern in remainder}
    for link, block in blocks.items():
        if link not in source_links:
            matches.update(pattern for pattern in FORBIDDEN_PATTERNS if pattern in block)
    return sorted(matches), sorted(source_links)


def validate_candidate(
    selected_json_path: Path,
    candidate_markdown_path: Path,
    improved_items_json_path: Path,
    rss_fallback_markdown_path: Path,
) -> dict[str, Any]:
    failures: list[str] = []
    selected_json, selected_error = read_json(selected_json_path)
    candidate, candidate_error = read_text(candidate_markdown_path)
    improved, improved_error = read_json(improved_items_json_path)
    rss_fallback, rss_error = read_text(rss_fallback_markdown_path)
    input_errors = {
        "selected_json": selected_error,
        "candidate_markdown": candidate_error,
        "improved_items_json": improved_error,
        "rss_fallback_markdown": rss_error,
    }
    failures.extend(f"unreadable {name}: {error}" for name, error in input_errors.items() if error)
    selected = selected_urls(selected_json)
    rendered = URL_RE.findall(candidate)
    missing = sorted((Counter(selected) - Counter(rendered)).elements())
    extra = sorted((Counter(rendered) - Counter(selected)).elements())
    counts, count_failures = parse_improved_counts(improved)
    failures.extend(count_failures)
    if counts["accepted"] is not None and counts["accepted"] <= 0:
        failures.append("Groq accepted count is zero")
    if not selected:
        failures.append("selected JSON contains no item links")
    if len(selected) != len(rendered):
        failures.append("selected URL count does not equal rendered URL count")
    if missing:
        failures.append("candidate Markdown is missing selected URLs")
    if extra:
        failures.append("candidate Markdown contains extra URLs")
    if count_duplicates(selected):
        failures.append("selected JSON contains duplicate URLs")
    if count_duplicates(rendered):
        failures.append("candidate Markdown contains duplicate rendered URLs")
    if not all(header in candidate for header in CATEGORY_HEADERS):
        failures.append("candidate Markdown is missing one or more category headers")
    for key, marker in REQUIRED_LINES.items():
        if marker not in candidate:
            failures.append(f"candidate Markdown is missing {key}")
    forbidden, source_display = forbidden_matches_by_provenance(candidate, improved)
    if forbidden:
        failures.append("candidate Markdown contains forbidden leakage strings")
    if counts["accepted"] and candidate == rss_fallback:
        failures.append("candidate Markdown is identical to RSS fallback despite accepted Groq items")
    diagnostics = parse_observation_diagnostics(improved)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": not failures,
        "failures": failures,
        "inputs": {
            "selected_json": str(selected_json_path),
            "candidate_markdown": str(candidate_markdown_path),
            "improved_items_json": str(improved_items_json_path),
            "rss_fallback_markdown": str(rss_fallback_markdown_path),
            "input_errors": input_errors,
        },
        "counts": {
            "selected_urls": len(selected),
            "rendered_urls": len(rendered),
            "groq_requested": counts["requested"],
            "groq_accepted": counts["accepted"],
            "groq_fallback": counts["fallback"],
        },
        "url_validation": {
            "missing_selected_urls": missing,
            "extra_rendered_urls": extra,
            "selected_duplicate_urls": count_duplicates(selected),
            "rendered_duplicate_urls": count_duplicates(rendered),
        },
        "markdown_validation": {
            "category_headers": {header: header in candidate for header in CATEGORY_HEADERS},
            "required_lines": {key: marker in candidate for key, marker in REQUIRED_LINES.items()},
            "forbidden_matches": forbidden,
            "source_display_links": source_display,
            "matches_rss_fallback": candidate == rss_fallback,
        },
        "observation": diagnostics,
    }


def write_report(path: Path, result: dict[str, Any]) -> None:
    observation = result["observation"]
    lines = [
        "# Groq Editorial Entry v3 validator",
        "",
        f"- status: {'pass' if result['passed'] else 'fail'}",
        f"- selected_urls: {result['counts']['selected_urls']}",
        f"- rendered_urls: {result['counts']['rendered_urls']}",
        f"- groq_requested: {result['counts']['groq_requested']}",
        f"- groq_accepted: {result['counts']['groq_accepted']}",
        f"- groq_fallback: {result['counts']['groq_fallback']}",
        f"- groq_repaired_count: {observation['groq_repaired_count']}",
        f"- source_display_count: {observation['source_display_count']}",
        f"- rss_fallback_count: {observation['rss_fallback_count']}",
        f"- rss_fallback_source_link_only_count: {observation['rss_fallback_source_link_only_count']}",
        f"- request_cap_skipped_count: {observation['request_cap_skipped_count']}",
        f"- hard_safety_rejection_reason_counts: {json.dumps(observation['hard_safety_rejection_reason_counts'], ensure_ascii=False)}",
        f"- transport_status_counts: {json.dumps(observation['transport_status_counts'], ensure_ascii=False)}",
        f"- json_contract_status_counts: {json.dumps(observation['json_contract_status_counts'], ensure_ascii=False)}",
        f"- json_contract_reason_counts: {json.dumps(observation['json_contract_reason_counts'], ensure_ascii=False)}",
        f"- repair_attempted_count: {observation['repair_attempted_count']}",
        f"- repair_accepted_count: {observation['repair_accepted_count']}",
        f"- repair_transport_status_counts: {json.dumps(observation['repair_transport_status_counts'], ensure_ascii=False)}",
        f"- repair_json_contract_status_counts: {json.dumps(observation['repair_json_contract_status_counts'], ensure_ascii=False)}",
        f"- repair_json_contract_reason_counts: {json.dumps(observation['repair_json_contract_reason_counts'], ensure_ascii=False)}",
        f"- primary_call_outcome_counts: {json.dumps(observation['primary_call_outcome_counts'], ensure_ascii=False)}",
        f"- repair_call_outcome_counts: {json.dumps(observation['repair_call_outcome_counts'], ensure_ascii=False)}",
    ]
    if result["failures"]:
        lines.extend(["", "## Failures", "", *[f"- {failure}" for failure in result["failures"]]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-json", type=Path, required=True)
    parser.add_argument("--candidate-markdown", type=Path, required=True)
    parser.add_argument("--improved-items-json", type=Path, required=True)
    parser.add_argument("--rss-fallback-markdown", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    result = validate_candidate(args.selected_json, args.candidate_markdown, args.improved_items_json, args.rss_fallback_markdown)
    write_json(args.status_output, result)
    write_report(args.report_output, result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
