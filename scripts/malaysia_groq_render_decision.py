#!/usr/bin/env python3
"""Finalize v2 Malaysia news editorial entries in one place."""

import copy
from dataclasses import dataclass
from typing import Any

from malaysia_groq_common import clean_text


GROQ_ACCEPTED = "groq_accepted"
RSS_FALLBACK = "rss_fallback"
PROVENANCE_ORIGINS = ("rss_derived", "groq_replaced", "groq_inherited")


@dataclass(frozen=True)
class RenderDecision:
    index: int
    link: str
    source_kind: str
    editorial_entry: dict[str, Any]


def editorial_entry_payload(value: Any) -> dict[str, Any]:
    entry = value if isinstance(value, dict) else {}
    points = entry.get("supporting_points_ja")
    return {
        "entry_ja": clean_text(entry.get("entry_ja")),
        "supporting_points_ja": [
            clean_text(point) for point in points if clean_text(point)
        ][:2]
        if isinstance(points, list)
        else [],
    }


def _record_for_item(
    index: int,
    item: dict[str, Any],
    records: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    record = records.get(index + 1)
    if not isinstance(record, dict) or clean_text(record.get("link")) != clean_text(item.get("link")):
        return None
    return record


def build_render_decisions(items: list[Any], decision_records: list[dict[str, Any]]) -> list[RenderDecision]:
    records = {
        record.get("index"): record
        for record in decision_records
        if isinstance(record, dict) and isinstance(record.get("index"), int)
    }
    decisions: list[RenderDecision] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        record = _record_for_item(index, item, records)
        accepted = record is not None and record.get("accepted") is True
        decisions.append(
            RenderDecision(
                index=index,
                link=clean_text(item.get("link")),
                source_kind=GROQ_ACCEPTED if accepted else RSS_FALLBACK,
                editorial_entry=editorial_entry_payload(item.get("editorial_entry")),
            )
        )
    return decisions


def apply_render_decisions(data: dict[str, Any], decisions: list[RenderDecision]) -> dict[str, Any]:
    rendered = copy.deepcopy(data)
    items = rendered.get("items")
    if not isinstance(items, list):
        return rendered
    by_index = {decision.index: decision for decision in decisions}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        decision = by_index.get(index)
        if decision is None or decision.link != clean_text(item.get("link")):
            continue
        item["editorial_entry"] = copy.deepcopy(decision.editorial_entry)
    return rendered


# Migration-only aliases for the rollback merge helper.  Production v2 calls
# apply_render_decisions directly and never creates the old render tiers.
def apply_json_render_decisions(data: dict[str, Any], decisions: list[RenderDecision]) -> dict[str, Any]:
    return apply_render_decisions(data, decisions)


def apply_entry_render_decisions(data: dict[str, Any], decisions: list[RenderDecision]) -> dict[str, Any]:
    return apply_render_decisions(data, decisions)


def _entry_lines(entry: dict[str, Any]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    text = clean_text(entry.get("entry_ja"))
    if text:
        lines.append(("entry_ja", text))
    points = entry.get("supporting_points_ja")
    if isinstance(points, list):
        lines.extend(("supporting_points_ja", clean_text(point)) for point in points if clean_text(point))
    return lines


def annotate_decision_records(
    original_data: dict[str, Any],
    final_data: dict[str, Any],
    decision_records: list[dict[str, Any]],
    decisions: list[RenderDecision],
) -> None:
    original_items = original_data.get("items")
    final_items = final_data.get("items")
    if not isinstance(original_items, list) or not isinstance(final_items, list):
        return
    decisions_by_index = {decision.index + 1: decision for decision in decisions}
    for record in decision_records:
        if not isinstance(record, dict) or not isinstance(record.get("index"), int):
            continue
        decision = decisions_by_index.get(record["index"])
        item_index = record["index"] - 1
        if (
            decision is None
            or not 0 <= item_index < len(original_items)
            or item_index >= len(final_items)
            or not isinstance(original_items[item_index], dict)
            or not isinstance(final_items[item_index], dict)
        ):
            continue
        record["render_source_kind"] = decision.source_kind
        original = editorial_entry_payload(original_items[item_index].get("editorial_entry"))
        final = editorial_entry_payload(final_items[item_index].get("editorial_entry"))
        remaining = {"entry_ja": {}, "supporting_points_ja": {}}
        for field, text in _entry_lines(original):
            remaining[field][text] = remaining[field].get(text, 0) + 1
        lines: list[dict[str, Any]] = []
        for field, text in _entry_lines(final):
            origin = "rss_derived"
            if decision.source_kind == GROQ_ACCEPTED:
                if remaining[field].get(text, 0):
                    remaining[field][text] -= 1
                    origin = "groq_inherited"
                else:
                    origin = "groq_replaced"
            lines.append({"field": field, "text": text, "origin": origin})
        record["editorial_entry_line_provenance"] = lines


def provenance_observation(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {origin: 0 for origin in PROVENANCE_ORIGINS}
    fields = {
        field: {origin: 0 for origin in PROVENANCE_ORIGINS}
        for field in ("entry_ja", "supporting_points_ja")
    }
    for record in records:
        raw_lines = record.get("editorial_entry_line_provenance") if isinstance(record, dict) else []
        for line in raw_lines if isinstance(raw_lines, list) else []:
            if not isinstance(line, dict):
                continue
            origin = clean_text(line.get("origin"))
            field = clean_text(line.get("field"))
            if origin in counts:
                counts[origin] += 1
                if field in fields:
                    fields[field][origin] += 1
    return {"observation_only": True, "line_counts": counts, "line_counts_by_field": fields}
