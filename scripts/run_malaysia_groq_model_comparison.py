#!/usr/bin/env python3
"""Run artifact-only Groq model profiles and build a fixed-metric comparison."""

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from malaysia_groq_model_profiles import (
    DEFAULT_CONFIG_PATH,
    ModelProfile,
    artifact_only_model_profiles,
    load_model_profile_registry,
    resolve_model_profile,
)


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER = SCRIPT_DIR / "render_malaysia_news_with_groq.py"
VALIDATOR = SCRIPT_DIR / "validate_malaysia_groq_merged_candidate.py"
COMPARISON_SCHEMA = "malaysia-groq-model-comparison/v1"
GOLDEN_SCHEMA = "malaysia-groq-model-migration-golden/v1"
QUALITY_REVIEW_CRITERIA = (
    "subject_preserved",
    "attribution_preserved",
    "state_and_certainty_preserved",
    "source_supported",
    "natural_japanese_entry",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def comparison_metrics(
    selected_count: int,
    improved: dict[str, Any] | None,
    validator: dict[str, Any] | None,
) -> dict[str, Any]:
    improved = improved or {}
    validator = validator or {}
    improved_counts = dict_value(improved.get("counts"))
    diagnostics = dict_value(improved.get("diagnostics"))
    fallback_counts = dict_value(diagnostics.get("json_render_fallback_counts"))
    entry_contract = dict_value(diagnostics.get("entry_candidate_observation"))
    entry_review = dict_value(diagnostics.get("entry_review_observation"))
    provenance = dict_value(diagnostics.get("json_render_summary_provenance"))
    provenance_line_counts = dict_value(provenance.get("line_counts"))
    validator_counts = dict_value(validator.get("counts"))
    url_validation = dict_value(validator.get("url_validation"))
    markdown_validation = dict_value(validator.get("markdown_validation"))

    requested = int_value(improved_counts.get("requested"))
    accepted = int_value(improved_counts.get("accepted"))
    request_fallback = int_value(improved_counts.get("fallback"))
    topic_fallback = int_value(fallback_counts.get("topic_fallback_count"))
    generic_fallback = int_value(fallback_counts.get("generic_fallback_count"))
    rendered_count = int_value(validator_counts.get("rendered_urls"))
    missing_count = len(list_value(url_validation.get("missing_selected_urls")))
    forbidden_matches = [str(value) for value in list_value(markdown_validation.get("forbidden_matches"))]
    entry_complete = int_value(entry_contract.get("entry_contract_complete_count"))
    reviewed_available = int_value(entry_review.get("reviewed_entry_available_count"))
    rss_lines = int_value(provenance_line_counts.get("rss_derived"))
    replaced_lines = int_value(provenance_line_counts.get("groq_replaced"))
    inherited_lines = int_value(provenance_line_counts.get("groq_inherited"))
    total_lines = rss_lines + replaced_lines + inherited_lines

    url_retention_rate = (
        safe_ratio(max(selected_count - missing_count, 0), selected_count) if validator else None
    )
    has_improved = bool(improved)
    has_validator = bool(validator)
    return {
        "selected_count": selected_count,
        "rendered_count": rendered_count,
        "url_retention_rate": url_retention_rate,
        "validator_passed": validator.get("passed") is True if has_validator else None,
        "validator_pass_rate": (
            1.0 if validator.get("passed") is True else 0.0 if has_validator else None
        ),
        "requested_count": requested,
        "accepted_count": accepted,
        "accepted_rate_of_requested": safe_ratio(accepted, requested) if has_improved else None,
        "request_fallback_count": request_fallback,
        "request_fallback_rate": safe_ratio(request_fallback, requested) if has_improved else None,
        "topic_fallback_count": topic_fallback,
        "generic_fallback_count": generic_fallback,
        "selected_fallback_rate": (
            safe_ratio(topic_fallback + generic_fallback, selected_count) if has_improved else None
        ),
        "forbidden_expression_count": len(forbidden_matches),
        "forbidden_expressions": forbidden_matches,
        "entry_contract_complete_count": entry_complete,
        "entry_contract_complete_rate_of_requested": (
            safe_ratio(entry_complete, requested) if has_improved else None
        ),
        "reviewed_entry_available_count": reviewed_available,
        "reviewed_entry_available_rate_of_requested": (
            safe_ratio(reviewed_available, requested) if has_improved else None
        ),
        "groq_replaced_summary_line_count": replaced_lines,
        "groq_inherited_summary_line_count": inherited_lines,
        "groq_replaced_summary_line_rate": safe_ratio(replaced_lines, total_lines) if has_improved else None,
    }


def accepted_summaries_by_link(improved: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not improved:
        return result
    for item in list_value(improved.get("items")):
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        summary = item.get("improved_summary")
        if isinstance(link, str) and link and isinstance(summary, dict):
            result[link] = summary
    return result


def decisions_by_link(improved: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    diagnostics = dict_value((improved or {}).get("diagnostics"))
    result: dict[str, dict[str, Any]] = {}
    for record in list_value(diagnostics.get("decision_records")):
        if isinstance(record, dict) and isinstance(record.get("link"), str):
            result[record["link"]] = record
    return result


def profile_result(
    profile: ModelProfile,
    role: str,
    run_status: str,
    selected_count: int,
    improved_path: Path,
    candidate_path: Path,
    validator_path: Path,
) -> dict[str, Any]:
    improved = load_optional_json(improved_path)
    validator = load_optional_json(validator_path)
    return {
        "profile": profile.name,
        "model_id": profile.model_id,
        "role": role,
        "artifact_only": role == "artifact-only",
        "preview": profile.preview,
        "run_status": run_status,
        "paths": {
            "improved_items": str(improved_path),
            "candidate_markdown": str(candidate_path),
            "validator_status": str(validator_path),
        },
        "metrics": comparison_metrics(selected_count, improved, validator),
        "accepted_summaries": accepted_summaries_by_link(improved),
        "decisions": decisions_by_link(improved),
    }


def markdown_text(value: Any) -> str:
    if isinstance(value, list):
        value = " / ".join(str(item) for item in value if str(item).strip())
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def percentage_text(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "n/a"
    return f"{value:.1%}"


def validator_text(value: Any) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "n/a"


def read_status(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or "unavailable"
    except OSError:
        return "unavailable"


def write_comparison_report(path: Path, report: dict[str, Any], selected: dict[str, Any]) -> None:
    profiles = list_value(report.get("profiles"))
    lines = [
        "# Malaysia Groq model comparison",
        "",
        "- observation_only: true",
        f"- generated_at: {report.get('generated_at')}",
        f"- selected_count: {report.get('selected_count')}",
        "- production_changed: false",
        "- prompt_changed: false",
        "- validator_changed: false",
        "",
        "## Fixed metrics",
        "",
        "| Profile | Role | Run | URL retention | Validator | Accepted/requested | Request fallback | Selected fallback | Forbidden | Entry contract complete | Reviewed entry available |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in profiles:
        if not isinstance(result, dict):
            continue
        metrics = dict_value(result.get("metrics"))
        lines.append(
            "| {profile} | {role} | {run} | {retention} | {validator} | {accepted}/{requested} ({accepted_rate}) | {fallback}/{requested} ({fallback_rate}) | {selected_fallback} | {forbidden} | {entry_rate} | {reviewed_rate} |".format(
                profile=markdown_text(result.get("profile")),
                role=markdown_text(result.get("role")),
                run=markdown_text(result.get("run_status")),
                retention=percentage_text(metrics.get("url_retention_rate")),
                validator=validator_text(metrics.get("validator_passed")),
                accepted=int_value(metrics.get("accepted_count")),
                requested=int_value(metrics.get("requested_count")),
                accepted_rate=percentage_text(metrics.get("accepted_rate_of_requested")),
                fallback=int_value(metrics.get("request_fallback_count")),
                fallback_rate=percentage_text(metrics.get("request_fallback_rate")),
                selected_fallback=percentage_text(metrics.get("selected_fallback_rate")),
                forbidden=int_value(metrics.get("forbidden_expression_count")),
                entry_rate=percentage_text(metrics.get("entry_contract_complete_rate_of_requested")),
                reviewed_rate=percentage_text(metrics.get("reviewed_entry_available_rate_of_requested")),
            )
        )

    lines.extend(
        [
            "",
            "## Summary quality proxies",
            "",
            "| Profile | Groq-replaced line rate | Replaced lines | Inherited lines |",
            "|---|---:|---:|---:|",
        ]
    )
    for result in profiles:
        if not isinstance(result, dict):
            continue
        metrics = dict_value(result.get("metrics"))
        lines.append(
            "| {profile} | {rate} | {replaced} | {inherited} |".format(
                profile=markdown_text(result.get("profile")),
                rate=percentage_text(metrics.get("groq_replaced_summary_line_rate")),
                replaced=int_value(metrics.get("groq_replaced_summary_line_count")),
                inherited=int_value(metrics.get("groq_inherited_summary_line_count")),
            )
        )

    lines.extend(
        [
            "",
            "## Quality review contract",
            "",
            "These criteria are fixed for manual review and are not an automatic promotion gate:",
            "",
            *[f"- {criterion}" for criterion in QUALITY_REVIEW_CRITERIA],
            "",
            "## Item-level review",
            "",
        ]
    )
    for index, item in enumerate(list_value(selected.get("items")), start=1):
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "")
        lines.extend(
            [
                f"### {index}. {markdown_text(item.get('title'))}",
                "",
                f"- source: {markdown_text(item.get('source'))}",
                f"- url: {link}",
                "",
                "| Profile | Decision | Contract | Conclusion | What happened | Life impact |",
                "|---|---|---|---|---|---|",
            ]
        )
        for result in profiles:
            if not isinstance(result, dict):
                continue
            decisions = dict_value(result.get("decisions"))
            summaries = dict_value(result.get("accepted_summaries"))
            record = dict_value(decisions.get(link))
            summary = dict_value(summaries.get(link))
            decision = record.get("decision") or "unavailable"
            reason = record.get("reason")
            if reason:
                decision = f"{decision}: {reason}"
            lines.append(
                "| {profile} | {decision} | {contract} | {conclusion} | {what_happened} | {life_impact} |".format(
                    profile=markdown_text(result.get("profile")),
                    decision=markdown_text(decision),
                    contract=markdown_text(record.get("entry_contract_status")),
                    conclusion=markdown_text(summary.get("conclusion")),
                    what_happened=markdown_text(summary.get("what_happened")),
                    life_impact=markdown_text(summary.get("life_impact")),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Boundary",
            "",
            "- Candidate profiles are artifact-only.",
            "- No comparison result can overwrite production.",
            "- RSS-only rollback: set MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def golden_item(item: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = (
        "category",
        "source",
        "published_date",
        "title",
        "description",
        "link",
        "selected_summary",
        "tags",
        "flags",
        "body_excerpt_policy",
        "body_evidence_excerpt",
        "body_evidence_focus",
        "body_evidence_forbidden",
    )
    return {field: copy.deepcopy(item[field]) for field in allowed_fields if field in item}


def update_golden_fixture(
    path: Path,
    selected: dict[str, Any],
    baseline_improved: dict[str, Any] | None,
    production_profile: ModelProfile,
    observed_on: str,
) -> int:
    if not baseline_improved:
        return 0
    if path.exists():
        value = load_json(path)
        if value.get("schema_version") != GOLDEN_SCHEMA:
            raise ValueError("unsupported golden fixture schema")
    else:
        value = {
            "schema_version": GOLDEN_SCHEMA,
            "description": "Production Groq fallback articles retained for model migration regression checks.",
            "items": [],
        }

    stored_items = list_value(value.get("items"))
    stored_by_link = {
        entry.get("link"): entry
        for entry in stored_items
        if isinstance(entry, dict) and isinstance(entry.get("link"), str)
    }
    selected_by_link = {
        item.get("link"): item
        for item in list_value(selected.get("items"))
        if isinstance(item, dict) and isinstance(item.get("link"), str)
    }
    added = 0
    changed = False
    for record in decisions_by_link(baseline_improved).values():
        if not record.get("requested") or record.get("accepted") or record.get("decision") != "fallback":
            continue
        link = record.get("link")
        item = selected_by_link.get(link)
        if not isinstance(link, str) or not isinstance(item, dict):
            continue
        reason = str(record.get("reason") or "fallback")
        existing = stored_by_link.get(link)
        if isinstance(existing, dict):
            reasons = [str(value) for value in list_value(existing.get("failure_reasons"))]
            if reason not in reasons:
                existing["failure_reasons"] = sorted([*reasons, reason])
                changed = True
            continue
        entry = {
            "link": link,
            "first_observed_on": observed_on,
            "production_profile": production_profile.name,
            "failure_reasons": [reason],
            "item": golden_item(item),
        }
        stored_items.append(entry)
        stored_by_link[link] = entry
        added += 1
        changed = True

    if changed:
        value["items"] = stored_items
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def run_command(command: list[str], stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        completed = subprocess.run(command, stdout=stdout_file, stderr=stderr_file, check=False)
    return completed.returncode


def run_artifact_profile(
    profile: ModelProfile,
    args: argparse.Namespace,
    selected_count: int,
) -> dict[str, Any]:
    profile_dir = args.output_dir / profile.artifact_key
    profile_dir.mkdir(parents=True, exist_ok=True)
    improved_path = profile_dir / "groq_improved_items.json"
    candidate_path = profile_dir / "groq_json_render_candidate.md"
    validator_path = profile_dir / "groq_json_render_validator_status.json"
    validator_report = profile_dir / "groq_json_render_validator_report.md"
    run_status_path = profile_dir / "run_status.txt"

    if not os.environ.get("GROQ_API_KEY"):
        run_status_path.write_text("skipped_missing_groq_api_key\n", encoding="utf-8")
        return profile_result(
            profile,
            "artifact-only",
            "skipped_missing_groq_api_key",
            selected_count,
            improved_path,
            candidate_path,
            validator_path,
        )

    command = [
        sys.executable,
        "-B",
        str(RENDERER),
        "--json-input",
        str(args.json_input),
        "--rss-markdown-input",
        str(args.rss_markdown_input),
        "--output",
        str(profile_dir / "groq_merged_candidate.md"),
        "--model",
        profile.model_id,
        "--improved-items-output",
        str(improved_path),
        "--json-render-output",
        str(candidate_path),
        "--entry-render-output",
        str(profile_dir / "groq_entry_render_candidate.md"),
        "--reviewed-entry-render-output",
        str(profile_dir / "groq_reviewed_entry_render_candidate.md"),
        "--merge-accepted-with-rss-markdown",
    ]
    if args.force_all:
        command.append("--force-all")
    if args.debug_groq:
        command.append("--debug-groq")
    render_code = run_command(command, profile_dir / "renderer_stdout.log", profile_dir / "renderer_stderr.log")
    if render_code != 0:
        run_status = f"renderer_failed_{render_code}"
        run_status_path.write_text(run_status + "\n", encoding="utf-8")
        return profile_result(
            profile,
            "artifact-only",
            run_status,
            selected_count,
            improved_path,
            candidate_path,
            validator_path,
        )

    validator_command = [
        sys.executable,
        "-B",
        str(VALIDATOR),
        "--selected-json",
        str(args.selected_json),
        "--candidate-markdown",
        str(candidate_path),
        "--improved-items-json",
        str(improved_path),
        "--rss-fallback-markdown",
        str(args.rss_markdown_input),
        "--status-output",
        str(validator_path),
        "--report-output",
        str(validator_report),
    ]
    validator_code = run_command(
        validator_command,
        profile_dir / "validator_stdout.log",
        profile_dir / "validator_stderr.log",
    )
    run_status = "success" if validator_code == 0 else f"validator_failed_{validator_code}"
    run_status_path.write_text(run_status + "\n", encoding="utf-8")
    return profile_result(
        profile,
        "artifact-only",
        run_status,
        selected_count,
        improved_path,
        candidate_path,
        validator_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--selected-json", type=Path, required=True)
    parser.add_argument("--json-input", type=Path, required=True)
    parser.add_argument("--rss-markdown-input", type=Path, required=True)
    parser.add_argument("--baseline-profile", required=True)
    parser.add_argument("--baseline-improved-items", type=Path, required=True)
    parser.add_argument("--baseline-candidate", type=Path, required=True)
    parser.add_argument("--baseline-validator-status", type=Path, required=True)
    parser.add_argument("--baseline-run-status-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--golden-fixture", type=Path, required=True)
    parser.add_argument("--force-all", action="store_true")
    parser.add_argument("--debug-groq", action="store_true")
    args = parser.parse_args()

    registry = load_model_profile_registry(args.profile_config)
    baseline_profile = resolve_model_profile(args.baseline_profile, registry)
    if baseline_profile.artifact_only:
        raise ValueError("baseline profile must be production-eligible")
    selected = load_json(args.selected_json)
    selected_count = len(list_value(selected.get("items")))
    baseline_improved = load_optional_json(args.baseline_improved_items)

    profiles = [
        profile_result(
            baseline_profile,
            "production-baseline",
            read_status(args.baseline_run_status_file),
            selected_count,
            args.baseline_improved_items,
            args.baseline_candidate,
            args.baseline_validator_status,
        )
    ]
    for profile in artifact_only_model_profiles(registry):
        profiles.append(run_artifact_profile(profile, args, selected_count))

    generated_at = datetime.now(tz=ZoneInfo("UTC")).replace(microsecond=0).isoformat()
    report = {
        "schema_version": COMPARISON_SCHEMA,
        "generated_at": generated_at,
        "observation_only": True,
        "selected_count": selected_count,
        "fixed_quality_review_criteria": list(QUALITY_REVIEW_CRITERIA),
        "profiles": profiles,
        "production_boundary": {
            "production_changed": False,
            "comparison_can_overwrite_production": False,
            "rss_only_rollback_variable": "MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false",
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_comparison_report(args.report_output, report, selected)

    observed_on = datetime.now(tz=ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
    added = update_golden_fixture(
        args.golden_fixture,
        load_optional_json(args.json_input) or selected,
        baseline_improved,
        baseline_profile,
        observed_on,
    )
    statuses = [str(dict_value(result).get("run_status") or "unavailable") for result in profiles[1:]]
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(
        json.dumps(
            {
                "observation_only": True,
                "artifact_profile_statuses": statuses,
                "golden_fixture_items_added": added,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
