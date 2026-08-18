#!/usr/bin/env python3
from typing import Any

import render_malaysia_news_from_json as fallback_renderer
from malaysia_groq_common import (
    SAFE_FALLBACK_WHAT_HAPPENED_LINE,
    clean_text,
    contains_any,
    summary_lines,
)


SAFE_FALLBACK_CONCLUSION_LINE = "詳細を出典本文で確認しておきたいニュースです。"
JSON_RENDER_HEALTH_FALLBACK_NEXT_ACTION = "関係する場合は、関係当局や公式発表で対象者・時期・利用条件を確認してください。"
PUBLIC_TRANSPORT_ENTITY_CUES = [
    "rapid kl",
    "mrt",
    "lrt",
    "ktmb",
    "public transport",
    "train",
    "rail",
    "bus",
]
PUBLIC_TRANSPORT_SERVICE_CONTEXT_CUES = [
    "operation",
    "operations",
    "operating",
    "pengoperasian",
    "perkhidmatan",
    "service",
    "services",
    "route",
    "routes",
    "schedule",
    "schedules",
    "frequency",
    "frequencies",
    "extra trains",
    "train services",
    "feeder bus",
    "feeder buses",
    "ridership",
    "trips",
    "passenger",
    "passengers",
    "commuter",
    "commuters",
    "penumpang",
    "pengguna",
    "delay",
    "delays",
    "disruption",
    "disruptions",
    "congestion",
    "crowding",
    "kesesakan",
    "kelancaran pergerakan",
    "pergerakan",
]
COST_OF_LIVING_FALLBACK_CUES = [
    "budi diesel",
    "budi madani",
    "cash aid",
    "fuel aid",
    "fuel subsidy",
    "diesel subsidy",
    "petrol subsidy",
    "subsidised diesel",
    "subsidized diesel",
    "subsidy recipients",
    "cost of living aid",
    "barang keperluan",
    "jualan murah",
    "rahmah",
    "sumbangan asas rahmah",
    "program sara",
    "atm fee",
    "fee waiver",
    "interbank atm",
    "withdrawal fee",
    "harga",
    "price",
    "prices",
]


def json_fallback_topic_text(item: dict[str, Any]) -> str:
    """Build topic-classification evidence from article headline metadata only."""
    parts = [
        clean_text(item.get("title")),
        clean_text(item.get("description")),
    ]
    return " ".join(part for part in parts if part).lower()


def json_fallback_flags(item: dict[str, Any]) -> dict[str, Any]:
    flags = item.get("flags")
    return flags if isinstance(flags, dict) else {}


def has_public_transport_service_context(text: str) -> bool:
    return contains_any(text, PUBLIC_TRANSPORT_ENTITY_CUES) and contains_any(
        text,
        PUBLIC_TRANSPORT_SERVICE_CONTEXT_CUES,
    )


def has_cost_of_living_fallback_context(text: str) -> bool:
    return contains_any(text, COST_OF_LIVING_FALLBACK_CUES)


def high_confidence_json_fallback_topic(item: dict[str, Any]) -> str:
    text = json_fallback_topic_text(item)
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
    if flags.get("is_public_transport") and has_public_transport_service_context(text):
        return "public_transport"
    if (
        flags.get("is_health_system")
        or contains_any(text, ["health ministry", "moh", "hospital", "clinic", "healthcare", "public health"])
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
    if has_cost_of_living_fallback_context(text):
        return "cost_of_living"
    return ""


def safe_json_render_fallback_summary_for_item(
    item: dict[str, Any] | None,
    topic: str | None = None,
) -> dict[str, Any]:
    if not item:
        return {
            "conclusion": SAFE_FALLBACK_CONCLUSION_LINE,
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": "",
            "next_action": "",
            "suppress_topic_next_action": True,
        }
    topic = high_confidence_json_fallback_topic(item) if topic is None else topic
    if not topic:
        return {
            "conclusion": SAFE_FALLBACK_CONCLUSION_LINE,
            "what_happened": [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
            "life_impact": "",
            "next_action": "",
            "suppress_topic_next_action": True,
        }
    topic_text = fallback_renderer.TOPIC_TEXT.get(topic, {})
    next_action = clean_text(topic_text.get("next_action"))
    if topic == "health":
        next_action = JSON_RENDER_HEALTH_FALLBACK_NEXT_ACTION
    return {
        "conclusion": clean_text(topic_text.get("conclusion")) or SAFE_FALLBACK_CONCLUSION_LINE,
        "what_happened": summary_lines(topic_text.get("what_happened")) or [SAFE_FALLBACK_WHAT_HAPPENED_LINE],
        "life_impact": clean_text(topic_text.get("life_impact")),
        "next_action": next_action,
        "suppress_topic_next_action": False,
    }
