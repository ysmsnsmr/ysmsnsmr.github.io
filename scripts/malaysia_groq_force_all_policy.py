#!/usr/bin/env python3
import os
from typing import Any

from malaysia_groq_body_focus import body_evidence_focus_values, life_impact_matches_body_focus
from malaysia_groq_common import (
    clean_text,
    contains_any,
    has_any_search_phrase,
    item_needs_groq,
    item_search_text,
    looks_generic,
    summary_text,
)


DEFAULT_FORCE_ALL_REQUEST_CAP = 6

FINANCIAL_MARKET_PHRASES = [
    "ringgit",
    "bursa",
    "fbm klci",
    "foreign exchange",
    "forex",
    "currency",
    "stock market",
    "equities",
    "shares",
    "market sentiment",
    "us dollar",
    "greenback",
]
INCIDENT_PHRASES = [
    "accident",
    "crash",
    "collision",
    "murder",
    "rape",
    "molest",
    "molester",
    "harassment",
    "drug bust",
    "drug syndicate",
    "syndicate",
    "court",
    "charged",
    "pleaded",
    "jail",
    "caning",
    "probe",
    "macc",
    "sprm",
    "police arrested",
    "arrested",
]
POLITICS_PHRASES = [
    "umno",
    "pas",
    "dap",
    "pkr",
    "bersatu",
    "election",
    "by-election",
    "parliament",
    "mp says",
    "minister says",
    "opposition",
    "criticism",
    "party",
    "cabinet",
]
INTERNATIONAL_INCIDENT_PHRASES = [
    "gaza",
    "israel",
    "iran",
    "strait of hormuz",
    "selat hormuz",
    "vessel",
    "shipping lane",
    "war",
    "missile",
    "attack",
    "cruise ship",
    "hantavirus",
]
FORCE_ALL_SOURCE_LIFE_IMPACT_SIGNALS = [
    "application",
    "applications",
    "deadline",
    "eligibility",
    "eligible",
    "counter",
    "procedure",
    "permit",
    "licence",
    "license",
    "renewal",
    "subsidy",
    "aid",
    "ecoss",
    "cost of living",
    "price",
    "payment",
    "fee",
    "fare",
    "toll",
    "road tax",
    "jpj",
    "summons",
    "inspection",
    "recall",
    "safety defect",
    "lrt",
    "mrt",
    "ktm",
    "ktmb",
    "komuter",
    "rapid kl",
    "bus",
    "route",
    "station",
    "schedule",
    "disruption",
    "road closure",
    "highway",
    "rfid",
    "smarttag",
    "touch 'n go",
    "tng",
    "mykad",
    "lhdn",
    "tax",
    "e-derma",
    "hospital",
    "clinic",
    "school",
    "bank",
    "account",
    "branch",
    "e-wallet",
    "ewallet",
    "申請",
    "期限",
    "対象者",
    "対象条件",
    "窓口",
    "手続",
    "許可",
    "免許",
    "更新",
    "補助",
    "支援",
    "生活費",
    "価格",
    "支払い",
    "料金",
    "通行料",
    "道路税",
    "車検",
    "リコール",
    "安全",
    "運行",
    "路線",
    "駅",
    "時刻",
    "通勤",
    "通学",
    "決済",
    "医療",
    "学校",
    "銀行",
    "口座",
]
FORCE_ALL_SUMMARY_LIFE_IMPACT_SIGNALS = [
    "申請",
    "期限",
    "対象者",
    "対象条件",
    "窓口",
    "手続",
    "許可",
    "免許",
    "更新",
    "補助",
    "支援",
    "家計",
    "生活費",
    "価格",
    "物価",
    "支払い",
    "料金",
    "手数料",
    "通行料",
    "道路税",
    "召喚状",
    "車検",
    "リコール",
    "安全",
    "運行",
    "路線",
    "駅",
    "時刻",
    "通勤",
    "通学",
    "移動",
    "利用者",
    "迂回",
    "決済",
    "アプリ",
    "受診",
    "制度",
    "学校",
    "銀行",
    "口座",
    "顧客対応",
]
FORCE_ALL_TRANSPORT_MARKERS = [
    "ktm",
    "ktmb",
    "komuter",
    "lrt",
    "mrt",
    "rapid kl",
    "train",
    "rail",
    "bus",
    "public transport",
]
FORCE_ALL_TRANSPORT_OPERATIONAL_SIGNALS = [
    "route",
    "station",
    "fare",
    "schedule",
    "service disruption",
    "service delay",
    "service delays",
    "service closure",
    "service closures",
    "service frequency",
    "delay",
    "delayed",
    "disruption",
    "closure",
    "closed",
    "operat",
    "commute",
    "passenger",
    "運行",
    "路線",
    "駅",
    "料金",
    "時刻",
    "遅延",
    "混雑",
    "通勤",
    "通学",
    "利用者",
]
FORCE_ALL_POLITICAL_CONTEXT_SIGNALS = [
    "minister",
    "mp ",
    "mp says",
    "says",
    "invited",
    "seat at the table",
    "caretaker",
    "barisan",
    "umno",
    "party",
    "opposition",
    "election",
    "会談",
    "発言",
    "批判",
    "政党",
    "選挙",
]
FORCE_ALL_TRANSPORT_POLITICAL_INVITATION_SIGNALS = [
    "anthony loke",
    "loke",
    "onn hafiz",
    "invitation",
    "invite",
    "invited",
    "formal invite",
    "surat jemputan",
    "jemputan",
    "jumpa di kulai",
    "see you in kulai",
    "touched",
    "sincere",
    "seat at the table",
    "caretaker",
    "barisan",
    "umno",
    "dap",
    "pakatan harapan",
    "election",
    "招待",
    "発言",
    "政治",
]
FORCE_ALL_SCAM_INCIDENT_SIGNALS = [
    "scam",
    "fraud",
    "cheated",
    "online ipo",
    "police report",
    "lost rm",
    "returned after",
    "only rm",
    "詐欺",
    "被害",
]
FORCE_ALL_INDIVIDUAL_VICTIM_SIGNALS = [
    "retiree",
    "victim",
    "79-year-old",
    "man",
    "woman",
    "aged",
    "invests",
    "invested",
    "lost",
    "kuching",
    "sibu",
    "police",
    "report",
    "男性",
    "女性",
    "個人",
]
FORCE_ALL_MONEY_BACKGROUND_SIGNALS = [
    "ringgit",
    "bursa",
    "fbm klci",
    "foreign exchange",
    "forex",
    "currency",
    "stock market",
    "equities",
    "shares",
    "market sentiment",
    "us dollar",
    "greenback",
    "為替",
    "相場",
    "株式",
    "市場",
]
FORCE_ALL_MONEY_CONCRETE_SIGNALS = [
    "subsidy",
    "aid",
    "cost of living",
    "payment",
    "fee",
    "bank",
    "account",
    "branch",
    "e-wallet",
    "ewallet",
    "補助",
    "支援",
    "生活費",
    "支払い",
    "手数料",
    "銀行",
    "口座",
    "窓口",
]
PAUL_TAN_FORCE_ALL_POSITIVE_SIGNALS = [
    "jpj",
    "licence",
    "license",
    "road tax",
    "summons",
    "inspection",
    "enforcement",
    "recall",
    "safety",
    "ron95",
    "diesel",
    "petrol",
    "fuel subsidy",
    "toll",
    "rfid",
    "smarttag",
    "road closure",
    "highway",
    "lrt",
    "mrt",
    "rapid kl",
    "ktmb",
    "bus",
    "public transport",
]
PAUL_TAN_FORCE_ALL_NOISE_SIGNALS = [
    "registration",
    "registrations",
    "sales",
    "market share",
    "ranking",
    "rankings",
    "top",
    "brand",
    "model",
    "variant",
    "launch",
    "preview",
    "review",
    "spyshot",
    "showroom",
]


def is_financial_market_item(item: dict[str, Any]) -> bool:
    return has_any_search_phrase(item_search_text(item), FINANCIAL_MARKET_PHRASES)


def is_incident_item(item: dict[str, Any]) -> bool:
    return has_any_search_phrase(item_search_text(item), INCIDENT_PHRASES)


def is_politics_item(item: dict[str, Any]) -> bool:
    return has_any_search_phrase(item_search_text(item), POLITICS_PHRASES)


def is_international_incident_item(item: dict[str, Any]) -> bool:
    return has_any_search_phrase(item_search_text(item), INTERNATIONAL_INCIDENT_PHRASES)


def groq_exclusion_reason(item: dict[str, Any]) -> str:
    if is_financial_market_item(item):
        return "financial_market"
    if is_incident_item(item):
        return "incident"
    if is_politics_item(item):
        return "politics"
    if is_international_incident_item(item):
        return "international_incident"
    return ""


def force_all_source_text(item: dict[str, Any]) -> str:
    parts = [
        clean_text(item.get("title")),
        clean_text(item.get("description")),
        clean_text(item.get("source")),
        clean_text(item.get("category")),
        clean_text(item.get("body_evidence_excerpt")),
    ]
    tags = item.get("tags")
    if isinstance(tags, list):
        parts.extend(clean_text(tag) for tag in tags)
    flags = item.get("flags")
    if isinstance(flags, dict):
        parts.extend(clean_text(key) for key, value in flags.items() if value)
    return " ".join(part for part in parts if part).lower()


def force_all_summary_text(summary: dict[str, Any]) -> str:
    return summary_text(summary).lower()


def has_force_all_body_evidence(item: dict[str, Any], summary: dict[str, Any]) -> bool:
    focus_values = body_evidence_focus_values(item)
    if not focus_values:
        return False
    return life_impact_matches_body_focus(item, clean_text(summary.get("life_impact")))


def is_paul_tan_source(item: dict[str, Any]) -> bool:
    return clean_text(item.get("source")).lower() == "paul tan"


def paul_tan_force_all_gate_reason(source_text: str) -> str:
    has_positive = contains_any(source_text, PAUL_TAN_FORCE_ALL_POSITIVE_SIGNALS)
    has_noise = contains_any(source_text, PAUL_TAN_FORCE_ALL_NOISE_SIGNALS)
    has_driver_obligation = contains_any(
        source_text,
        [
            "licence",
            "license",
            "road tax",
            "summons",
            "inspection",
            "enforcement",
            "recall",
            "safety",
            "fuel subsidy",
            "toll",
            "road closure",
            "public transport",
        ],
    )
    if has_noise and not has_driver_obligation:
        return "paul_tan_noise_without_driver_impact"
    if not has_positive:
        return "paul_tan_no_transport_driver_signal"
    return ""


def force_all_gate_reason(item: dict[str, Any], summary: dict[str, Any]) -> str:
    """Return a rejection reason for force-all accepted summaries, or empty string when safe."""
    source_text = force_all_source_text(item)
    rendered_text = force_all_summary_text(summary)
    focus_values = body_evidence_focus_values(item)

    if is_paul_tan_source(item):
        reason = paul_tan_force_all_gate_reason(source_text)
        if reason:
            return reason

    has_transport_marker = contains_any(source_text, FORCE_ALL_TRANSPORT_MARKERS)
    has_transport_operation = contains_any(source_text, FORCE_ALL_TRANSPORT_OPERATIONAL_SIGNALS)
    has_political_context = contains_any(source_text, FORCE_ALL_POLITICAL_CONTEXT_SIGNALS)
    has_transport_focus = "transport_or_infra" in focus_values
    has_transport_invitation_context = contains_any(source_text, FORCE_ALL_TRANSPORT_POLITICAL_INVITATION_SIGNALS)
    if (has_transport_marker or has_transport_focus) and has_transport_invitation_context:
        return "transport_political_invitation_context"
    if (has_transport_marker or has_transport_focus) and has_political_context and not has_transport_operation:
        return "transport_political_background_without_operational_impact"

    has_scam_incident = contains_any(source_text, FORCE_ALL_SCAM_INCIDENT_SIGNALS)
    has_individual_victim = contains_any(source_text, FORCE_ALL_INDIVIDUAL_VICTIM_SIGNALS)
    if has_scam_incident and has_individual_victim:
        return "individual_scam_incident"

    if has_force_all_body_evidence(item, summary):
        return ""

    has_money_background = contains_any(source_text, FORCE_ALL_MONEY_BACKGROUND_SIGNALS)
    has_money_concrete = contains_any(source_text, FORCE_ALL_MONEY_CONCRETE_SIGNALS)
    if has_money_background and not has_money_concrete:
        return "money_market_background_without_concrete_life_impact"

    source_has_signal = contains_any(source_text, FORCE_ALL_SOURCE_LIFE_IMPACT_SIGNALS)
    if not source_has_signal:
        return "no_strong_source_life_impact_signal"

    if looks_generic(clean_text(summary.get("life_impact"))):
        return "generic_life_impact"

    summary_has_signal = contains_any(rendered_text, FORCE_ALL_SUMMARY_LIFE_IMPACT_SIGNALS)
    if not summary_has_signal:
        return "no_strong_summary_life_impact_signal"

    return ""


def force_all_pre_request_skip_reason(item: dict[str, Any]) -> str:
    """Skip force-all requests that are known to be low-value before calling Groq."""
    source_text = force_all_source_text(item)
    focus_values = body_evidence_focus_values(item)

    if is_paul_tan_source(item):
        reason = paul_tan_force_all_gate_reason(source_text)
        if reason:
            return reason

    has_transport_marker = contains_any(source_text, FORCE_ALL_TRANSPORT_MARKERS)
    has_transport_focus = "transport_or_infra" in focus_values
    if (has_transport_marker or has_transport_focus) and contains_any(
        source_text, FORCE_ALL_TRANSPORT_POLITICAL_INVITATION_SIGNALS
    ):
        return "transport_political_invitation_context"

    if contains_any(source_text, FORCE_ALL_SCAM_INCIDENT_SIGNALS) and contains_any(
        source_text, FORCE_ALL_INDIVIDUAL_VICTIM_SIGNALS
    ):
        return "individual_scam_incident"

    if contains_any(source_text, FORCE_ALL_MONEY_BACKGROUND_SIGNALS) and not contains_any(
        source_text, FORCE_ALL_MONEY_CONCRETE_SIGNALS
    ):
        return "money_market_background_without_concrete_life_impact"

    return ""


def force_all_request_priority(item: dict[str, Any]) -> int:
    """Rank force-all request candidates so likely concrete items stay within the cap."""
    source_text = force_all_source_text(item)
    score = 0
    focus_values = body_evidence_focus_values(item)
    if focus_values:
        score += 100
        if any(
            focus in focus_values
            for focus in (
                "procedure_or_public_service",
                "cost_or_subsidy",
                "consumer_or_payment",
                "health_or_education",
                "financial_service_access",
            )
        ):
            score += 30
        if "transport_or_infra" in focus_values and contains_any(
            source_text, FORCE_ALL_TRANSPORT_OPERATIONAL_SIGNALS
        ):
            score += 25
    if contains_any(source_text, FORCE_ALL_MONEY_CONCRETE_SIGNALS):
        score += 45
    if contains_any(source_text, ["subsidy", "aid", "bantuan", "voucher", "補助", "支援"]):
        score += 35
    if contains_any(source_text, ["application", "deadline", "permit", "dbkl", "lhdn", "申請", "期限", "手続"]):
        score += 30
    if contains_any(source_text, ["health", "medical", "hospital", "clinic", "rawatan", "医療", "受診"]):
        score += 30
    if contains_any(source_text, FORCE_ALL_TRANSPORT_OPERATIONAL_SIGNALS):
        score += 20
    if item_needs_groq(item):
        score += 10
    return score


def force_all_request_cap() -> int:
    raw_value = os.getenv("MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP", "").strip()
    if not raw_value:
        return DEFAULT_FORCE_ALL_REQUEST_CAP
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_FORCE_ALL_REQUEST_CAP
    return max(0, value)


def ordered_force_all_entries(items: list[Any]) -> list[tuple[int, dict[str, Any]]]:
    entries = [(index, item) for index, item in enumerate(items) if isinstance(item, dict)]
    return sorted(entries, key=lambda entry: (-force_all_request_priority(entry[1]), entry[0]))
