#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "malaysia-groq-merged-candidate-validator/v1"
CATEGORY_HEADERS = ["【速報】", "【生活インパクト】", "【知っておくと得】"]
REQUIRED_LINES = {
    "has_processed_count": "処理対象件数：",
    "has_selected_count": "要約対象件数：",
    "has_failed_sources_line": "失敗したソース一覧：",
}
FORBIDDEN_PATTERNS = [
    "KUALA LUMPUR,",
    "PUTRAJAYA,",
    "SHAH ALAM,",
    "GEORGE TOWN,",
    "MELAKA,",
    "— The",
    "::inbox-item",
    "The post",
    "appeared first",
    "Lowyat",
    "lowyat",
    "RSS内のタイトルと説明をもとに整理しました。",
    "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。",
]
URL_RE = re.compile(r"出典元URL：(\S+)")


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as error:
        return "", f"{path}: {error}"
    except UnicodeDecodeError as error:
        return "", f"{path}: {error}"


def read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    text, error = read_text(path)
    if error:
        return {}, error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return {}, f"{path}: {error}"
    if not isinstance(value, dict):
        return {}, f"{path}: top-level JSON is not an object"
    return value, None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def markdown_urls(markdown: str) -> list[str]:
    return URL_RE.findall(markdown)


def selected_urls(selected_json: dict[str, Any]) -> list[str]:
    items = selected_json.get("items")
    if not isinstance(items, list):
        return []
    urls: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if isinstance(link, str) and link:
            urls.append(link)
    return urls


def count_duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def counter_missing_and_extra(expected: list[str], actual: list[str]) -> tuple[list[str], list[str]]:
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    missing = sorted((expected_counts - actual_counts).elements())
    extra = sorted((actual_counts - expected_counts).elements())
    return missing, extra


def parse_improved_counts(improved_json: dict[str, Any]) -> tuple[dict[str, int | None], list[str]]:
    failures: list[str] = []
    raw_counts = improved_json.get("counts")
    parsed: dict[str, int | None] = {"requested": None, "accepted": None, "fallback": None}
    if not isinstance(raw_counts, dict):
        return parsed, ["improved-items JSON does not contain a counts object"]
    for key in parsed:
        value = raw_counts.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            failures.append(f"improved-items counts.{key} is not an integer")
        else:
            parsed[key] = value
    return parsed, failures


def parse_decision_diagnostics(improved_json: dict[str, Any]) -> dict[str, int | None]:
    parsed: dict[str, int | None] = {
        "decision_records": None,
        "decision_requested": None,
        "decision_accepted": None,
        "decision_fallback": None,
        "decision_skipped": None,
    }
    diagnostics = improved_json.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return parsed
    records = diagnostics.get("decision_records")
    if not isinstance(records, list):
        return parsed
    parsed["decision_records"] = len(records)
    parsed["decision_requested"] = sum(
        1 for record in records if isinstance(record, dict) and record.get("requested") is True
    )
    parsed["decision_accepted"] = sum(
        1 for record in records if isinstance(record, dict) and record.get("accepted") is True
    )
    parsed["decision_fallback"] = sum(
        1 for record in records if isinstance(record, dict) and record.get("decision") == "fallback"
    )
    parsed["decision_skipped"] = sum(
        1 for record in records if isinstance(record, dict) and record.get("decision") == "skipped"
    )
    return parsed


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def parse_observation_diagnostics(improved_json: dict[str, Any]) -> dict[str, int | None]:
    parsed: dict[str, int | None] = {
        "accepted_count": None,
        "topic_fallback_count": None,
        "generic_fallback_count": None,
        "request_cap_skipped_generic_fallback_count": None,
        "entry_candidate_available_count": None,
        "entry_candidate_full_rejected_count": None,
        "entry_candidate_unavailable_count": None,
    }
    diagnostics = improved_json.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return parsed
    fallback_counts = diagnostics.get("json_render_fallback_counts")
    if isinstance(fallback_counts, dict):
        parsed["accepted_count"] = optional_int(fallback_counts.get("accepted_count"))
        parsed["topic_fallback_count"] = optional_int(fallback_counts.get("topic_fallback_count"))
        parsed["generic_fallback_count"] = optional_int(fallback_counts.get("generic_fallback_count"))
    priority_observation = diagnostics.get("request_priority_observation")
    if isinstance(priority_observation, dict):
        parsed["request_cap_skipped_generic_fallback_count"] = optional_int(
            priority_observation.get("request_cap_skipped_generic_fallback_count")
        )
    entry_observation = diagnostics.get("entry_candidate_observation")
    if isinstance(entry_observation, dict):
        parsed["entry_candidate_available_count"] = optional_int(
            entry_observation.get("entry_candidate_available_count")
        )
        parsed["entry_candidate_full_rejected_count"] = optional_int(
            entry_observation.get("entry_candidate_full_rejected_count")
        )
        parsed["entry_candidate_unavailable_count"] = optional_int(
            entry_observation.get("entry_candidate_unavailable_count")
        )
    return parsed


def validate_candidate(
    selected_json_path: Path,
    candidate_markdown_path: Path,
    improved_items_json_path: Path,
    rss_fallback_markdown_path: Path,
) -> dict[str, Any]:
    failures: list[str] = []

    selected_json, selected_error = read_json(selected_json_path)
    candidate_markdown, candidate_error = read_text(candidate_markdown_path)
    improved_json, improved_error = read_json(improved_items_json_path)
    rss_fallback_markdown, rss_error = read_text(rss_fallback_markdown_path)

    input_errors = {
        "selected_json": selected_error,
        "candidate_markdown": candidate_error,
        "improved_items_json": improved_error,
        "rss_fallback_markdown": rss_error,
    }
    for label, error in input_errors.items():
        if error:
            failures.append(f"unreadable {label}: {error}")

    selected = selected_urls(selected_json)
    rendered = markdown_urls(candidate_markdown)
    missing_urls, extra_urls = counter_missing_and_extra(selected, rendered)
    selected_duplicate_urls = count_duplicates(selected)
    rendered_duplicate_urls = count_duplicates(rendered)

    counts, count_failures = parse_improved_counts(improved_json)
    decision_diagnostics = parse_decision_diagnostics(improved_json)
    observation_diagnostics = parse_observation_diagnostics(improved_json)
    failures.extend(count_failures)
    accepted_count = counts.get("accepted")
    if accepted_count is not None and accepted_count <= 0:
        failures.append("Groq accepted count is zero")

    if not selected:
        failures.append("selected JSON contains no item links")
    if len(selected) != len(rendered):
        failures.append("selected URL count does not equal rendered URL count")
    if missing_urls:
        failures.append("candidate Markdown is missing selected URLs")
    if extra_urls:
        failures.append("candidate Markdown contains extra URLs")
    if selected_duplicate_urls:
        failures.append("selected JSON contains duplicate URLs")
    if rendered_duplicate_urls:
        failures.append("candidate Markdown contains duplicate rendered URLs")

    required_line_results = {
        key: marker in candidate_markdown for key, marker in REQUIRED_LINES.items()
    }
    category_header_results = {
        header: header in candidate_markdown for header in CATEGORY_HEADERS
    }
    if not all(category_header_results.values()):
        failures.append("candidate Markdown is missing one or more category headers")
    for key, present in required_line_results.items():
        if not present:
            failures.append(f"candidate Markdown is missing {key}")

    forbidden_matches = [
        pattern for pattern in FORBIDDEN_PATTERNS if pattern in candidate_markdown
    ]
    if forbidden_matches:
        failures.append("candidate Markdown contains forbidden leakage strings")

    candidate_matches_rss_fallback = (
        not candidate_error
        and not rss_error
        and candidate_markdown == rss_fallback_markdown
    )
    if accepted_count is not None and accepted_count > 0 and candidate_matches_rss_fallback:
        failures.append("candidate Markdown is identical to RSS fallback despite accepted Groq items")

    passed = not failures
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": passed,
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
            "groq_requested": counts.get("requested"),
            "groq_accepted": counts.get("accepted"),
            "groq_fallback": counts.get("fallback"),
            **decision_diagnostics,
            **observation_diagnostics,
        },
        "url_validation": {
            "missing_selected_urls": missing_urls,
            "extra_rendered_urls": extra_urls,
            "selected_duplicate_urls": selected_duplicate_urls,
            "rendered_duplicate_urls": rendered_duplicate_urls,
        },
        "markdown_validation": {
            "category_headers": category_header_results,
            **required_line_results,
            "forbidden_matches": forbidden_matches,
            "candidate_matches_rss_fallback": candidate_matches_rss_fallback,
        },
        "production_boundary": {
            "validator_only": True,
            "wrote_news_malaysia": False,
        },
    }


def write_markdown_report(path: Path, status: dict[str, Any]) -> None:
    counts = status["counts"]
    url_validation = status["url_validation"]
    markdown_validation = status["markdown_validation"]
    failures = status["failures"]
    lines = [
        "# Phase 2B.15B Groq Merged Candidate Validator Report",
        "",
        f"- generated_at: {status['generated_at']}",
        f"- passed: {str(status['passed']).lower()}",
        f"- selected_urls: {counts['selected_urls']}",
        f"- rendered_urls: {counts['rendered_urls']}",
        f"- groq_requested: {counts['groq_requested']}",
        f"- groq_accepted: {counts['groq_accepted']}",
        f"- groq_fallback: {counts['groq_fallback']}",
        f"- decision_records: {counts.get('decision_records')}",
        f"- decision_requested: {counts.get('decision_requested')}",
        f"- decision_accepted: {counts.get('decision_accepted')}",
        f"- decision_fallback: {counts.get('decision_fallback')}",
        f"- decision_skipped: {counts.get('decision_skipped')}",
        f"- accepted_count: {counts.get('accepted_count')}",
        f"- topic_fallback_count: {counts.get('topic_fallback_count')}",
        f"- generic_fallback_count: {counts.get('generic_fallback_count')}",
        f"- request_cap_skipped_generic_fallback_count: {counts.get('request_cap_skipped_generic_fallback_count')}",
        f"- entry_candidate_available_count: {counts.get('entry_candidate_available_count')}",
        f"- entry_candidate_full_rejected_count: {counts.get('entry_candidate_full_rejected_count')}",
        f"- entry_candidate_unavailable_count: {counts.get('entry_candidate_unavailable_count')}",
        "",
        "## Validation",
        "",
        f"- missing_selected_urls: {len(url_validation['missing_selected_urls'])}",
        f"- extra_rendered_urls: {len(url_validation['extra_rendered_urls'])}",
        f"- selected_duplicate_urls: {len(url_validation['selected_duplicate_urls'])}",
        f"- rendered_duplicate_urls: {len(url_validation['rendered_duplicate_urls'])}",
        f"- category_headers_present: {all(markdown_validation['category_headers'].values())}",
        f"- has_processed_count: {markdown_validation['has_processed_count']}",
        f"- has_selected_count: {markdown_validation['has_selected_count']}",
        f"- has_failed_sources_line: {markdown_validation['has_failed_sources_line']}",
        f"- forbidden_matches: {', '.join(markdown_validation['forbidden_matches']) or 'none'}",
        f"- candidate_matches_rss_fallback: {markdown_validation['candidate_matches_rss_fallback']}",
        "",
        "## Failure Reasons",
        "",
    ]
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- production_overwrite: not performed",
            "- news/malaysia: not written by validator",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-json", required=True)
    parser.add_argument("--candidate-markdown", required=True)
    parser.add_argument("--improved-items-json", required=True)
    parser.add_argument("--rss-fallback-markdown", required=True)
    parser.add_argument("--status-output", required=True)
    parser.add_argument("--report-output", required=True)
    args = parser.parse_args()

    status = validate_candidate(
        Path(args.selected_json),
        Path(args.candidate_markdown),
        Path(args.improved_items_json),
        Path(args.rss_fallback_markdown),
    )
    write_json(Path(args.status_output), status)
    write_markdown_report(Path(args.report_output), status)

    if not status["passed"]:
        print(
            "Groq merged candidate validation failed; future production overwrite must fail open to RSS Markdown.",
            file=sys.stderr,
        )
    return 0 if status["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
