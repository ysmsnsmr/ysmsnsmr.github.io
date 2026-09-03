#!/usr/bin/env python3
"""Finalize v3 Malaysia news editorial entries in one place."""

import copy
from dataclasses import dataclass
from typing import Any

from malaysia_groq_common import clean_text
from malaysia_groq_output_contract import editorial_entry_schema_error


GROQ_ACCEPTED = "groq_accepted"
GROQ_REPAIRED = "groq_repaired"
SOURCE_DISPLAY = "source_display"
RSS_FALLBACK = "rss_fallback"
RSS_FALLBACK_ENTRY_KIND = "source_link_only"
SOURCE_DISPLAY_ENTRY_KIND = "source_title_and_description"
PROVENANCE_ORIGINS = (
    "rss_derived",
    "groq_replaced",
    "groq_inherited",
    "source_display",
    "fallback_source_only",
)

# This is the only article-level fallback emitted by the v3 candidate path.
# It makes no claim about the article, so a rejected model response cannot
# reintroduce unverified legacy RSS text into an otherwise valid document.
RSS_FALLBACK_EDITORIAL_ENTRY = {
    "headline_ja": "記事詳細は出典へ",
    "short_headline_ja": "記事詳細は出典へ",
    "entry_ja": "この記事の詳細は出典リンクで確認できます。",
    "supporting_points_ja": [],
}


@dataclass(frozen=True)
class RenderDecision:
    index: int
    link: str
    source_kind: str
    editorial_entry: dict[str, Any]
    rss_fallback_entry_kind: str = ""


def editorial_entry_payload(value: Any) -> dict[str, Any]:
    entry = value if isinstance(value, dict) else {}
    points = entry.get("supporting_points_ja")
    return {
        "headline_ja": clean_text(entry.get("headline_ja")) or "記事詳細は出典へ",
        "short_headline_ja": clean_text(entry.get("short_headline_ja")) or clean_text(entry.get("headline_ja")) or "記事詳細は出典へ",
        "entry_ja": clean_text(entry.get("entry_ja")),
        "supporting_points_ja": [
            clean_text(point) for point in points if clean_text(point)
        ][:2]
        if isinstance(points, list)
        else [],
    }


def validated_rss_fallback_editorial_entry() -> dict[str, Any]:
    """Return the code-owned, validator-safe v3 fallback object.

    Legacy RSS entries are not used here.  They can contain untranslated text
    or old topic templates, while this object has no article-level assertion
    that could conflict with a hard-safety rejection.
    """
    entry = editorial_entry_payload(RSS_FALLBACK_EDITORIAL_ENTRY)
    error = editorial_entry_schema_error({"editorial_entry": entry})
    if error:
        raise ValueError(f"invalid code-owned RSS fallback entry: {error}")
    return entry


def validated_source_display_editorial_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Keep ungenerated source fields visible when the model was not run."""
    description = clean_text(item.get("description"))
    entry = {
        "headline_ja": "原題・出典情報",
        "short_headline_ja": "原題・出典情報",
        "entry_ja": clean_text(item.get("title")) or "原題は出典リンクで確認できます。",
        "supporting_points_ja": [description] if description else [],
    }
    error = editorial_entry_schema_error({"editorial_entry": entry})
    if error:
        raise ValueError(f"invalid source display entry: {error}")
    return entry


def _uses_source_display(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict) or record.get("requested") is True:
        return False
    return clean_text(record.get("reason")) in {
        "missing_groq_api_key",
        "request_cap",
        "rate_budget_deferred",
        "comparison_cohort_excluded",
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
        repaired = accepted and record is not None and record.get("repair_accepted") is True
        source_kind = (
            GROQ_REPAIRED if repaired
            else GROQ_ACCEPTED if accepted
            else SOURCE_DISPLAY if _uses_source_display(record)
            else RSS_FALLBACK
        )
        decisions.append(
            RenderDecision(
                index=index,
                link=clean_text(item.get("link")),
                source_kind=source_kind,
                editorial_entry=(
                    editorial_entry_payload(item.get("editorial_entry"))
                    if accepted
                    else validated_rss_fallback_editorial_entry()
                    if source_kind == RSS_FALLBACK
                    else validated_source_display_editorial_entry(item)
                ),
                rss_fallback_entry_kind=(
                    RSS_FALLBACK_ENTRY_KIND if source_kind == RSS_FALLBACK
                    else SOURCE_DISPLAY_ENTRY_KIND if source_kind == SOURCE_DISPLAY
                    else ""
                ),
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


# Migration-only aliases for the rollback merge helper. Production v3 calls
# apply_render_decisions directly and never creates the old render tiers.
def apply_json_render_decisions(data: dict[str, Any], decisions: list[RenderDecision]) -> dict[str, Any]:
    return apply_render_decisions(data, decisions)


def apply_entry_render_decisions(data: dict[str, Any], decisions: list[RenderDecision]) -> dict[str, Any]:
    return apply_render_decisions(data, decisions)


def _entry_lines(entry: dict[str, Any]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    headline = clean_text(entry.get("headline_ja"))
    if headline:
        lines.append(("headline_ja", headline))
    short_headline = clean_text(entry.get("short_headline_ja"))
    if short_headline:
        lines.append(("short_headline_ja", short_headline))
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
        if decision.source_kind == RSS_FALLBACK:
            record["rss_fallback_entry_kind"] = decision.rss_fallback_entry_kind
            record["rss_fallback_entry_contract_status"] = "valid"
        elif decision.source_kind == SOURCE_DISPLAY:
            record["source_display_entry_kind"] = decision.rss_fallback_entry_kind
            record["source_display_entry_contract_status"] = "valid"
        original = editorial_entry_payload(original_items[item_index].get("editorial_entry"))
        final = editorial_entry_payload(final_items[item_index].get("editorial_entry"))
        remaining = {
            "headline_ja": {},
            "short_headline_ja": {},
            "entry_ja": {},
            "supporting_points_ja": {},
        }
        for field, text in _entry_lines(original):
            remaining[field][text] = remaining[field].get(text, 0) + 1
        lines: list[dict[str, Any]] = []
        for field, text in _entry_lines(final):
            origin = "rss_derived"
            if decision.source_kind == RSS_FALLBACK:
                origin = "fallback_source_only"
            elif decision.source_kind == SOURCE_DISPLAY:
                origin = "source_display"
            elif decision.source_kind in {GROQ_ACCEPTED, GROQ_REPAIRED}:
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
        for field in ("headline_ja", "short_headline_ja", "entry_ja", "supporting_points_ja")
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
