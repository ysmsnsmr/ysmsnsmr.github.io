#!/usr/bin/env python3
"""Run artifact-only Groq model profiles and build a fixed-metric comparison."""

import argparse
import copy
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
from malaysia_groq_output_contract import (
    SUMMARY_ENTRY_SCHEMA,
    SUMMARY_ONLY_SCHEMA,
    summary_entry_schema_error,
    summary_only_schema_error,
)
from malaysia_groq_transport import error_diagnostic, request_chat_completion
from render_malaysia_news_with_groq import USER_MESSAGE_JSON_CONTRACT


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER = SCRIPT_DIR / "render_malaysia_news_with_groq.py"
VALIDATOR = SCRIPT_DIR / "validate_malaysia_groq_merged_candidate.py"
COMPARISON_SCHEMA = "malaysia-groq-model-comparison/v2"
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
PROBE_PROMPT = "Return one concise Japanese news summary and entry using only the supplied source. Return JSON only."

GATE_REASON_HARD_SAFETY_MARKERS = (
    "unsafe ",
    "unsupported ",
    "english lead leakage",
    "forbidden",
)
GATE_REASON_USEFULNESS_MARKERS = (
    "no_strong_source_life_impact_signal",
    "no_strong_summary_life_impact_signal",
    "generic_life_impact",
    "generic life_impact for body_evidence focus",
    "transport_political_background_without_operational_impact",
    "transport_political_invitation_context",
    "money_market_background_without_concrete_life_impact",
    "paul_tan_noise_without_driver_impact",
    "paul_tan_no_transport_driver_signal",
)
GATE_REASON_TRANSPORT_OR_CONTRACT_MARKERS = (
    "http ",
    "429",
    "timeout",
    "network",
    "urlerror",
    "json",
    "schema",
    "contract",
    "missing_groq_api_key",
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


def comparison_request_configuration(profile: ModelProfile) -> dict[str, Any]:
    """Expose artifact-only request variations beside their comparison results."""
    return {
        "prompt_layout": profile.comparison_prompt_layout,
        "max_tokens": profile.comparison_max_tokens,
        "contract": profile.comparison_contract,
        "response_mode": profile.response_mode,
        "reasoning_mode": profile.reasoning_mode,
    }


def compatibility_probe_messages(profile: ModelProfile, item: dict[str, Any]) -> list[dict[str, str]]:
    """Keep the fixed probe stable while varying only a profile's requested transport shape."""
    article_json = json.dumps(item, ensure_ascii=False)
    if profile.comparison_prompt_layout == "production":
        return [
            {"role": "system", "content": PROBE_PROMPT},
            {"role": "user", "content": article_json},
        ]

    content = f"{PROBE_PROMPT}\n\nInput article JSON:\n{article_json}"
    if profile.comparison_prompt_layout == "user_only_explicit_contract":
        content = f"{PROBE_PROMPT}\n\n{USER_MESSAGE_JSON_CONTRACT}\n\nInput article JSON:\n{article_json}"
    return [{"role": "user", "content": content}]


def counter_dict(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def classify_gate_failure_reason(reason: Any) -> str:
    """Classify recorded failures without changing the production gate."""
    normalized = str(reason or "").strip().lower()
    if not normalized:
        return "unknown"
    if any(marker in normalized for marker in GATE_REASON_HARD_SAFETY_MARKERS):
        return "hard_safety"
    if any(marker in normalized for marker in GATE_REASON_USEFULNESS_MARKERS):
        return "usefulness"
    if any(marker in normalized for marker in GATE_REASON_TRANSPORT_OR_CONTRACT_MARKERS):
        return "transport_or_contract"
    return "unknown"


def golden_item_gate_observation(entry: dict[str, Any]) -> dict[str, Any]:
    reasons = [str(reason) for reason in list_value(entry.get("failure_reasons")) if str(reason).strip()]
    classifications = [classify_gate_failure_reason(reason) for reason in reasons]
    has_hard_safety = "hard_safety" in classifications
    has_usefulness = "usefulness" in classifications
    has_unavailable = any(
        classification in {"transport_or_contract", "unknown"}
        for classification in classifications
    )
    if has_hard_safety:
        safety_status = "reject"
    elif has_usefulness and not has_unavailable:
        safety_status = "pass"
    else:
        safety_status = "not_evaluated"
    if has_hard_safety:
        usefulness_status = "not_evaluated"
    elif has_usefulness and not has_unavailable:
        usefulness_status = "reject"
    else:
        usefulness_status = "not_evaluated"
    if has_hard_safety or has_usefulness:
        current_decision = "reject"
    else:
        current_decision = "not_evaluated"
    if has_hard_safety:
        hard_safety_only_accept_possible: bool | None = False
    elif has_usefulness and not has_unavailable:
        hard_safety_only_accept_possible = True
    else:
        hard_safety_only_accept_possible = None
    return {
        "safety_gate_status": safety_status,
        "usefulness_gate_status": usefulness_status,
        "current_gate_decision": current_decision,
        "hard_safety_only_accept_possible": hard_safety_only_accept_possible,
        "reason_classifications": classifications,
    }


def golden_fixture_gate_observation(fixture: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize the current-vs-hard-safety-only view of recorded fixture failures."""
    entries = [entry for entry in list_value((fixture or {}).get("items")) if isinstance(entry, dict)]
    observations: list[dict[str, Any]] = []
    reason_classes: list[str] = []
    safety_statuses: list[str] = []
    usefulness_statuses: list[str] = []
    decisions: list[str] = []
    hard_safety_only_count = 0
    for entry in entries:
        observation = golden_item_gate_observation(entry)
        reason_classes.extend(observation["reason_classifications"])
        safety_statuses.append(observation["safety_gate_status"])
        usefulness_statuses.append(observation["usefulness_gate_status"])
        decisions.append(observation["current_gate_decision"])
        if observation["hard_safety_only_accept_possible"] is True:
            hard_safety_only_count += 1
        observations.append(
            {
                "link": str(entry.get("link") or ""),
                "failure_reasons": [str(reason) for reason in list_value(entry.get("failure_reasons"))],
                **observation,
            }
        )
    return {
        "observation_only": True,
        "source": "recorded_golden_fixture_failure_reasons",
        "fixture_item_count": len(entries),
        "safety_gate_status_counts": counter_dict(safety_statuses),
        "usefulness_gate_status_counts": counter_dict(usefulness_statuses),
        "current_gate_decision_counts": counter_dict(decisions),
        "reason_class_counts": counter_dict(reason_classes),
        "hard_safety_only_accept_possible_count": hard_safety_only_count,
        "hard_safety_only_accept_possible_rate": safe_ratio(hard_safety_only_count, len(entries)),
        "items": observations,
    }


def decision_records(improved: dict[str, Any] | None) -> list[dict[str, Any]]:
    diagnostics = dict_value((improved or {}).get("diagnostics"))
    return [record for record in list_value(diagnostics.get("decision_records")) if isinstance(record, dict)]


def quality_cohort_links(improved: dict[str, Any] | None, limit: int = QUALITY_COHORT_SIZE) -> list[str]:
    requested = [
        record
        for record in decision_records(improved)
        if record.get("requested") is True and isinstance(record.get("link"), str) and record["link"]
    ]
    requested.sort(
        key=lambda record: (
            -int_value(record.get("force_all_priority")),
            int_value(record.get("index")) or sys.maxsize,
        )
    )
    return [record["link"] for record in requested[:limit]]


def transport_observation(improved: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    records = [record for record in decision_records(improved) if record.get("requested") is True]
    calls = [dict_value(record.get("groq_call")) for record in records]
    return {
        "transport_status_counts": counter_dict(
            [str(call.get("transport_status") or "not_recorded") for call in calls]
        ),
        "json_contract_status_counts": counter_dict(
            [str(call.get("json_contract_status") or "not_evaluated") for call in calls]
        ),
        "semantic_gate_status_counts": counter_dict(
            [
                "accepted"
                if record.get("accepted") is True
                else "rejected"
                if str(record.get("reason") or "").startswith("ValueError: force_all accepted gate:")
                else "not_accepted"
                for record in records
            ]
        ),
    }


def cohort_metrics(improved: dict[str, Any] | None, links: list[str]) -> dict[str, int]:
    wanted = set(links)
    records = [record for record in decision_records(improved) if record.get("link") in wanted]
    requested = [record for record in records if record.get("requested") is True]
    return {
        "cohort_size": len(links),
        "requested_count": len(requested),
        "accepted_count": sum(1 for record in requested if record.get("accepted") is True),
        "fallback_count": sum(1 for record in requested if record.get("decision") == "fallback"),
    }


def comparison_metrics(
    selected_count: int,
    improved: dict[str, Any] | None,
    validator: dict[str, Any] | None,
    cohort_links: list[str] | None = None,
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
    usefulness_gate = dict_value(diagnostics.get("usefulness_gate_observation"))
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
    review_disabled = entry_review.get("entry_review_policy") == "disabled_for_model_comparison"
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
            None if review_disabled else safe_ratio(reviewed_available, requested) if has_improved else None
        ),
        "entry_review_policy": entry_review.get("entry_review_policy") or "enabled",
        "usefulness_gate_status_counts": dict_value(usefulness_gate.get("status_counts")),
        "usefulness_gate_reason_counts": dict_value(usefulness_gate.get("reason_counts")),
        "json_render_display_tier_counts": dict_value(usefulness_gate.get("display_tier_counts")),
        "quality_cohort": cohort_metrics(improved, cohort_links or []),
        **transport_observation(improved),
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
    cohort_links: list[str],
    probe_path: Path | None = None,
) -> dict[str, Any]:
    improved = load_optional_json(improved_path)
    validator = load_optional_json(validator_path)
    probe = load_optional_json(probe_path) if probe_path else None
    probe_observation = probe_contract_observation(probe)
    metrics = comparison_metrics(selected_count, improved, validator, cohort_links)
    if role == "artifact-only" and not improved:
        metrics["entry_review_policy"] = "disabled_for_model_comparison"
        metrics["reviewed_entry_available_rate_of_requested"] = None
    return {
        "profile": profile.name,
        "model_id": profile.model_id,
        "role": role,
        "artifact_only": role == "artifact-only",
        "preview": profile.preview,
        "comparison_request_configuration": comparison_request_configuration(profile),
        "run_status": run_status,
        "paths": {
            "improved_items": str(improved_path),
            "candidate_markdown": str(candidate_path),
            "validator_status": str(validator_path),
            "compatibility_probe": str(probe_path) if probe_path else "",
        },
        "probe_status": probe.get("probe_status") if isinstance(probe, dict) else "not_applicable",
        "probe_transport_status": probe_observation["transport_status"],
        "probe_json_contract_status": probe_observation["json_contract_status"],
        "probe_contract_observation": probe_observation["contract_observation"],
        "probe_error_code": probe_observation["error_code"],
        "probe": probe or {},
        "quality_cohort_links": cohort_links,
        "entry_review_policy": metrics.get("entry_review_policy"),
        "transport_status_counts": metrics.get("transport_status_counts"),
        "json_contract_status_counts": metrics.get("json_contract_status_counts"),
        "semantic_gate_status_counts": metrics.get("semantic_gate_status_counts"),
        "metrics": metrics,
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
        f"- quality_cohort_links: {', '.join(str(link) for link in list_value(report.get('quality_cohort_links')))}",
        "- production_changed: false",
        "- production_prompt_changed: false",
        "- validator_changed: false",
        "",
        "## Fixed metrics",
        "",
        "| Profile | Role | Run | URL retention | Validator | Accepted/requested | Request fallback | Selected fallback | Forbidden | Entry contract complete | Entry review |",
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
                reviewed_rate=(
                    "not_run"
                    if metrics.get("entry_review_policy") == "disabled_for_model_comparison"
                    else percentage_text(metrics.get("reviewed_entry_available_rate_of_requested"))
                ),
            )
        )

    lines.extend(
        [
            "",
            "## Usefulness gate observation",
            "",
            "Usefulness warnings do not reject the summary in force-all comparison; the display tier may limit the life-impact field. Hard safety failures remain rejected.",
            "",
            "| Profile | Usefulness status | Display tier | Reasons |",
            "|---|---|---|---|",
        ]
    )
    for result in profiles:
        if not isinstance(result, dict):
            continue
        metrics = dict_value(result.get("metrics"))
        lines.append(
            "| {profile} | {status} | {tier} | {reasons} |".format(
                profile=markdown_text(result.get("profile")),
                status=markdown_text(metrics.get("usefulness_gate_status_counts")),
                tier=markdown_text(metrics.get("json_render_display_tier_counts")),
                reasons=markdown_text(metrics.get("usefulness_gate_reason_counts")),
            )
        )

    lines.extend(
        [
            "",
            "## Candidate request configuration",
            "",
            "| Profile | Prompt layout | Contract | Max tokens | Response mode | Reasoning mode |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for result in profiles:
        if not isinstance(result, dict):
            continue
        configuration = dict_value(result.get("comparison_request_configuration"))
        lines.append(
            "| {profile} | {prompt_layout} | {contract} | {max_tokens} | {response_mode} | {reasoning_mode} |".format(
                profile=markdown_text(result.get("profile")),
                prompt_layout=markdown_text(configuration.get("prompt_layout")),
                contract=markdown_text(configuration.get("contract")),
                max_tokens=int_value(configuration.get("max_tokens")),
                response_mode=markdown_text(configuration.get("response_mode")),
                reasoning_mode=markdown_text(configuration.get("reasoning_mode")),
            )
        )

    lines.extend(
        [
            "",
            "## Transport and JSON contract",
            "",
            "| Profile | Probe | Probe transport | Probe JSON contract | Probe detail | Cohort accepted/requested | Transport | JSON contract | Semantic gate | Markdown validator |",
            "|---|---|---|---|---|---:|---|---|---|---:|",
        ]
    )
    for result in profiles:
        if not isinstance(result, dict):
            continue
        metrics = dict_value(result.get("metrics"))
        cohort = dict_value(metrics.get("quality_cohort"))
        lines.append(
            "| {profile} | {probe} | {probe_transport} | {probe_contract} | {probe_detail} | {accepted}/{requested} | {transport} | {contract} | {gate} | {validator} |".format(
                profile=markdown_text(result.get("profile")),
                probe=markdown_text(result.get("probe_status")),
                probe_transport=markdown_text(result.get("probe_transport_status")),
                probe_contract=markdown_text(result.get("probe_contract_observation")),
                probe_detail=markdown_text(result.get("probe_error_code")),
                accepted=int_value(cohort.get("accepted_count")),
                requested=int_value(cohort.get("requested_count")),
                transport=markdown_text(result.get("transport_status_counts")),
                contract=markdown_text(result.get("json_contract_status_counts")),
                gate=markdown_text(result.get("semantic_gate_status_counts")),
                validator=validator_text(metrics.get("validator_passed")),
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

    golden_observation = dict_value(report.get("golden_fixture_observation"))
    lines.extend(
        [
            "",
            "## Golden fixture gate observation",
            "",
            "This is observation-only classification of recorded fixture failure reasons; it does not change the production gate.",
            "",
            f"- fixture_item_count: {int_value(golden_observation.get('fixture_item_count'))}",
            f"- safety_gate_status_counts: {markdown_text(golden_observation.get('safety_gate_status_counts'))}",
            f"- usefulness_gate_status_counts: {markdown_text(golden_observation.get('usefulness_gate_status_counts'))}",
            f"- current_gate_decision_counts: {markdown_text(golden_observation.get('current_gate_decision_counts'))}",
            f"- hard_safety_only_accept_possible_count: {int_value(golden_observation.get('hard_safety_only_accept_possible_count'))}",
            f"- hard_safety_only_accept_possible_rate: {percentage_text(golden_observation.get('hard_safety_only_accept_possible_rate'))}",
            f"- reason_class_counts: {markdown_text(golden_observation.get('reason_class_counts'))}",
            "",
            "| Fixture URL | Safety gate | Usefulness gate | Current gate | Hard safety only accept possible | Reasons |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in list_value(golden_observation.get("items")):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {link} | {safety} | {usefulness} | {current} | {hard_only} | {reasons} |".format(
                link=markdown_text(item.get("link")),
                safety=markdown_text(item.get("safety_gate_status")),
                usefulness=markdown_text(item.get("usefulness_gate_status")),
                current=markdown_text(item.get("current_gate_decision")),
                hard_only=markdown_text(item.get("hard_safety_only_accept_possible")),
                reasons=markdown_text(item.get("failure_reasons")),
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


def reset_seconds(diagnostic: dict[str, Any]) -> float | None:
    rate_limit = dict_value(diagnostic.get("rate_limit"))
    value = str(rate_limit.get("reset_tokens") or "")
    if not value.endswith("s"):
        return None
    try:
        if "m" in value:
            minutes, seconds = value[:-1].split("m", 1)
            return int(minutes) * 60 + float(seconds)
        return float(value[:-1])
    except ValueError:
        return None


def wait_for_rate_reset(diagnostic: dict[str, Any]) -> str:
    seconds = reset_seconds(diagnostic)
    if seconds is None or seconds <= 0:
        return "not_needed"
    if seconds > MAX_RATE_RESET_WAIT_SECONDS:
        return "rate_budget_deferred"
    time.sleep(seconds)
    return "waited"


def probe_status_from_diagnostic(diagnostic: dict[str, Any]) -> str:
    """Separate a server-side JSON contract rejection from transport failure."""
    error = dict_value(diagnostic.get("error"))
    if (
        int_value(diagnostic.get("http_status")) == 400
        and error.get("code") == "json_validate_failed"
    ):
        return "contract_failed"
    if str(diagnostic.get("transport_status") or "") not in {"success", ""}:
        return "transport_failed"
    return "contract_failed"


def probe_contract_observation(probe: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(probe, dict):
        return {
            "transport_status": "not_applicable",
            "json_contract_status": "not_applicable",
            "contract_observation": "not_applicable",
            "error_code": "",
        }
    diagnostic = dict_value(dict_value(probe).get("diagnostic"))
    error = dict_value(diagnostic.get("error"))
    raw_contract_status = str(diagnostic.get("json_contract_status") or "not_evaluated")
    error_code = str(error.get("code") or "")
    return {
        "transport_status": str(diagnostic.get("transport_status") or "not_recorded"),
        "json_contract_status": raw_contract_status,
        "contract_observation": (
            "server_json_validate_failed"
            if error_code == "json_validate_failed"
            else raw_contract_status
        ),
        "error_code": error_code,
    }


def run_compatibility_probe(profile: ModelProfile, api_key: str, path: Path) -> dict[str, Any]:
    fixture = load_json(PROBE_FIXTURE)
    item = dict_value(fixture.get("item"))
    if not item:
        raise ValueError("compatibility probe fixture is missing item")
    try:
        schema = SUMMARY_ONLY_SCHEMA if profile.comparison_contract == "summary_only" else SUMMARY_ENTRY_SCHEMA
        schema_error = (
            summary_only_schema_error
            if profile.comparison_contract == "summary_only"
            else summary_entry_schema_error
        )
        completion = request_chat_completion(
            profile=profile,
            messages=compatibility_probe_messages(profile, item),
            temperature=0.0,
            max_tokens=profile.comparison_max_tokens,
            timeout_seconds=30,
            max_response_chars=4000,
            json_schema_name=(
                "malaysia_news_summary_only"
                if profile.comparison_contract == "summary_only"
                else "malaysia_news_summary_entry"
            ),
            json_schema=schema,
            schema_error=schema_error,
            api_key=api_key,
        )
        contract_valid = completion.diagnostic.get("json_contract_status") == "valid"
        result = {
            "probe_status": "passed" if contract_valid else "contract_failed",
            "request_configuration": comparison_request_configuration(profile),
            "diagnostic": completion.diagnostic,
            "parsed_root_keys": sorted(completion.parsed) if isinstance(completion.parsed, dict) else [],
            "rate_wait": wait_for_rate_reset(completion.diagnostic) if contract_valid else "not_needed",
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


def run_artifact_profile(
    profile: ModelProfile,
    args: argparse.Namespace,
    selected_count: int,
    cohort_links: list[str],
) -> dict[str, Any]:
    profile_dir = args.output_dir / profile.artifact_key
    profile_dir.mkdir(parents=True, exist_ok=True)
    improved_path = profile_dir / "groq_improved_items.json"
    candidate_path = profile_dir / "groq_json_render_candidate.md"
    validator_path = profile_dir / "groq_json_render_validator_status.json"
    validator_report = profile_dir / "groq_json_render_validator_report.md"
    run_status_path = profile_dir / "run_status.txt"
    probe_path = profile_dir / "compatibility_probe.json"

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
            cohort_links,
            probe_path,
        )

    probe = run_compatibility_probe(profile, os.environ["GROQ_API_KEY"], probe_path)
    if probe.get("probe_status") != "passed":
        run_status = "probe_failed"
        run_status_path.write_text(run_status + "\n", encoding="utf-8")
        return profile_result(
            profile,
            "artifact-only",
            run_status,
            selected_count,
            improved_path,
            candidate_path,
            validator_path,
            cohort_links,
            probe_path,
        )
    if probe.get("rate_wait") == "rate_budget_deferred":
        run_status = "rate_budget_deferred"
        run_status_path.write_text(run_status + "\n", encoding="utf-8")
        return profile_result(
            profile,
            "artifact-only",
            run_status,
            selected_count,
            improved_path,
            candidate_path,
            validator_path,
            cohort_links,
            probe_path,
        )
    if not cohort_links:
        run_status = "skipped_no_quality_cohort"
        run_status_path.write_text(run_status + "\n", encoding="utf-8")
        return profile_result(
            profile,
            "artifact-only",
            run_status,
            selected_count,
            improved_path,
            candidate_path,
            validator_path,
            cohort_links,
            probe_path,
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
        "--summary-prompt-layout",
        profile.comparison_prompt_layout,
        "--summary-max-tokens",
        str(profile.comparison_max_tokens),
        "--summary-contract",
        profile.comparison_contract,
        "--improved-items-output",
        str(improved_path),
        "--json-render-output",
        str(candidate_path),
        "--entry-render-output",
        str(profile_dir / "groq_entry_render_candidate.md"),
        "--request-link-allowlist",
        str(args.cohort_output),
        "--disable-entry-review",
        "--rate-reset-wait-max-seconds",
        str(MAX_RATE_RESET_WAIT_SECONDS),
        "--max-429-retry-after-seconds",
        str(MAX_RATE_RESET_WAIT_SECONDS),
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
            cohort_links,
            probe_path,
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
    improved = load_optional_json(improved_path)
    records = decision_records(improved)
    if any(record.get("reason") == "rate_budget_deferred" for record in records):
        run_status = "rate_budget_deferred"
    elif len([record for record in records if record.get("requested") is True]) < len(cohort_links):
        run_status = "quality_partial"
    else:
        run_status = "quality_completed"
    run_status_path.write_text(run_status + "\n", encoding="utf-8")
    return profile_result(
        profile,
        "artifact-only",
        run_status,
        selected_count,
        improved_path,
        candidate_path,
        validator_path,
        cohort_links,
        probe_path,
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
    cohort_links = quality_cohort_links(baseline_improved)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cohort_output = args.output_dir / "comparison_cohort.json"
    args.cohort_output.write_text(
        json.dumps(
            {
                "schema_version": "malaysia-groq-model-comparison-cohort/v1",
                "links": cohort_links,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    profiles = [
        profile_result(
            baseline_profile,
            "production-baseline",
            read_status(args.baseline_run_status_file),
            selected_count,
            args.baseline_improved_items,
            args.baseline_candidate,
            args.baseline_validator_status,
            cohort_links,
        )
    ]
    for profile in artifact_only_model_profiles(registry):
        profiles.append(run_artifact_profile(profile, args, selected_count, cohort_links))

    observed_on = datetime.now(tz=ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()
    added = update_golden_fixture(
        args.golden_fixture,
        load_optional_json(args.json_input) or selected,
        baseline_improved,
        baseline_profile,
        observed_on,
    )
    golden_observation = golden_fixture_gate_observation(load_optional_json(args.golden_fixture))
    generated_at = datetime.now(tz=ZoneInfo("UTC")).replace(microsecond=0).isoformat()
    report = {
        "schema_version": COMPARISON_SCHEMA,
        "generated_at": generated_at,
        "observation_only": True,
        "selected_count": selected_count,
        "quality_cohort_links": cohort_links,
        "fixed_quality_review_criteria": list(QUALITY_REVIEW_CRITERIA),
        "profiles": profiles,
        "golden_fixture_observation": golden_observation,
        "production_boundary": {
            "production_changed": False,
            "comparison_can_overwrite_production": False,
            "rss_only_rollback_variable": "MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false",
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_comparison_report(args.report_output, report, selected)

    statuses = [str(dict_value(result).get("run_status") or "unavailable") for result in profiles[1:]]
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(
        json.dumps(
            {
                "observation_only": True,
                "artifact_profile_statuses": statuses,
                "quality_cohort_links": cohort_links,
                "golden_fixture_items_added": added,
                "golden_fixture_observation": golden_observation,
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
