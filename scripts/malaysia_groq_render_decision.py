#!/usr/bin/env python3
import copy
from dataclasses import dataclass
from typing import Any, Callable

from malaysia_groq_common import (
    SAFE_FALLBACK_LIFE_IMPACT_LINE,
    SAFE_FALLBACK_WHAT_HAPPENED_LINE,
    clean_text,
    summary_lines,
)


JSON_TIER_ACCEPTED = "accepted_full"
JSON_TIER_TOPIC_FALLBACK = "topic_fallback"
JSON_TIER_GENERIC_FALLBACK = "generic_fallback"
ENTRY_TIER_ENTRY_CANDIDATE = "entry_candidate"


@dataclass(frozen=True)
class RenderDecision:
    """The finalized display inputs for one selected item across render modes."""

    index: int
    link: str
    json_tier: str
    entry_tier: str
    fallback_topic: str
    json_summary: dict[str, Any]
    entry_summary: dict[str, Any]


def summary_payload(value: Any) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    return {
        "conclusion": clean_text(summary.get("conclusion")),
        "what_happened": summary_lines(summary.get("what_happened")),
        "life_impact": clean_text(summary.get("life_impact")),
        "next_action": clean_text(summary.get("next_action")),
    }


def entry_text(record: dict[str, Any]) -> str:
    entry = record.get("entry")
    if isinstance(entry, dict):
        return clean_text(entry.get("text_ja"))
    if "entry" not in record:
        return clean_text(record.get("entry_candidate"))
    return ""


def record_for_item(
    index: int,
    item: dict[str, Any],
    records_by_index: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    record = records_by_index.get(index + 1)
    if not isinstance(record, dict):
        return None
    if clean_text(record.get("link")) != clean_text(item.get("link")):
        return None
    return record


def build_render_decisions(
    items: list[Any],
    decision_records: list[dict[str, Any]],
    fallback_summary_for_item: Callable[[dict[str, Any] | None, str | None], dict[str, Any]],
    fallback_topic_for_item: Callable[[dict[str, Any]], str],
) -> list[RenderDecision]:
    """Finalize JSON and entry render tiers once, keyed by item index and link."""
    records_by_index = {
        record.get("index"): record
        for record in decision_records
        if isinstance(record, dict) and isinstance(record.get("index"), int)
    }
    decisions: list[RenderDecision] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        record = record_for_item(index, item, records_by_index)
        link = clean_text(item.get("link"))
        if record is not None and record.get("accepted") is True:
            summary = summary_payload(item.get("selected_summary"))
            decisions.append(
                RenderDecision(
                    index=index,
                    link=link,
                    json_tier=JSON_TIER_ACCEPTED,
                    entry_tier=JSON_TIER_ACCEPTED,
                    fallback_topic="",
                    json_summary=summary,
                    entry_summary=copy.deepcopy(summary),
                )
            )
            continue

        topic = fallback_topic_for_item(item)
        fallback_summary = summary_payload(fallback_summary_for_item(item, topic))
        json_tier = JSON_TIER_TOPIC_FALLBACK if topic else JSON_TIER_GENERIC_FALLBACK
        entry_candidate = entry_text(record) if record is not None else ""
        entry_tier = json_tier
        entry_summary = copy.deepcopy(fallback_summary)
        if record is not None and record.get("entry_candidate_status") == "full_rejected" and entry_candidate:
            entry_tier = ENTRY_TIER_ENTRY_CANDIDATE
            entry_summary = {
                "conclusion": entry_candidate,
                "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
                "life_impact": SAFE_FALLBACK_LIFE_IMPACT_LINE,
                "next_action": "",
            }
        decisions.append(
            RenderDecision(
                index=index,
                link=link,
                json_tier=json_tier,
                entry_tier=entry_tier,
                fallback_topic=topic,
                json_summary=fallback_summary,
                entry_summary=entry_summary,
            )
        )
    return decisions


def apply_render_decisions(
    data: dict[str, Any],
    render_decisions: list[RenderDecision],
    summary_field: str,
) -> dict[str, Any]:
    """Copy data and apply a precomputed summary without recomputing its tier."""
    normalized_data = copy.deepcopy(data)
    items = normalized_data.get("items")
    if not isinstance(items, list):
        return normalized_data
    decision_by_index = {decision.index: decision for decision in render_decisions}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        decision = decision_by_index.get(index)
        if decision is None or decision.link != clean_text(item.get("link")):
            continue
        summary = getattr(decision, summary_field)
        item["selected_summary"] = copy.deepcopy(summary)
    return normalized_data


def apply_json_render_decisions(
    data: dict[str, Any], render_decisions: list[RenderDecision]
) -> dict[str, Any]:
    return apply_render_decisions(data, render_decisions, "json_summary")


def apply_entry_render_decisions(
    data: dict[str, Any], render_decisions: list[RenderDecision]
) -> dict[str, Any]:
    return apply_render_decisions(data, render_decisions, "entry_summary")


def annotate_decision_records(
    decision_records: list[dict[str, Any]], render_decisions: list[RenderDecision]
) -> None:
    """Keep existing diagnostics fields as projections of the render decisions."""
    decisions_by_index = {decision.index + 1: decision for decision in render_decisions}
    for record in decision_records:
        if not isinstance(record, dict):
            continue
        index = record.get("index")
        decision = decisions_by_index.get(index) if isinstance(index, int) else None
        if decision is None or decision.link != clean_text(record.get("link")):
            continue
        record["json_render_fallback_kind"] = {
            JSON_TIER_ACCEPTED: "accepted",
            JSON_TIER_TOPIC_FALLBACK: "topic",
            JSON_TIER_GENERIC_FALLBACK: "generic",
        }[decision.json_tier]
        record["json_render_fallback_topic"] = decision.fallback_topic
        record["entry_render_tier"] = {
            JSON_TIER_ACCEPTED: "full_summary",
            ENTRY_TIER_ENTRY_CANDIDATE: "entry_candidate",
            JSON_TIER_TOPIC_FALLBACK: "existing_fallback",
            JSON_TIER_GENERIC_FALLBACK: "existing_fallback",
        }[decision.entry_tier]
