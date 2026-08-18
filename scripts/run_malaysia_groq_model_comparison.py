#!/usr/bin/env python3
"""Compare Groq model profiles against the Editorial Entry v2 contract."""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
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
from malaysia_groq_output_contract import EDITORIAL_ENTRY_V2_SCHEMA, editorial_entry_schema_error
from malaysia_groq_transport import error_diagnostic, request_chat_completion
from render_malaysia_news_with_groq import EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER = SCRIPT_DIR / "render_malaysia_news_with_groq.py"
VALIDATOR = SCRIPT_DIR / "validate_malaysia_groq_merged_candidate.py"
COMPARISON_SCHEMA = "malaysia-groq-model-comparison/v3"
GOLDEN_SCHEMA = "malaysia-groq-model-migration-golden/v1"
PROBE_FIXTURE = SCRIPT_DIR / "fixtures" / "malaysia_groq_model_compatibility_probe.json"
QUALITY_COHORT_SIZE = 2
MAX_RATE_RESET_WAIT_SECONDS = 60
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


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def counter_dict(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def comparison_request_configuration(profile: ModelProfile) -> dict[str, Any]:
    return {
        "prompt_layout": profile.comparison_prompt_layout,
        "max_tokens": profile.comparison_max_tokens,
        "contract": profile.comparison_contract,
        "response_mode": profile.response_mode,
        "reasoning_mode": profile.reasoning_mode,
    }


def compatibility_probe_messages(profile: ModelProfile, item: dict[str, Any]) -> list[dict[str, str]]:
    article_json = json.dumps(item, ensure_ascii=False)
    prompt = (
        "Use only the supplied article. Return one Japanese editorial entry that preserves "
        "subject, attribution, and certainty.\n\n"
        f"{EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION}"
    )
    if profile.comparison_prompt_layout == "production":
        return [{"role": "system", "content": prompt}, {"role": "user", "content": article_json}]
    return [{"role": "user", "content": f"{prompt}\n\nInput article JSON:\n{article_json}"}]


def wait_for_rate_reset(diagnostic: dict[str, Any]) -> str:
    rate_limit = dict_value(diagnostic.get("rate_limit"))
    raw = str(rate_limit.get("reset_tokens") or "")
    import re

    match = re.fullmatch(r"(?:(\d+)m)?(\d+(?:\.\d+)?)s", raw)
    if not match:
        return "not_needed"
    wait = int(match.group(1) or "0") * 60 + float(match.group(2))
    if wait > MAX_RATE_RESET_WAIT_SECONDS:
        return "rate_budget_deferred"
    if wait > 0:
        time.sleep(wait)
    return "waited" if wait > 0 else "not_needed"


def probe_status_from_diagnostic(diagnostic: dict[str, Any]) -> str:
    error = dict_value(diagnostic.get("error"))
    if error.get("code") == "json_validate_failed":
        return "contract_failed"
    status = str(diagnostic.get("transport_status") or "")
    if status in {"success", "invalid_envelope"}:
        return "contract_failed"
    return "transport_failed"


def run_compatibility_probe(profile: ModelProfile, api_key: str, path: Path) -> dict[str, Any]:
    fixture = load_json(PROBE_FIXTURE)
    item = dict_value(fixture.get("item"))
    if not item:
        raise ValueError("compatibility probe fixture is missing item")
    try:
        completion = request_chat_completion(
            profile=profile,
            messages=compatibility_probe_messages(profile, item),
            temperature=0.0,
            max_tokens=profile.comparison_max_tokens,
            timeout_seconds=30,
            max_response_chars=4000,
            json_schema_name="malaysia_news_editorial_entry_v2",
            json_schema=EDITORIAL_ENTRY_V2_SCHEMA,
            schema_error=editorial_entry_schema_error,
            api_key=api_key,
        )
        diagnostic = completion.diagnostic
        result = {
            "probe_status": "passed" if diagnostic.get("json_contract_status") == "valid" else "contract_failed",
            "request_configuration": comparison_request_configuration(profile),
            "diagnostic": diagnostic,
            "parsed_root_keys": sorted(completion.parsed) if isinstance(completion.parsed, dict) else [],
            "rate_wait": wait_for_rate_reset(diagnostic),
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        diagnostic = error_diagnostic(error) or {}
        result = {
            "probe_status": probe_status_from_diagnostic(diagnostic),
            "request_configuration": comparison_request_configuration(profile),
            "diagnostic": diagnostic,
            "rate_wait": "not_needed",
        }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def decision_records(improved: dict[str, Any] | None) -> list[dict[str, Any]]:
    diagnostics = dict_value((improved or {}).get("diagnostics"))
    return [record for record in list_value(diagnostics.get("decision_records")) if isinstance(record, dict)]


def quality_cohort_links(improved: dict[str, Any] | None) -> list[str]:
    records = [
        record
        for record in decision_records(improved)
        if record.get("requested") is True and isinstance(record.get("link"), str) and record["link"]
    ]
    records.sort(key=lambda record: int_value(record.get("index")) or sys.maxsize)
    return [record["link"] for record in records[:QUALITY_COHORT_SIZE]]


def transport_observation(improved: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    records = [record for record in decision_records(improved) if record.get("requested") is True]
    calls = [dict_value(record.get("groq_call")) for record in records]
    return {
        "transport_status_counts": counter_dict([str(call.get("transport_status") or "not_recorded") for call in calls]),
        "json_contract_status_counts": counter_dict([str(call.get("json_contract_status") or "not_evaluated") for call in calls]),
        "semantic_gate_status_counts": counter_dict(
            [
                "accepted" if record.get("accepted") is True
                else "hard_safety_rejected" if record.get("hard_safety_rejection_reason")
                else "not_accepted"
                for record in records
            ]
        ),
    }


def comparison_metrics(
    selected_count: int,
    improved: dict[str, Any] | None,
    validator: dict[str, Any] | None,
    cohort_links: list[str],
) -> dict[str, Any]:
    counts = dict_value((improved or {}).get("counts"))
    diagnostics = dict_value((improved or {}).get("diagnostics"))
    entry_counts = dict_value(diagnostics.get("editorial_entry_counts"))
    provenance = dict_value(diagnostics.get("editorial_entry_provenance"))
    line_counts = dict_value(provenance.get("line_counts"))
    validator_counts = dict_value((validator or {}).get("counts"))
    url_validation = dict_value((validator or {}).get("url_validation"))
    records = decision_records(improved)
    wanted = set(cohort_links)
    cohort_records = [record for record in records if record.get("link") in wanted]
    requested = int_value(counts.get("requested"))
    accepted = int_value(counts.get("accepted"))
    fallback = int_value(counts.get("fallback"))
    missing = len(list_value(url_validation.get("missing_selected_urls")))
    replaced = int_value(line_counts.get("groq_replaced"))
    inherited = int_value(line_counts.get("groq_inherited"))
    total_model_lines = replaced + inherited
    return {
        "selected_count": selected_count,
        "rendered_count": int_value(validator_counts.get("rendered_urls")),
        "url_retention_rate": safe_ratio(max(selected_count - missing, 0), selected_count) if validator else None,
        "validator_passed": (validator or {}).get("passed") if validator else None,
        "requested_count": requested,
        "accepted_count": accepted,
        "accepted_rate_of_requested": safe_ratio(accepted, requested) if improved else None,
        "request_fallback_count": fallback,
        "request_fallback_rate": safe_ratio(fallback, requested) if improved else None,
        "rss_fallback_count": int_value(entry_counts.get("rss_fallback_count")),
        "rss_fallback_rate": safe_ratio(int_value(entry_counts.get("rss_fallback_count")), selected_count) if improved else None,
        "forbidden_expression_count": len(list_value(dict_value((validator or {}).get("markdown_validation")).get("forbidden_matches"))),
        "quality_cohort": {
            "cohort_size": len(cohort_links),
            "requested_count": sum(record.get("requested") is True for record in cohort_records),
            "accepted_count": sum(record.get("accepted") is True for record in cohort_records),
        },
        "groq_replaced_entry_line_count": replaced,
        "groq_inherited_entry_line_count": inherited,
        "groq_replaced_entry_line_rate": safe_ratio(replaced, total_model_lines) if improved else None,
        **transport_observation(improved),
    }


def entries_by_link(improved: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in list_value((improved or {}).get("items")):
        if isinstance(item, dict) and isinstance(item.get("link"), str) and isinstance(item.get("improved_editorial_entry"), dict):
            result[item["link"]] = item["improved_editorial_entry"]
    return result


def decisions_by_link(improved: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        record["link"]: record
        for record in decision_records(improved)
        if isinstance(record.get("link"), str)
    }


def profile_result(
    profile: ModelProfile,
    role: str,
    run_status: str,
    selected_count: int,
    improved_path: Path,
    candidate_path: Path,
    validator_path: Path,
    cohort_links: list[str],
    probe_path: Path | None = None,
) -> dict[str, Any]:
    improved = load_optional_json(improved_path)
    validator = load_optional_json(validator_path)
    probe = load_optional_json(probe_path) if probe_path else None
    diagnostic = dict_value(dict_value(probe).get("diagnostic"))
    error = dict_value(diagnostic.get("error"))
    metrics = comparison_metrics(selected_count, improved, validator, cohort_links)
    return {
        "profile": profile.name,
        "model_id": profile.model_id,
        "role": role,
        "artifact_only": role == "artifact-only",
        "comparison_request_configuration": comparison_request_configuration(profile),
        "run_status": run_status,
        "probe_status": (probe or {}).get("probe_status", "not_applicable"),
        "probe_transport_status": diagnostic.get("transport_status", "not_applicable"),
        "probe_json_contract_status": diagnostic.get("json_contract_status", "not_applicable"),
        "probe_error_code": error.get("code", ""),
        "quality_cohort_links": cohort_links,
        "metrics": metrics,
        "transport_status_counts": metrics["transport_status_counts"],
        "json_contract_status_counts": metrics["json_contract_status_counts"],
        "semantic_gate_status_counts": metrics["semantic_gate_status_counts"],
        "accepted_entries": entries_by_link(improved),
        "decisions": decisions_by_link(improved),
    }


def run_command(command: list[str], stdout: Path, stderr: Path) -> int:
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        return subprocess.run(command, stdout=out, stderr=err, check=False).returncode


def run_artifact_profile(profile: ModelProfile, args: argparse.Namespace, selected_count: int, cohort_links: list[str]) -> dict[str, Any]:
    directory = args.output_dir / profile.artifact_key
    directory.mkdir(parents=True, exist_ok=True)
    improved = directory / "groq_improved_items.json"
    candidate = directory / "groq_json_render_candidate.md"
    validator = directory / "groq_json_render_validator_status.json"
    report = directory / "groq_json_render_validator_report.md"
    run_status_path = directory / "run_status.txt"
    probe_path = directory / "compatibility_probe.json"
    if not os.environ.get("GROQ_API_KEY"):
        run_status_path.write_text("skipped_missing_groq_api_key\n", encoding="utf-8")
        return profile_result(profile, "artifact-only", "skipped_missing_groq_api_key", selected_count, improved, candidate, validator, cohort_links, probe_path)
    probe = run_compatibility_probe(profile, os.environ["GROQ_API_KEY"], probe_path)
    if probe.get("probe_status") != "passed":
        run_status_path.write_text("probe_failed\n", encoding="utf-8")
        return profile_result(profile, "artifact-only", "probe_failed", selected_count, improved, candidate, validator, cohort_links, probe_path)
    if probe.get("rate_wait") == "rate_budget_deferred":
        run_status_path.write_text("rate_budget_deferred\n", encoding="utf-8")
        return profile_result(profile, "artifact-only", "rate_budget_deferred", selected_count, improved, candidate, validator, cohort_links, probe_path)
    if not cohort_links:
        # The probe remains useful for contract observation, but there is no fair
        # production cohort to send when the baseline did not request any article.
        run_status_path.write_text("skipped_no_quality_cohort\n", encoding="utf-8")
        return profile_result(profile, "artifact-only", "skipped_no_quality_cohort", selected_count, improved, candidate, validator, cohort_links, probe_path)
    command = [
        sys.executable, "-B", str(RENDERER),
        "--json-input", str(args.json_input),
        "--output", str(candidate),
        "--model", profile.model_id,
        "--summary-prompt-layout", profile.comparison_prompt_layout,
        "--summary-max-tokens", str(profile.comparison_max_tokens),
        "--summary-contract", profile.comparison_contract,
        "--improved-items-output", str(improved),
        "--request-link-allowlist", str(args.cohort_output),
        "--rate-reset-wait-max-seconds", str(MAX_RATE_RESET_WAIT_SECONDS),
        "--max-429-retry-after-seconds", str(MAX_RATE_RESET_WAIT_SECONDS),
    ]
    if args.debug_groq:
        command.append("--debug-groq")
    if run_command(command, directory / "renderer_stdout.log", directory / "renderer_stderr.log") != 0:
        run_status_path.write_text("renderer_failed\n", encoding="utf-8")
        return profile_result(profile, "artifact-only", "renderer_failed", selected_count, improved, candidate, validator, cohort_links, probe_path)
    validator_command = [
        sys.executable, "-B", str(VALIDATOR),
        "--selected-json", str(args.selected_json),
        "--candidate-markdown", str(candidate),
        "--improved-items-json", str(improved),
        "--rss-fallback-markdown", str(args.rss_markdown_input),
        "--status-output", str(validator),
        "--report-output", str(report),
    ]
    run_command(validator_command, directory / "validator_stdout.log", directory / "validator_stderr.log")
    records = decision_records(load_optional_json(improved))
    status = "quality_completed" if sum(record.get("requested") is True for record in records) == len(cohort_links) else "quality_partial"
    if any(record.get("reason") == "rate_budget_deferred" for record in records):
        status = "rate_budget_deferred"
    run_status_path.write_text(status + "\n", encoding="utf-8")
    return profile_result(profile, "artifact-only", status, selected_count, improved, candidate, validator, cohort_links, probe_path)


def update_golden_fixture(path: Path, selected: dict[str, Any], improved: dict[str, Any] | None, profile: ModelProfile, observed_on: str) -> int:
    existing = load_optional_json(path) or {
        "schema_version": GOLDEN_SCHEMA,
        "description": "Production failures retained for future model migration checks.",
        "items": [],
    }
    rows = [row for row in list_value(existing.get("items")) if isinstance(row, dict)]
    known = {str(row.get("link") or "") for row in rows}
    selected_by_link = {
        str(item.get("link") or ""): item
        for item in list_value(selected.get("items"))
        if isinstance(item, dict) and item.get("link")
    }
    added = 0
    for record in decision_records(improved):
        link = str(record.get("link") or "")
        if not link or link in known or record.get("accepted") is True or not record.get("requested"):
            continue
        rows.append(
            {
                "link": link,
                "first_observed_on": observed_on,
                "production_profile": profile.name,
                "failure_reasons": [str(record.get("reason") or "unknown")],
                "item": selected_by_link.get(link, {"link": link}),
            }
        )
        known.add(link)
        added += 1
    existing["schema_version"] = GOLDEN_SCHEMA
    existing["items"] = rows
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def golden_fixture_observation(fixture: dict[str, Any] | None) -> dict[str, Any]:
    records = [row for row in list_value((fixture or {}).get("items")) if isinstance(row, dict)]
    reasons = [
        str(reason)
        for row in records
        for reason in list_value(row.get("failure_reasons"))
        if str(reason).strip()
    ]
    return {
        "observation_only": True,
        "fixture_item_count": len(records),
        "hard_safety_reason_counts": counter_dict([reason for reason in reasons if "unsafe" in reason.lower() or "unsupported" in reason.lower() or "english lead" in reason.lower()]),
        "other_failure_reason_counts": counter_dict([reason for reason in reasons if not ("unsafe" in reason.lower() or "unsupported" in reason.lower() or "english lead" in reason.lower())]),
    }


def markdown_text(value: Any) -> str:
    if isinstance(value, list):
        value = " / ".join(str(item) for item in value if str(item).strip())
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def percentage(value: Any) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def validator_text(value: Any) -> str:
    return "pass" if value is True else "fail" if value is False else "n/a"


def write_comparison_report(path: Path, report: dict[str, Any], selected: dict[str, Any]) -> None:
    profiles = [profile for profile in list_value(report.get("profiles")) if isinstance(profile, dict)]
    lines = [
        "# Malaysia Groq model comparison",
        "",
        "- observation_only: true",
        f"- selected_count: {report.get('selected_count')}",
        f"- quality_cohort_links: {', '.join(str(link) for link in list_value(report.get('quality_cohort_links')))}",
        "",
        "## Fixed Metrics",
        "",
        "| Profile | Run | URL retention | Validator | Accepted/requested | RSS fallback | Forbidden |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for result in profiles:
        metrics = dict_value(result.get("metrics"))
        lines.append(
            "| {profile} | {run} | {retention} | {validator} | {accepted}/{requested} ({rate}) | {fallback} | {forbidden} |".format(
                profile=markdown_text(result.get("profile")),
                run=markdown_text(result.get("run_status")),
                retention=percentage(metrics.get("url_retention_rate")),
                validator=validator_text(metrics.get("validator_passed")),
                accepted=int_value(metrics.get("accepted_count")),
                requested=int_value(metrics.get("requested_count")),
                rate=percentage(metrics.get("accepted_rate_of_requested")),
                fallback=int_value(metrics.get("rss_fallback_count")),
                forbidden=int_value(metrics.get("forbidden_expression_count")),
            )
        )
    lines.extend(["", "## Transport, Contract, Safety, Validator", "", "| Profile | Probe | Transport | JSON contract | Hard safety | Markdown validator |", "|---|---|---|---|---|---|"])
    for result in profiles:
        metrics = dict_value(result.get("metrics"))
        lines.append(
            "| {profile} | {probe} | {transport} | {contract} | {safety} | {validator} |".format(
                profile=markdown_text(result.get("profile")),
                probe=markdown_text(result.get("probe_status")),
                transport=markdown_text(metrics.get("transport_status_counts")),
                contract=markdown_text(metrics.get("json_contract_status_counts")),
                safety=markdown_text(metrics.get("semantic_gate_status_counts")),
                validator=validator_text(metrics.get("validator_passed")),
            )
        )
    lines.extend(["", "## Manual Review", "", *[f"- {criterion}" for criterion in QUALITY_REVIEW_CRITERIA]])
    for index, item in enumerate(list_value(selected.get("items")), start=1):
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "")
        lines.extend(["", f"### {index}. {markdown_text(item.get('title'))}", "", "| Profile | Decision | Entry | Supporting points |", "|---|---|---|---|"])
        for result in profiles:
            record = dict_value(dict_value(result.get("decisions")).get(link))
            entry = dict_value(dict_value(result.get("accepted_entries")).get(link))
            decision = str(record.get("decision") or "unavailable")
            if record.get("reason"):
                decision += f": {record['reason']}"
            lines.append(
                "| {profile} | {decision} | {entry} | {points} |".format(
                    profile=markdown_text(result.get("profile")),
                    decision=markdown_text(decision),
                    entry=markdown_text(entry.get("entry_ja")),
                    points=markdown_text(entry.get("supporting_points_ja")),
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser.add_argument("--force-all", action="store_true", help="Accepted for workflow compatibility; v2 ignores it.")
    parser.add_argument("--debug-groq", action="store_true")
    args = parser.parse_args()
    registry = load_model_profile_registry(args.profile_config)
    baseline = resolve_model_profile(args.baseline_profile, registry)
    if baseline.artifact_only:
        raise ValueError("baseline profile must be production-eligible")
    selected = load_json(args.selected_json)
    selected_count = len(list_value(selected.get("items")))
    baseline_improved = load_optional_json(args.baseline_improved_items)
    cohort_links = quality_cohort_links(baseline_improved)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cohort_output = args.output_dir / "comparison_cohort.json"
    args.cohort_output.write_text(json.dumps({"links": cohort_links}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    profiles = [
        profile_result(
            baseline,
            "production-baseline",
            args.baseline_run_status_file.read_text(encoding="utf-8").strip() if args.baseline_run_status_file.exists() else "unavailable",
            selected_count,
            args.baseline_improved_items,
            args.baseline_candidate,
            args.baseline_validator_status,
            cohort_links,
        )
    ]
    for profile in artifact_only_model_profiles(registry):
        profiles.append(run_artifact_profile(profile, args, selected_count, cohort_links))
    update_golden_fixture(
        args.golden_fixture,
        selected,
        baseline_improved,
        baseline,
        datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat(),
    )
    report = {
        "schema_version": COMPARISON_SCHEMA,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "selected_count": selected_count,
        "quality_cohort_links": cohort_links,
        "profiles": profiles,
        "golden_fixture_observation": golden_fixture_observation(load_optional_json(args.golden_fixture)),
    }
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.status_output.write_text(json.dumps({"passed": True, "schema_version": COMPARISON_SCHEMA}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_comparison_report(args.report_output, report, selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
