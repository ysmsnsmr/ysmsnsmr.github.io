#!/usr/bin/env python3
import re
from typing import Any

import render_malaysia_news_from_json as fallback_renderer


GENERIC_WHAT_HAPPENED_LINE = "RSS内のタイトルと説明をもとに整理しました。"
GENERIC_LIFE_IMPACT_LINE = "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。"
SAFE_FALLBACK_WHAT_HAPPENED_LINE = "RSSの見出しと説明に基づく概要です。"
SAFE_FALLBACK_LIFE_IMPACT_LINE = "内容に応じて、対象者や利用条件を確認してください。"

TOPIC_ALIASES = {
    "storm_weather": "storm_weather",
    "weather": "storm_weather",
    "storm": "storm_weather",
    "heavy_rain": "storm_weather",
    "rain": "storm_weather",
    "heat_weather": "heat_weather",
    "heat": "heat_weather",
    "hot_weather": "heat_weather",
    "flood": "flood",
    "flood_impact": "flood",
    "road_closure": "road_closure",
    "road": "road_closure",
    "road_issue": "road_closure",
    "public_transport": "public_transport",
    "transport": "public_transport",
    "cost_of_living": "cost_of_living",
    "prices": "cost_of_living",
    "health": "health",
    "public_health": "health",
    "currency": "currency",
    "market": "market",
}


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def summary_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)][:2]
    if isinstance(value, str):
        return [clean_text(line) for line in value.splitlines() if clean_text(line)][:2]
    return []


def looks_english_or_bm(text: str) -> bool:
    if not text:
        return True
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    japanese_chars = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    if japanese_chars == 0 and ascii_letters >= 12:
        return True
    return ascii_letters >= 24 and ascii_letters > japanese_chars * 2


def looks_generic(text: str) -> bool:
    generic_phrases = [
        GENERIC_LIFE_IMPACT_LINE.rstrip("。"),
        GENERIC_LIFE_IMPACT_LINE,
        "背景ニュースとして",
        "把握しておく価値があります",
        "rssでは",
        "rssの情報では",
    ]
    lower_text = text.lower()
    return any(phrase.lower() in lower_text for phrase in generic_phrases)


def has_any_text(text: str, phrases: list[str]) -> bool:
    return any(phrase.lower() in text for phrase in phrases)


def has_search_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = re.sub(r"\s+", " ", phrase.strip().lower())
    if not normalized_phrase:
        return False
    if re.search(r"[a-z0-9]", normalized_phrase):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized_phrase in text


def has_any_search_phrase(text: str, phrases: list[str]) -> bool:
    return any(has_search_phrase(text, phrase) for phrase in phrases)


def contains_any(text: str, words: list[str]) -> bool:
    return has_any_search_phrase(text.lower(), words)


def normalize_topic(topic: str) -> str:
    return TOPIC_ALIASES.get(clean_text(topic).lower(), "")


def item_search_text(item: dict[str, Any]) -> str:
    parts = [
        clean_text(item.get("title")),
        clean_text(item.get("description")),
    ]
    summary = item.get("selected_summary")
    if isinstance(summary, dict):
        parts.extend(
            [
                clean_text(summary.get("conclusion")),
                " ".join(summary_lines(summary.get("what_happened"))),
                clean_text(summary.get("life_impact")),
                clean_text(summary.get("next_action")),
            ]
        )
    tags = item.get("tags")
    if isinstance(tags, list):
        parts.extend(clean_text(tag) for tag in tags)
    flags = item.get("flags")
    if isinstance(flags, dict):
        parts.extend(clean_text(key) for key, value in flags.items() if value)
    return " ".join(part for part in parts if part).lower()


def item_source_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            clean_text(item.get("title")),
            clean_text(item.get("description")),
            clean_text(item.get("body_evidence_excerpt")),
        ]
    ).lower()


def summary_text(summary: dict[str, Any]) -> str:
    return " ".join(
        [
            clean_text(summary.get("conclusion")),
            " ".join(summary_lines(summary.get("what_happened"))),
            clean_text(summary.get("life_impact")),
            clean_text(summary.get("next_action")),
        ]
    )


def collect_item_text(item: dict[str, Any]) -> str:
    """Return a compact lower-cased text blob for conservative local guards."""
    parts: list[str] = []
    for key in ("title", "description", "source", "category"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    selected_summary = item.get("selected_summary")
    if isinstance(selected_summary, dict):
        for value in selected_summary.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(part) for part in value if part)
    return " ".join(parts).lower()


def item_needs_groq(item: dict[str, Any]) -> bool:
    rendered_summary = fallback_renderer.build_display_summary(item)
    fields = [
        clean_text(rendered_summary.get("conclusion")),
        clean_text(rendered_summary.get("life_impact")),
        clean_text(rendered_summary.get("next_action")),
        " ".join(summary_lines(rendered_summary.get("what_happened"))),
    ]
    meaningful_fields = [field for field in fields if field]
    if not meaningful_fields:
        return True
    return any(looks_english_or_bm(field) or looks_generic(field) for field in meaningful_fields)
