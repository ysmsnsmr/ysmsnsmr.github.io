#!/usr/bin/env python3
"""Apply a bounded Jev editorial budget to Malaysia News candidates.

This is deliberately fail-open. The legacy selector JSON remains the output
whenever the routing kill switch is off, the candidate set is too large, or any
Jev call fails validation. Freshness, URL validation, and canonical
deduplication run before this module. Source and topic diversity run here after
Jev relevance classification.
"""

import argparse
import copy
import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from jev_shadow_transport import JevRequestError, post_jev_request
from malaysia_event_match_observation import observe as observe_event_coverage
from malaysia_jev_selector_shadow import (
    QUESTION_SET_VERSION,
    REQUESTED_MODEL_ID,
    build_request,
    extract_answer,
)
from malaysia_news_display_categories import display_category_for_jev


SCHEMA_VERSION = "malaysia-news-jev-editorial-routing/v2"
MAX_ROUTING_CANDIDATES = 150
TARGET_CARD_COUNT = 20
CHOICE_ORDER = ("direct_life_impact", "public_information", "unclear")

PostJson = Callable[[dict[str, Any], str, float], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _items(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    value = payload.get("items")
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} items must be an array of objects")
    return value


def _fingerprint(item: dict[str, Any]) -> str:
    values = (str(item.get("source") or ""), str(item.get("link") or ""), str(item.get("published_at") or ""))
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _publication_item(item: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(item)
    value.pop("routing_metadata", None)
    return value


def _selected_item(item: dict[str, Any], jev_decision: str) -> dict[str, Any]:
    value = copy.deepcopy(item)
    value["display_category"] = display_category_for_jev(jev_decision, value.get("category"))
    return value


def _positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return fallback


def _post_relevance_policy(candidate_pool: dict[str, Any]) -> dict[str, Any]:
    raw = candidate_pool.get("post_relevance_policy")
    if not isinstance(raw, dict):
        raw = {}
    source_limits = raw.get("source_limits")
    financial_limits = raw.get("financial_limits")
    return {
        "target_card_count": _positive_int(raw.get("target_card_count"), TARGET_CARD_COUNT),
        "default_source_limit": _positive_int(raw.get("default_source_limit"), 24),
        "source_limits": {
            str(name): value
            for name, value in (source_limits.items() if isinstance(source_limits, dict) else [])
            if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool) and value > 0
        },
        "financial_limits": {
            str(name): value
            for name, value in (financial_limits.items() if isinstance(financial_limits, dict) else [])
            if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool) and value > 0
        },
    }


def _safe_result(index: int, item: dict[str, Any], baseline_links: set[str]) -> dict[str, Any]:
    return {
        "candidateRank": index,
        "itemFingerprint": _fingerprint(item),
        "baselineSelected": str(item.get("link") or "") in baseline_links,
        "category": item.get("category") if isinstance(item.get("category"), str) else None,
    }


def _baseline_output(baseline: dict[str, Any], routing: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(baseline)
    output["editorial_routing"] = routing
    return output


def _routed_output(
    baseline: dict[str, Any],
    selected: list[dict[str, Any]],
    routing: dict[str, Any],
) -> dict[str, Any]:
    output = _baseline_output(baseline, routing)
    output["items"] = [_publication_item(item) for item in selected]
    counts = output.get("counts")
    if not isinstance(counts, dict):
        counts = {}
        output["counts"] = counts
    counts["selected"] = len(selected)
    return output


def _report_base(enabled: bool, candidate_count: int, baseline_count: int) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "enabled": enabled,
        "routingEffect": False,
        "requestedModelId": REQUESTED_MODEL_ID,
        "questionSetVersion": QUESTION_SET_VERSION,
        "maxRoutingCandidates": MAX_ROUTING_CANDIDATES,
        "targetCardCount": TARGET_CARD_COUNT,
        "rawProviderResponseStored": False,
        "credentialStored": False,
        "articleTextStored": False,
        "candidateCount": candidate_count,
        "baselineSelectedCount": baseline_count,
        "results": [],
    }


def _finish_report(report: dict[str, Any], status: str, selected_count: int) -> dict[str, Any]:
    results = report["results"]
    classified = [result for result in results if result.get("outcome") == "classified"]
    report["status"] = status
    report["summary"] = {
        "classified": len(classified),
        "errors": sum(result.get("outcome") == "error" for result in results),
        "jevDecisionCounts": dict(sorted(Counter(result["jevDecision"] for result in classified).items())),
        "publicationDecisionCounts": dict(
            sorted(Counter(result.get("publicationDecision", "not_routed") for result in classified).items())
        ),
        "selectedCount": selected_count,
    }
    return report


def route_candidates(
    candidate_pool: dict[str, Any],
    baseline: dict[str, Any],
    *,
    enabled: bool,
    api_key: str | None,
    timeout_seconds: float,
    post_json: PostJson = post_jev_request,
    event_enabled: bool = False,
    event_api_key: str | None = None,
    event_model: str = "gpt-oss-120b",
    event_observer: Callable[..., dict[str, Any]] = observe_event_coverage,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a routed payload or the untouched selector baseline.

    A single bad response fails open for the entire selection. That prevents a
    partial Jev result from silently changing which articles are published.
    """
    candidates = _items(candidate_pool, "candidate pool")
    baseline_items = _items(baseline, "baseline")
    baseline_links = {str(item.get("link") or "") for item in baseline_items}
    policy = _post_relevance_policy(candidate_pool)
    report = _report_base(enabled, len(candidates), len(baseline_items))

    if not enabled:
        routing = {"status": "disabled", "applied": False, "policy": "legacy_selector_baseline"}
        return _baseline_output(baseline, routing), _finish_report(report, "disabled", len(baseline_items))
    if not api_key:
        routing = {"status": "fallback_missing_api_key", "applied": False, "policy": "legacy_selector_baseline"}
        return _baseline_output(baseline, routing), _finish_report(report, "fallback_missing_api_key", len(baseline_items))
    if len(candidates) > MAX_ROUTING_CANDIDATES:
        routing = {
            "status": "fallback_candidate_cap",
            "applied": False,
            "policy": "legacy_selector_baseline",
            "candidateCount": len(candidates),
        }
        return _baseline_output(baseline, routing), _finish_report(report, "fallback_candidate_cap", len(baseline_items))

    classified: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for index, item in enumerate(candidates, start=1):
        result = _safe_result(index, item, baseline_links)
        started = time.monotonic()
        try:
            response = post_json(build_request(item), api_key, timeout_seconds)
            answer, provider_model_id = extract_answer(response)
        except JevRequestError as error:
            report["results"].append({**result, "outcome": "error", "errorCode": error.code})
            routing = {"status": "fallback_classifier_error", "applied": False, "policy": "legacy_selector_baseline"}
            return _baseline_output(baseline, routing), _finish_report(report, "fallback_classifier_error", len(baseline_items))
        except Exception:
            report["results"].append({**result, "outcome": "error", "errorCode": "transport_error"})
            routing = {"status": "fallback_classifier_error", "applied": False, "policy": "legacy_selector_baseline"}
            return _baseline_output(baseline, routing), _finish_report(report, "fallback_classifier_error", len(baseline_items))
        classified.append((index, item, answer))
        report["results"].append(
            {
                **result,
                "outcome": "classified",
                "jevDecision": answer["choice"],
                "displayCategory": display_category_for_jev(answer["choice"], item.get("category")),
                "confidence": answer["confidence"],
                "providerModelId": provider_model_id,
                "latencyMs": round((time.monotonic() - started) * 1000),
            }
        )

    by_choice: dict[str, list[tuple[int, dict[str, Any]]]] = {choice: [] for choice in (*CHOICE_ORDER, "unrelated_noise")}
    for index, item, answer in classified:
        by_choice[answer["choice"]].append((index, item))

    coverage = {"status": "disabled", "productionEffect": False, "coverageDecisions": [], "cohort": []}
    if event_enabled:
        try:
            coverage = event_observer(
                candidate_pool, {"status": "applied", "results": report["results"]},
                api_key=event_api_key, model_name=event_model,
            )
        except Exception:
            coverage = {"status": "request_failed", "productionEffect": False, "coverageDecisions": [], "cohort": []}
    report["eventCoverage"] = coverage
    cohort_ranks = {row["id"]: row["candidateRank"] for row in coverage.get("cohort", [])}
    covered_by = {
        cohort_ranks[row["omit"]]: cohort_ranks[row["keep"]]
        for row in coverage.get("coverageDecisions", [])
        if coverage.get("status") == "completed"
        and row["omit"] in cohort_ranks and row["keep"] in cohort_ranks
    }

    selected: list[dict[str, Any]] = []
    selected_fingerprints: set[str] = set()
    selected_ranks: set[int] = set()
    source_counts: Counter[str] = Counter()
    financial_counts: Counter[str] = Counter()
    results_by_fingerprint = {
        result["itemFingerprint"]: result
        for result in report["results"]
        if result.get("outcome") == "classified"
    }
    for _, item in by_choice["unrelated_noise"]:
        results_by_fingerprint[_fingerprint(item)]["publicationDecision"] = "excluded_unrelated_noise"

    for choice in CHOICE_ORDER:
        for rank, item in by_choice[choice]:
            fingerprint = _fingerprint(item)
            result = results_by_fingerprint[fingerprint]
            if fingerprint in selected_fingerprints:
                continue
            if choice == "unclear" and str(item.get("link") or "") not in baseline_links:
                result["publicationDecision"] = "excluded_unclear"
                continue
            representative_rank = covered_by.get(rank)
            if representative_rank in selected_ranks:
                result["publicationDecision"] = "excluded_covered_event"
                result["coveredByCandidateRank"] = representative_rank
                result["coveredByFingerprint"] = report["results"][representative_rank - 1]["itemFingerprint"]
                continue
            source = str(item.get("source") or "")
            source_limit = policy["source_limits"].get(source, policy["default_source_limit"])
            if source_counts[source] >= source_limit:
                result["publicationDecision"] = "excluded_source_diversity"
                continue
            metadata = item.get("routing_metadata")
            financial_bucket = metadata.get("financial_bucket") if isinstance(metadata, dict) else ""
            financial_limit = policy["financial_limits"].get(financial_bucket) if financial_bucket else None
            if financial_limit is not None and financial_counts[financial_bucket] >= financial_limit:
                result["publicationDecision"] = "excluded_financial_diversity"
                continue
            if len(selected) >= policy["target_card_count"]:
                result["publicationDecision"] = "excluded_editorial_budget"
                continue
            selected.append(_selected_item(item, choice))
            selected_fingerprints.add(fingerprint)
            selected_ranks.add(rank)
            result["publicationDecision"] = "selected"
            source_counts[source] += 1
            if financial_bucket:
                financial_counts[financial_bucket] += 1

    coverage["productionEffect"] = bool(
        any(result.get("publicationDecision") == "excluded_covered_event" for result in report["results"])
    )
    coverage["suppressedCount"] = sum(
        result.get("publicationDecision") == "excluded_covered_event" for result in report["results"]
    )
    routing = {
        "status": "applied",
        "applied": True,
        "policy": "jev_relevance_then_event_coverage_then_diversity_and_editorial_budget",
        "event_coverage_status": coverage["status"],
        "event_coverage_suppressed_count": coverage["suppressedCount"],
        "target_card_count": policy["target_card_count"],
        "direct_life_impact_protected": True,
        "fixed_category_caps_applied": False,
        "source_limits_applied_after_relevance": True,
        "financial_limits_applied_after_relevance": True,
        "summary_validation_stage": "after_summary_generation",
        "legacy_baseline_selected_count": len(baseline_items),
        "routed_selected_count": len(selected),
    }
    report["routingEffect"] = True
    return _routed_output(baseline, selected, routing), _finish_report(report, "applied", len(selected))


def main() -> int:
    parser = argparse.ArgumentParser(description="Route Malaysia News candidates with a bounded Jev editorial budget.")
    parser.add_argument("--candidate-pool", required=True)
    parser.add_argument("--baseline-selected", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--event-coverage", action="store_true")
    parser.add_argument("--event-model", default="gpt-oss-120b")
    parser.add_argument("--event-report-output")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--disabled", action="store_true")
    args = parser.parse_args()

    try:
        candidate_pool = _read_json(Path(args.candidate_pool))
        baseline = _read_json(Path(args.baseline_selected))
        output, report = route_candidates(
            candidate_pool,
            baseline,
            enabled=args.live,
            api_key=os.environ.get("TYPESAFE_API_KEY", "").strip() or None,
            timeout_seconds=args.timeout_seconds,
            event_enabled=args.event_coverage and args.live,
            event_api_key=os.environ.get("GROQ_API_KEY", "").strip() or None,
            event_model=args.event_model,
        )
        _write_json(Path(args.output), output)
        _write_json(Path(args.report_output), report)
        if args.event_report_output:
            _write_json(Path(args.event_report_output), report.get("eventCoverage") or {
                "status": "skipped_routing_not_applied", "productionEffect": False,
                "coverageDecisions": [], "cohort": [],
            })
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: editorial routing input failure: {error}")
        return 2

    print(
        f"PASS: Jev editorial routing {report['status']} "
        f"selected={report['summary']['selectedCount']} classified={report['summary']['classified']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
