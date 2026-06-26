#!/usr/bin/env python3
import copy
import re
import sys
from typing import Any

import render_malaysia_news_from_json as fallback_renderer
from malaysia_groq_common import (
    GENERIC_LIFE_IMPACT_LINE,
    GENERIC_WHAT_HAPPENED_LINE,
    SAFE_FALLBACK_LIFE_IMPACT_LINE,
    SAFE_FALLBACK_WHAT_HAPPENED_LINE,
    clean_text,
    contains_any,
    looks_generic,
    summary_lines,
)


RSS_ITEM_BLOCK_RE = re.compile(r"(?ms)^- 結論：.*?\n- 出典元URL：(?P<link>[^\n]+)\n?")
RSS_FALLBACK_DATELINE_RE = re.compile(
    r"(?m)(- 何が起きた：)"
    r"(?:[A-Z][A-Z .'-]+),\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2}\s+[—–-]\s*"
)
RSS_FALLBACK_TEXT_DATELINE_RE = re.compile(
    r"^(?:[A-Z][A-Z .'-]+),\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2}\s+[—–-]\s*"
)
RSS_FALLBACK_ENGLISH_ARTICLE_LEAD_RE = re.compile(r"^[—–-]\s+(?:The|A|An)\s+", re.IGNORECASE)
SAFE_FALLBACK_CONCLUSION_LINE = "内容の詳細確認が必要なニュースです。"


def safe_log(message: str) -> None:
    print(message, file=sys.stderr)


def strip_rss_fallback_datelines(block: str) -> str:
    """Clean RSS-rendered fallback blocks only in merge-candidate Markdown."""
    return RSS_FALLBACK_DATELINE_RE.sub(r"\1", block)


def clean_rss_fallback_text_value(text: str) -> str:
    """Clean fallback replacement text before inserting it into merge candidates."""
    value = clean_text(text)
    value = RSS_FALLBACK_TEXT_DATELINE_RE.sub("", value)
    value = RSS_FALLBACK_ENGLISH_ARTICLE_LEAD_RE.sub("", value)
    return clean_text(value)


def item_by_link(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = data.get("items")
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        link = clean_text(item.get("link"))
        if link:
            result[link] = item
    return result


def safe_fallback_summary_for_item(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": SAFE_FALLBACK_LIFE_IMPACT_LINE,
        }
    topic = fallback_renderer.detect_topic(item)
    if not topic:
        return {
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": SAFE_FALLBACK_LIFE_IMPACT_LINE,
        }
    summary = fallback_renderer.build_display_summary(item)
    what_happened = [
        clean_rss_fallback_text_value(line)
        for line in summary_lines(summary.get("what_happened"))
        if line != GENERIC_WHAT_HAPPENED_LINE and not looks_generic(line)
    ]
    what_happened = [line for line in what_happened if line]
    life_impact = clean_rss_fallback_text_value(summary.get("life_impact"))
    if not what_happened:
        what_happened = [SAFE_FALLBACK_WHAT_HAPPENED_LINE]
    if not life_impact or life_impact == GENERIC_LIFE_IMPACT_LINE or looks_generic(life_impact):
        life_impact = SAFE_FALLBACK_LIFE_IMPACT_LINE
    return {"what_happened": what_happened[:2], "life_impact": life_impact}


def json_fallback_text(item: dict[str, Any]) -> str:
    parts = [
        clean_text(item.get("title")),
        clean_text(item.get("description")),
        clean_text(item.get("body_evidence_excerpt")),
    ]
    return " ".join(part for part in parts if part).lower()


def json_fallback_flags(item: dict[str, Any]) -> dict[str, Any]:
    flags = item.get("flags")
    return flags if isinstance(flags, dict) else {}


def high_confidence_json_fallback_topic(item: dict[str, Any]) -> str:
    text = json_fallback_text(item)
    flags = json_fallback_flags(item)
    if contains_any(text, ["flash flood", "flash floods", "flood hotline", "banjir"]):
        return "flood"
    if flags.get("is_weather") and contains_any(
        text,
        ["thunderstorm", "heavy rain", "ribut petir", "hujan lebat", "weather warning", "rain warning"],
    ):
        return "storm_weather"
    if flags.get("is_heat") or contains_any(text, ["hot weather", "heatstroke", "heat stroke", "strok haba"]):
        return "heat_weather"
    if contains_any(text, ["spill", "tumpah"]) and contains_any(text, ["accident", "tanker", "lorry", "truck"]):
        return "oil_spill"
    if flags.get("is_road_issue") and contains_any(
        text,
        ["closure", "closed", "tutup", "ditutup", "traffic congestion", "road closure"],
    ):
        return "road_closure"
    if flags.get("is_public_transport") and contains_any(
        text,
        ["rapid kl", "mrt", "lrt", "ktmb", "bus stop", "route", "schedule", "extra trains", "train services"],
    ):
        return "public_transport"
    if (
        flags.get("is_health_system")
        or contains_any(text, ["health ministry", "moh", "hospital", "clinic", "medical", "healthcare", "public health"])
    ):
        return "health"
    if (
        flags.get("is_currency")
        or contains_any(text, ["ringgit", "foreign exchange", "us dollar", "against the dollar", "currency"])
    ):
        return "currency"
    if (
        flags.get("is_market")
        or contains_any(text, ["bursa", "fbm klci", "stock market", "market index"])
    ):
        return "market"
    if contains_any(
        text,
        [
            "sara",
            "rahmah",
            "budi",
            "cash aid",
            "fuel aid",
            "fuel subsidy",
            "diesel subsidy",
            "petrol subsidy",
            "subsidy recipients",
            "cost of living",
            "kos sara hidup",
            "barang keperluan",
            "jualan murah",
            "harga",
            "price",
            "prices",
        ],
    ):
        return "cost_of_living"
    return ""


def safe_json_render_fallback_summary_for_item(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "conclusion": SAFE_FALLBACK_CONCLUSION_LINE,
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": SAFE_FALLBACK_LIFE_IMPACT_LINE,
            "next_action": "",
        }
    topic = high_confidence_json_fallback_topic(item)
    if not topic:
        return {
            "conclusion": SAFE_FALLBACK_CONCLUSION_LINE,
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": SAFE_FALLBACK_LIFE_IMPACT_LINE,
            "next_action": "",
        }
    topic_text = fallback_renderer.TOPIC_TEXT.get(topic, {})
    return {
        "conclusion": clean_text(topic_text.get("conclusion")) or SAFE_FALLBACK_CONCLUSION_LINE,
        "what_happened": summary_lines(topic_text.get("what_happened")) or [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
        "life_impact": clean_text(topic_text.get("life_impact")) or SAFE_FALLBACK_LIFE_IMPACT_LINE,
        "next_action": clean_text(topic_text.get("next_action")),
    }


def strip_generic_fallback_lines(block: str, item: dict[str, Any] | None) -> str:
    summary = safe_fallback_summary_for_item(item)
    replacement_what = summary_lines(summary.get("what_happened")) or [SAFE_FALLBACK_WHAT_HAPPENED_LINE]
    replacement_life = clean_text(summary.get("life_impact")) or SAFE_FALLBACK_LIFE_IMPACT_LINE
    lines = block.splitlines()
    cleaned_lines: list[str] = []
    seen_what_happened: set[str] = set()
    inserted_what = False
    for line in lines:
        what_match = re.match(r"^- 何が起きた：(.+)$", line)
        if line == f"- 何が起きた：{GENERIC_WHAT_HAPPENED_LINE}":
            if not inserted_what:
                for value in replacement_what[:2]:
                    normalized_value = clean_rss_fallback_text_value(value)
                    if normalized_value and normalized_value not in seen_what_happened:
                        cleaned_lines.append(f"- 何が起きた：{normalized_value}")
                        seen_what_happened.add(normalized_value)
                inserted_what = True
            continue
        if line == f"- 生活への影響：{GENERIC_LIFE_IMPACT_LINE}":
            cleaned_lines.append(f"- 生活への影響：{clean_rss_fallback_text_value(replacement_life)}")
            continue
        if what_match:
            normalized_value = clean_rss_fallback_text_value(what_match.group(1))
            if normalized_value in seen_what_happened:
                continue
            if normalized_value:
                seen_what_happened.add(normalized_value)
            line = f"- 何が起きた：{normalized_value}" if normalized_value else line
        cleaned_lines.append(line)
    suffix = "\n" if block.endswith("\n") else ""
    return "\n".join(cleaned_lines) + suffix


def clean_rss_fallback_block(block: str, item: dict[str, Any] | None) -> str:
    block = strip_rss_fallback_datelines(block)
    return strip_generic_fallback_lines(block, item)


def normalize_fallback_summaries_for_json_render(
    data: dict[str, Any],
    accepted_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the merge fallback cleanup to non-accepted items before JSON rendering."""
    normalized_data = copy.deepcopy(data)
    accepted_links = {
        clean_text(record.get("link"))
        for record in accepted_records
        if isinstance(record, dict) and clean_text(record.get("link"))
    }
    items = normalized_data.get("items")
    if not isinstance(items, list):
        return normalized_data
    for item in items:
        if not isinstance(item, dict):
            continue
        link = clean_text(item.get("link"))
        if link and link in accepted_links:
            continue
        summary = item.get("selected_summary")
        if not isinstance(summary, dict):
            summary = {}
        safe_summary = safe_json_render_fallback_summary_for_item(item)
        item["selected_summary"] = {
            "conclusion": clean_text(safe_summary.get("conclusion")),
            "what_happened": summary_lines(safe_summary.get("what_happened")),
            "life_impact": clean_text(safe_summary.get("life_impact")),
            "next_action": clean_text(safe_summary.get("next_action")),
        }
    return normalized_data


def render_accepted_record_block(record: dict[str, Any]) -> str:
    summary = record.get("improved_summary")
    if not isinstance(summary, dict):
        summary = {}
    lines: list[str] = []
    conclusion = clean_text(summary.get("conclusion"))
    life_impact = clean_text(summary.get("life_impact"))
    next_action = clean_text(summary.get("next_action"))
    source = clean_text(record.get("source"))
    published_date = clean_text(record.get("published_date"))
    link = clean_text(record.get("link"))

    lines.append(f"- 結論：{conclusion}")
    for line in summary_lines(summary.get("what_happened")):
        lines.append(f"- 何が起きた：{line}")
    lines.append(f"- 生活への影響：{life_impact}")
    if next_action:
        lines.append(f"- 次アクション：{next_action}")
    lines.append(f"- 出典：{source}（{published_date}）")
    lines.append(f"- 出典元URL：{link}")
    return "\n".join(lines) + "\n"


def merge_accepted_with_rss_markdown(
    rss_markdown: str,
    accepted_records: list[dict[str, Any]],
    data: dict[str, Any] | None = None,
) -> str:
    if not accepted_records:
        return rss_markdown

    block_by_link: dict[str, re.Match[str]] = {}
    duplicate_links: set[str] = set()
    for match in RSS_ITEM_BLOCK_RE.finditer(rss_markdown):
        link = clean_text(match.group("link"))
        if not link:
            continue
        if link in block_by_link:
            duplicate_links.add(link)
        block_by_link[link] = match
    if duplicate_links:
        safe_log("groq-merge: duplicate RSS Markdown URL block found; using exact RSS Markdown fallback.")
        return rss_markdown

    replacements: dict[str, str] = {}
    items_by_link = item_by_link(data or {})
    for record in accepted_records:
        if not isinstance(record, dict):
            continue
        link = clean_text(record.get("link"))
        if not link or link not in block_by_link:
            safe_log(f"groq-merge: accepted URL not found in RSS Markdown; using exact RSS Markdown fallback: {link}")
            return rss_markdown
        replacements[link] = render_accepted_record_block(record)

    def replace_block(match: re.Match[str]) -> str:
        link = clean_text(match.group("link"))
        if link in replacements:
            return replacements[link]
        return clean_rss_fallback_block(match.group(0), items_by_link.get(link))

    return RSS_ITEM_BLOCK_RE.sub(replace_block, rss_markdown)
