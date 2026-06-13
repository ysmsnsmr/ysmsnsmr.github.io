#!/usr/bin/env python3
import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_malaysia_news_from_json as fallback_renderer


DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
MAX_RESPONSE_CHARS = 4000
TIMEOUT_SECONDS = 30
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
WEATHER_IMPACT_WORDS = [
    "weather",
    "rain",
    "storm",
    "thunderstorm",
    "heavy rain",
    "ribut",
    "hujan",
    "天候",
    "気象",
    "雨",
    "大雨",
    "雷雨",
    "強風",
    "警報",
    "外出",
]
HEAT_IMPACT_WORDS = [
    "heat",
    "hot weather",
    "heatstroke",
    "heat stroke",
    "strok haba",
    "暑さ",
    "熱中症",
    "水分",
    "屋外",
    "体調",
]
FLOOD_IMPACT_WORDS = [
    "flood",
    "flash flood",
    "banjir",
    "冠水",
    "洪水",
    "浸水",
    "低地",
    "排水",
]
ROAD_TRANSPORT_IMPACT_WORDS = [
    "road",
    "jalan",
    "traffic",
    "closure",
    "closed",
    "congestion",
    "route",
    "commute",
    "public transport",
    "train",
    "bus",
    "mrt",
    "lrt",
    "ktmb",
    "道路",
    "閉鎖",
    "交通",
    "渋滞",
    "迂回",
    "移動",
    "通勤",
    "通学",
    "運行",
    "公共交通",
]
FINANCIAL_IMPACT_WORDS = [
    "market",
    "investment",
    "investor",
    "stock",
    "currency",
    "ringgit",
    "bursa",
    "forex",
    "投資",
    "投資判断",
    "市場",
    "株式",
    "為替",
    "金融",
    "相場",
]
POLICY_EDUCATION_IMPACT_WORDS = [
    "policy",
    "application",
    "education",
    "school",
    "admission",
    "制度",
    "申請",
    "手続",
    "進学",
    "教育制度",
    "入学",
]
COST_IMPACT_WORDS = [
    "cost of living",
    "price",
    "prices",
    "subsidy",
    "aid",
    "rahmah",
    "kos sara hidup",
    "家計",
    "生活費",
    "日用品",
    "価格",
    "物価",
    "支援",
    "補助",
    "買い物",
]
HEALTH_IMPACT_WORDS = [
    "health",
    "healthcare",
    "medical",
    "hospital",
    "disease",
    "infection",
    "健康",
    "医療",
    "体調",
    "感染",
    "症状",
    "公衆衛生",
    "医療機関",
]
BACKGROUND_IMPACT_WORDS = [
    "背景情報",
    "当局対応",
    "関連制度",
    "確認しておく価値",
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

SYSTEM_PROMPT = """あなたはマレーシア在住者向けニュースダッシュボードの日本語編集者です。
入力はRSSのtitle、description、既存summary、必要に応じてbody_evidenceだけです。
body_evidenceがない場合はRSSの情報だけを使ってください。
body_evidenceは本文から抽出・掃除された短い証拠です。body_evidenceにない事実や生活影響を推測で足さないでください。
body_evidence.forbiddenに示された要素（dateline、wire credit、広告、関連記事、根拠のない条件など）は出力に使わないでください。
入力にない事実を追加しないでください。
カテゴリ、出典、URL、日付は変更しないでください。
英語またはマレー語の文を、自然で短い日本語に整えてください。
dateline（例: KUALA LUMPUR, May 17 — / クアラルンプール、5月17日 -）は出力しないでください。
人名や機関名は必要な場合だけ短く使ってください。
制度名や略称は無理に翻訳せず、入力にある略称を保持してください。
eCOSSは「eCOSS（食用油価格安定化制度）」と表記してください。
conclusionは30〜45字程度の自然な日本語にしてください。
titleにある主要な具体要素を落とさないでください。
what_happenedはRSS title/descriptionにある事実だけで、最大2文にしてください。
life_impactでは「生活・仕事・家計に関わる背景ニュース」のような汎用文を避けてください。
body_evidence.focusがある場合、life_impactはfocusに沿って具体化してください。
focusがprocedure_or_public_serviceなら、申請・期限・対象者・窓口・手続き変更に関する影響として書いてください。
focusがcost_or_subsidyなら、家計・価格・補助・対象条件・支払いに関する影響として書いてください。
focusがtransport_or_infraなら、運行・道路・通勤・移動・利用者影響として書いてください。
focusがconsumer_or_paymentなら、決済・アプリ・利用手段・手数料に関する影響として書いてください。
focusがhealth_or_educationなら、受診・制度・学校・対象者に関する影響として書いてください。
focusがfinancial_service_accessなら、銀行や金融サービス利用・窓口・顧客対応に関する影響として書いてください。
body_evidence.focusが空、またはevidenceが弱い場合だけ、控えめな背景情報として書いてください。
影響が分からない場合は「制度や進学条件に関わる背景情報として確認しておく価値があります。」程度にしてください。
RSSにない事実、対象者、影響、次アクションを足さないでください。
“lost students”, “losing students” は死亡を意味すると明確でない限り、「生徒の利用が減った」「利用者を失った」「生徒が乗らなくなった」のように訳してください。
死亡、事故、被害、収入減などはRSSに明記されていない限り書かないでください。
個人の苦境・個別事例では、life_impactは広げすぎず「関連制度や当局対応を知る背景情報です」程度に留めてください。
“funeral transport” は文脈上「葬儀関連の送迎」「葬儀向け送迎」など、車両そのものを断定しすぎない表現にしてください。
conclusionは自然な日本語にしつつ、titleにない因果関係を強めないでください。
what_happenedは重複した内容を2行にしないでください。2行目が1行目と同じ意味なら1行だけにしてください。
life_impactはRSSに具体的な生活影響がない場合、無理に個人の収入・生活への影響を作らないでください。
個別事例では、読者の生活への直接影響を断定せず、制度・当局対応・地域事情の背景情報として控えめに述べてください。
出力はJSONのみです。"""


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


def normalize_summary(value: Any) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    return {
        "conclusion": clean_text(summary.get("conclusion")),
        "what_happened": summary_lines(summary.get("what_happened")),
        "life_impact": clean_text(summary.get("life_impact")),
        "next_action": clean_text(summary.get("next_action")),
    }


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
        "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります",
        "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。",
        "背景ニュースとして",
        "把握しておく価値があります",
        "rssでは",
        "rssの情報では",
    ]
    lower_text = text.lower()
    return any(phrase.lower() in lower_text for phrase in generic_phrases)


BODY_FOCUS_LIFE_IMPACT_CUES = {
    "procedure_or_public_service": [
        "申請",
        "期限",
        "対象",
        "窓口",
        "手続き",
        "制度",
        "利用",
        "確認",
    ],
    "cost_or_subsidy": [
        "家計",
        "価格",
        "補助",
        "対象",
        "支払い",
        "負担",
        "生活費",
        "費用",
    ],
    "transport_or_infra": [
        "運行",
        "道路",
        "通勤",
        "移動",
        "利用者",
        "交通",
        "路線",
        "駅",
    ],
    "consumer_or_payment": [
        "決済",
        "アプリ",
        "利用",
        "手数料",
        "支払い",
        "カード",
        "サービス",
    ],
    "health_or_education": [
        "受診",
        "医療",
        "制度",
        "学校",
        "対象",
        "学生",
        "教育",
        "健康",
    ],
    "financial_service_access": [
        "銀行",
        "金融",
        "窓口",
        "顧客",
        "口座",
        "サービス",
        "利用",
    ],
}


def body_evidence_focus_values(item: dict[str, Any]) -> list[str]:
    if item.get("body_excerpt_policy") != "use_body":
        return []
    focus = item.get("body_evidence_focus")
    if not isinstance(focus, list):
        return []
    return [clean_text(value) for value in focus if clean_text(value)]


def life_impact_matches_body_focus(item: dict[str, Any], life_impact: str) -> bool:
    focus_values = body_evidence_focus_values(item)
    if not focus_values:
        return True
    text = clean_text(life_impact)
    if not text:
        return False
    if looks_generic(text):
        return False
    allowed_cues: list[str] = []
    for focus in focus_values:
        allowed_cues.extend(BODY_FOCUS_LIFE_IMPACT_CUES.get(focus, []))
    if not allowed_cues:
        return True
    return any(cue in text for cue in allowed_cues)


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


def groq_payload_for_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "category": item.get("category"),
        "source": item.get("source"),
        "published_date": item.get("published_date"),
        "title": item.get("title"),
        "description": item.get("description"),
        "selected_summary": normalize_summary(item.get("selected_summary")),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "flags": item.get("flags") if isinstance(item.get("flags"), dict) else {},
    }
    if item.get("body_excerpt_policy") == "use_body":
        evidence_excerpt = clean_text(item.get("body_evidence_excerpt"))
        if evidence_excerpt:
            focus = item.get("body_evidence_focus")
            forbidden = item.get("body_evidence_forbidden")
            payload["body_evidence"] = {
                "excerpt": evidence_excerpt,
                "focus": focus if isinstance(focus, list) else [],
                "forbidden": forbidden if isinstance(forbidden, list) else [],
                "policy": item.get("body_excerpt_policy"),
                "reason": item.get("body_excerpt_reason"),
                "content_source": item.get("content_source"),
            }
    return payload


def is_enriched_json(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("body_enrichment"), dict):
        return True
    items = data.get("items")
    if not isinstance(items, list):
        return False
    return any(isinstance(item, dict) and "body_excerpt_policy" in item for item in items)


def resolve_json_input(path: str) -> Path:
    input_path = Path(path)
    if not input_path.exists():
        return input_path
    try:
        data = fallback_renderer.load_json(str(input_path))
    except Exception:
        return input_path
    if is_enriched_json(data):
        return input_path
    enriched_candidates = [
        input_path.with_name(f"{input_path.stem}_enriched{input_path.suffix}"),
        input_path.with_name("selected_items_enriched.json"),
    ]
    for enriched_path in enriched_candidates:
        if not enriched_path.exists():
            continue
        try:
            enriched_data = fallback_renderer.load_json(str(enriched_path))
        except Exception:
            continue
        if is_enriched_json(enriched_data):
            return enriched_path
    return input_path


def strip_json_code_fence(content: str) -> str:
    text = content.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def debug_groq_payload(index: int, item: dict[str, Any], parsed: Any | None = None, reason: str = "") -> None:
    title = clean_text(item.get("title"))[:80]
    if parsed is None:
        keys_text = "n/a"
    elif isinstance(parsed, dict):
        keys_text = ", ".join(sorted(str(key) for key in parsed.keys()))
    else:
        keys_text = type(parsed).__name__
    reason_text = f" reason={reason}" if reason else ""
    safe_log(f"groq-debug: item={index + 1} title={title!r} parsed_keys={keys_text}{reason_text}")


def parse_groq_content(content: str) -> Any:
    cleaned_content = strip_json_code_fence(content)
    return json.loads(cleaned_content)


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


def has_any_text(text: str, phrases: list[str]) -> bool:
    return any(phrase.lower() in text for phrase in phrases)


def rendered_has_japanese_unit_for_number(rendered_text: str, number: str, units: list[str]) -> bool:
    """Return true when Groq reused an English magnitude number with a Japanese unit."""
    if not number:
        return False
    normalized_number = re.escape(number.rstrip("."))
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    return re.search(rf"(?<![0-9]){normalized_number}\s*(?:{unit_pattern})", rendered_text) is not None


def reject_numeric_unit_reason(source_text: str, rendered_text: str) -> str:
    """Conservatively reject obvious magnitude/unit conversions that are unsafe to publish."""
    billion_patterns = [
        r"\bRM\s*([0-9]+(?:\.[0-9]+)?)\s*(?:b|bn|billion)\b",
        r"\b([0-9]+(?:\.[0-9]+)?)\s*billion\b",
    ]
    for pattern in billion_patterns:
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            number = match.group(1)
            if rendered_has_japanese_unit_for_number(rendered_text, number, ["億", "億リンギット", "万人"]):
                return f"unsafe numeric unit conversion: {match.group(0)}"

    for match in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s*million\b", source_text, flags=re.IGNORECASE):
        number = match.group(1)
        if rendered_has_japanese_unit_for_number(rendered_text, number, ["万人", "万"]):
            return f"unsafe numeric unit conversion: {match.group(0)}"

    return ""


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
    if (has_transport_marker or has_transport_focus) and has_political_context and not has_transport_operation:
        return "transport_political_background_without_operational_impact"

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


def reject_life_impact_reason(topic: str, item: dict[str, Any], life_impact: str) -> str:
    normalized_topic = normalize_topic(topic)
    impact_text = clean_text(life_impact).lower()
    if not normalized_topic or not impact_text:
        return ""
    if contains_any(impact_text, BACKGROUND_IMPACT_WORDS):
        return ""

    source_text = item_source_text(item)

    def source_supports(words: list[str]) -> bool:
        return contains_any(source_text, words)

    topic_expected_words = {
        "storm_weather": WEATHER_IMPACT_WORDS + ROAD_TRANSPORT_IMPACT_WORDS,
        "heat_weather": HEAT_IMPACT_WORDS + HEALTH_IMPACT_WORDS,
        "flood": FLOOD_IMPACT_WORDS + ROAD_TRANSPORT_IMPACT_WORDS + WEATHER_IMPACT_WORDS,
        "road_closure": ROAD_TRANSPORT_IMPACT_WORDS,
        "public_transport": ROAD_TRANSPORT_IMPACT_WORDS,
        "cost_of_living": COST_IMPACT_WORDS,
        "health": HEALTH_IMPACT_WORDS,
        "currency": FINANCIAL_IMPACT_WORDS,
        "market": FINANCIAL_IMPACT_WORDS,
    }
    if contains_any(impact_text, topic_expected_words.get(normalized_topic, [])):
        return ""

    mismatches = {
        "storm_weather": [
            ("financial", FINANCIAL_IMPACT_WORDS),
            ("policy_education", POLICY_EDUCATION_IMPACT_WORDS),
        ],
        "heat_weather": [
            ("road_transport", ROAD_TRANSPORT_IMPACT_WORDS),
            ("flood", FLOOD_IMPACT_WORDS),
            ("financial", FINANCIAL_IMPACT_WORDS),
        ],
        "road_closure": [
            ("health", HEALTH_IMPACT_WORDS),
            ("financial", FINANCIAL_IMPACT_WORDS),
            ("policy_education", POLICY_EDUCATION_IMPACT_WORDS),
        ],
        "public_transport": [
            ("financial", FINANCIAL_IMPACT_WORDS),
            ("health", HEALTH_IMPACT_WORDS),
            ("weather", WEATHER_IMPACT_WORDS + HEAT_IMPACT_WORDS),
        ],
        "cost_of_living": [
            ("road_transport", ROAD_TRANSPORT_IMPACT_WORDS),
            ("weather", WEATHER_IMPACT_WORDS + HEAT_IMPACT_WORDS),
            ("health", HEALTH_IMPACT_WORDS),
        ],
        "health": [
            ("financial", FINANCIAL_IMPACT_WORDS),
            ("road_transport", ROAD_TRANSPORT_IMPACT_WORDS),
        ],
    }
    for reason, words in mismatches.get(normalized_topic, []):
        if contains_any(impact_text, words) and not source_supports(words):
            return reason
    return ""


def validate_summary_against_source(item: dict[str, Any], summary: dict[str, Any]) -> None:
    source_text = item_source_text(item)
    rendered_text = summary_text(summary)
    rendered_lower = rendered_text.lower()

    if "学生を失った" in rendered_text and not has_any_text(source_text, ["death", "dead", "died", "killed", "fatal", "meninggal", "maut"]):
        raise ValueError("unsafe losing students wording")

    english_lead_markers = [
        "KUALA LUMPUR, May ",
        "PUTRAJAYA, May ",
        "IPOH, May ",
        "ALOR SETAR, May ",
        "GEORGE TOWN, May ",
        "JOHOR BARU, May ",
        "KOTA KINABALU, May ",
        "KUCHING, May ",
        "— The ",
        "— A ",
        "— An ",
        "— Prime Minister ",
        "The Domestic Trade and Cost of Living Ministry",
    ]
    if any(marker in rendered_text for marker in english_lead_markers):
        raise ValueError("english lead leakage")

    numeric_unit_reason = reject_numeric_unit_reason(source_text, rendered_text)
    if numeric_unit_reason:
        raise ValueError(numeric_unit_reason)

    guarded_claims = {
        "death": ["死亡", "亡くな", "死者"],
        "accident": ["事故"],
        "damage": ["被害"],
        "income_loss": ["収入減", "収入が減", "所得減", "売上減"],
    }
    source_evidence = {
        "death": ["death", "dead", "died", "killed", "fatal", "meninggal", "maut"],
        "accident": ["accident", "crash", "collision", "kemalangan"],
        "damage": ["damage", "damaged", "losses", "kerosakan", "被害"],
        "income_loss": ["income", "revenue", "earnings", "salary", "wage", "fare", "lost students", "losing students"],
    }
    for claim, phrases in guarded_claims.items():
        if any(phrase in rendered_text for phrase in phrases) and not has_any_text(source_text, source_evidence[claim]):
            raise ValueError(f"unsupported {claim} claim")

    if has_any_text(rendered_lower, ["生活への影響が大きい", "家計に直接影響", "収入に影響", "生活を圧迫"]) and not has_any_text(
        source_text,
        ["cost", "price", "fare", "income", "revenue", "salary", "wage", "living", "kos sara hidup", "tambang"],
    ):
        raise ValueError("unsupported life impact")


    life_impact_text = summary.get("life_impact", "")
    if not life_impact_matches_body_focus(item, life_impact_text):
        raise ValueError("generic life_impact for body_evidence focus")

    if "進学条件" in life_impact_text:
        admission_evidence = [
            "admission",
            "entrance",
            "university entry",
            "school requirement",
            "exam requirement",
            "entry requirement",
            "入学",
            "進学",
            "受験",
            "出願",
            "入試",
        ]
        if not has_any_text(source_text, admission_evidence):
            raise ValueError("unsupported admission requirement claim")

    topic = normalize_topic(fallback_renderer.detect_topic(item))
    reason = reject_life_impact_reason(topic, item, summary["life_impact"])
    if reason:
        raise ValueError(f"life_impact topic mismatch: {reason}")



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


def is_enforcement_or_misuse_item(item: dict[str, Any]) -> bool:
    """Skip Groq for narrow enforcement/misuse articles where display gains are low."""
    text = collect_item_text(item)
    keywords = [
        "raid",
        "raids",
        "seized",
        "seize",
        "siphon",
        "siphoning",
        "misuse",
        "fleet card",
        "enforcement",
        "probe",
        "probes",
        "investigate",
        "investigating",
        "spot check",
        "spot checks",
    ]
    return any(keyword in text for keyword in keywords)


def normalize_malaysia_terms_in_text(text: str, item: dict[str, Any]) -> str:
    """Normalize recurring Malaysia-government terms after Groq generation."""
    if not text:
        return text

    source_text = collect_item_text(item)
    source_lower = source_text.lower()
    has_ecoss_evidence = (
        "ecoss" in source_lower
        or "cooking oil price stabilisation scheme" in source_lower
        or "cooking oil price stabilization scheme" in source_lower
    )

    replacements = {
        "国内取引・生活費省": "国内貿易・生活費省",
        "国内取引省": "国内貿易省",
        "車両カード": "フリートカード",
        "油価": "石油価格",
    }

    if "kpdn" in source_text or "domestic trade" in source_text:
        replacements.update(
            {
                "商務省": "国内貿易・生活費省",
                "ケダ州商務省": "ケダ州国内貿易・生活費省",
            }
        )

    if has_ecoss_evidence:
        ecoss_label = "eCOSS（食用油価格安定化制度）"
        replacements.update(
            {
                "食用石油価格格安定化制度(eCOSS)": ecoss_label,
                "食用石油価格格安定化制度（eCOSS）": ecoss_label,
                "食用油価格格安定化制度(eCOSS)": ecoss_label,
                "食用油価格格安定化制度（eCOSS）": ecoss_label,
                "食用石油価格安定化制度(eCOSS)": ecoss_label,
                "食用石油価格安定化制度（eCOSS）": ecoss_label,
                "食用油価格安定化制度(eCOSS)": ecoss_label,
                "食用油価格安定化制度（eCOSS）": ecoss_label,
                "食用石油価格格安定化制度": ecoss_label,
                "食用油価格格安定化制度": ecoss_label,
                "食用石油価格安定化制度": ecoss_label,
                "食用油価格安定化制度": ecoss_label,
                "食用石油価格安定制度": ecoss_label,
                "食用油価格安定制度": ecoss_label,
                "eCOSS制度": ecoss_label,
                "eCOSS 制度": ecoss_label,
            }
        )

    for old, new in replacements.items():
        text = text.replace(old, new)
    if has_ecoss_evidence:
        ecoss_label = "eCOSS（食用油価格安定化制度）"
        text = re.sub(
            r"食用(?:石)?(?:石油|油)価格(?:格)?(?:格安|安定)定?化?制度[（(]eCOSS[）)]",
            ecoss_label,
            text,
        )
        text = re.sub(
            r"食用(?:石)?(?:石油|油)価格(?:格)?(?:格安|安定)定?化?制度",
            ecoss_label,
            text,
        )
        nested_ecoss_label = f"eCOSS（{ecoss_label}）"
        while nested_ecoss_label in text:
            text = text.replace(nested_ecoss_label, ecoss_label)
    return text


def normalize_malaysia_terms(summary: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Normalize terms in a Groq summary while preserving the summary schema."""
    normalized = dict(summary)
    for key in ("conclusion", "life_impact", "next_action"):
        if isinstance(normalized.get(key), str):
            normalized[key] = normalize_malaysia_terms_in_text(normalized[key], item)
    if isinstance(normalized.get("what_happened"), list):
        normalized["what_happened"] = [
            normalize_malaysia_terms_in_text(str(line), item)
            for line in normalized["what_happened"]
            if line
        ]
    return normalized

def request_groq_summary(item: dict[str, Any], api_key: str, model: str, debug: bool = False, index: int = 0) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(groq_payload_for_item(item), ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 500,
        "stream": False,
    }
    if model.startswith("openai/gpt-oss-"):
        body["include_reasoning"] = False
        body["reasoning_effort"] = "low"
    else:
        body["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        GROQ_CHAT_COMPLETIONS_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        response_body = response.read(MAX_RESPONSE_CHARS + 1).decode("utf-8", errors="replace")
    if len(response_body) > MAX_RESPONSE_CHARS:
        raise ValueError("Groq response too long")
    payload = json.loads(response_body)
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Groq response content is empty")
    if len(content) > MAX_RESPONSE_CHARS:
        raise ValueError("Groq message content too long")
    parsed_content = parse_groq_content(content)
    if debug:
        debug_groq_payload(index, item, parsed_content)
    summary = validate_groq_summary(parsed_content)
    summary = normalize_malaysia_terms(summary, item)
    validate_summary_against_source(item, summary)
    return summary


def validate_groq_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("summary is not object")
    if isinstance(value.get("selected_summary"), dict):
        value = value["selected_summary"]
    conclusion = clean_text(value.get("conclusion"))
    raw_what_happened = value.get("what_happened")
    if isinstance(raw_what_happened, str):
        raw_what_happened = [raw_what_happened]
    what_happened = summary_lines(raw_what_happened)
    life_impact = clean_text(value.get("life_impact"))
    next_action = clean_text(value.get("next_action"))
    if not conclusion:
        raise ValueError("missing conclusion")
    if not isinstance(raw_what_happened, list):
        raise ValueError("what_happened is not list")
    if not what_happened:
        raise ValueError("missing what_happened")
    if not life_impact:
        raise ValueError("missing life_impact")
    return {
        "conclusion": conclusion,
        "what_happened": what_happened[:2],
        "life_impact": life_impact,
        "next_action": next_action,
    }


def safe_log(message: str) -> None:
    print(message, file=sys.stderr)


def build_improved_items_payload(
    accepted_records: list[dict[str, Any]],
    model: str,
    stats: dict[str, int],
    now: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "malaysia-groq-improved-items/v1",
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "model": model,
        "counts": {
            "requested": stats.get("requested", 0),
            "accepted": stats.get("accepted", 0),
            "fallback": stats.get("fallback", 0),
        },
        "items": accepted_records,
    }


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def accepted_only_render_data(data: dict[str, Any], accepted_records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted_indexes = {
        record.get("index")
        for record in accepted_records
        if isinstance(record, dict) and isinstance(record.get("index"), int)
    }
    render_data = copy.deepcopy(data)
    items = render_data.get("items", [])
    if not isinstance(items, list):
        render_data["items"] = []
    else:
        render_data["items"] = [
            item
            for index, item in enumerate(items, start=1)
            if isinstance(item, dict) and index in accepted_indexes
        ]
    counts = render_data.get("counts")
    if isinstance(counts, dict):
        counts["selected"] = len(render_data["items"])
    return render_data


def accepted_only_empty_markdown(model: str, stats: dict[str, int]) -> str:
    return "\n".join(
        [
            "# Groq Accepted Items",
            "",
            "No Groq-accepted items were available for this artifact.",
            "",
            "RSS fallback and non-accepted items are intentionally not rendered in accepted-only Markdown.",
            "",
            f"- model: {model}",
            f"- requested: {stats.get('requested', 0)}",
            f"- accepted: {stats.get('accepted', 0)}",
            f"- fallback: {stats.get('fallback', 0)}",
        ]
    )


RSS_ITEM_BLOCK_RE = re.compile(r"(?ms)^- 結論：.*?\n- 出典元URL：(?P<link>[^\n]+)\n?")
RSS_FALLBACK_DATELINE_RE = re.compile(
    r"(?m)(- 何が起きた：)"
    r"(?:KUALA LUMPUR|PUTRAJAYA|MELAKA|GEORGE TOWN|IPOH|ALOR SETAR|JOHOR BARU|KOTA KINABALU|KUCHING),\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2}\s+[—–-]\s*"
)


def strip_rss_fallback_datelines(block: str) -> str:
    """Clean RSS-rendered fallback blocks only in merge-candidate Markdown."""
    return RSS_FALLBACK_DATELINE_RE.sub(r"\1", block)


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


def merge_accepted_with_rss_markdown(rss_markdown: str, accepted_records: list[dict[str, Any]]) -> str:
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
        return strip_rss_fallback_datelines(match.group(0))

    return RSS_ITEM_BLOCK_RE.sub(replace_block, rss_markdown)


def render_with_groq(
    data: dict[str, Any],
    api_key: str,
    model: str,
    force_all: bool,
    debug: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    rendered_data = copy.deepcopy(data)
    accepted_records: list[dict[str, Any]] = []
    stats = {"requested": 0, "accepted": 0, "fallback": 0}
    items = rendered_data.get("items", [])
    if not isinstance(items, list):
        return rendered_data, accepted_records, stats
    if not api_key:
        safe_log("groq: GROQ_API_KEY is not set; using fallback renderer for all items.")
        return rendered_data, accepted_records, stats

    requested = 0
    accepted = 0
    failed = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        reason = groq_exclusion_reason(item)
        if reason:
            if debug:
                safe_log(f"groq-debug: item={index + 1} skipped {reason}")
            continue
        if not force_all and not item_needs_groq(item):
            continue
        if is_enforcement_or_misuse_item(item):
            if debug:
                safe_log(f"groq-debug: item={index + 1} skipped enforcement_misuse")
            continue

        requested += 1
        try:
            original_summary = copy.deepcopy(item.get("selected_summary", {}))
            improved_summary = request_groq_summary(item, api_key, model, debug, index)
            if force_all:
                gate_reason = force_all_gate_reason(item, improved_summary)
                if gate_reason:
                    raise ValueError(f"force_all accepted gate: {gate_reason}")
                if debug:
                    safe_log(f"groq-debug: item={index + 1} force_all_gate passed")
            item["selected_summary"] = improved_summary
            accepted_records.append(
                {
                    "index": index + 1,
                    "category": item.get("category", ""),
                    "source": item.get("source", ""),
                    "published_date": item.get("published_date", ""),
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "original_summary": original_summary,
                    "improved_summary": improved_summary,
                }
            )
            accepted += 1
        except urllib.error.HTTPError as error:
            failed += 1
            safe_log(f"groq: item {index + 1} fallback (HTTP {error.code}).")
        except ValueError as error:
            failed += 1
            reason = str(error) or "validation failed"
            safe_log(f"groq: item {index + 1} fallback (ValueError: {reason}).")
            if debug:
                debug_groq_payload(index, item, reason=reason)
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError) as error:
            failed += 1
            safe_log(f"groq: item {index + 1} fallback ({error.__class__.__name__}).")
    safe_log(f"groq: requested={requested} accepted={accepted} fallback={failed}")
    stats = {"requested": requested, "accepted": accepted, "fallback": failed}
    return rendered_data, accepted_records, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read selected Malaysia news items JSON from this path.")
    parser.add_argument("--output", help="Write rendered Markdown to this path. Defaults to stdout.")
    parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or llama-3.3-70b-versatile.")
    parser.add_argument("--force-all", action="store_true", help="Send all items to Groq for local comparison.")
    parser.add_argument("--debug-groq", action="store_true", help="Write short Groq validation diagnostics to stderr.")
    parser.add_argument("--improved-items-output", help="Write accepted Groq summary improvements to this JSON path.")
    render_mode = parser.add_mutually_exclusive_group()
    render_mode.add_argument("--accepted-only-markdown", action="store_true", help="Render only Groq-accepted items in Markdown output.")
    render_mode.add_argument(
        "--merge-accepted-with-rss-markdown",
        action="store_true",
        help="Merge Groq-accepted item blocks into an existing RSS-rendered Markdown file.",
    )
    parser.add_argument("--rss-markdown-input", help="Read original RSS-rendered Markdown for merge mode.")
    args = parser.parse_args()
    if args.merge_accepted_with_rss_markdown and not args.rss_markdown_input:
        parser.error("--merge-accepted-with-rss-markdown requires --rss-markdown-input")

    resolved_json_input = resolve_json_input(args.json_input)
    safe_log(f"groq: reading JSON {resolved_json_input}")
    data = fallback_renderer.load_json(str(resolved_json_input))
    model = args.model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    api_key = os.environ.get("GROQ_API_KEY", "")
    rendered_data, accepted_records, stats = render_with_groq(data, api_key, model, args.force_all, args.debug_groq)
    if args.improved_items_output:
        payload = build_improved_items_payload(accepted_records, model, stats, datetime.now().astimezone())
        write_json(args.improved_items_output, payload)
    if args.accepted_only_markdown:
        if accepted_records:
            markdown = fallback_renderer.render(accepted_only_render_data(rendered_data, accepted_records))
        else:
            markdown = accepted_only_empty_markdown(model, stats)
    elif args.merge_accepted_with_rss_markdown:
        rss_markdown = Path(args.rss_markdown_input).read_text(encoding="utf-8")
        markdown = merge_accepted_with_rss_markdown(rss_markdown, accepted_records)
    else:
        markdown = fallback_renderer.render(rendered_data)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if args.merge_accepted_with_rss_markdown:
            output_path.write_text(markdown, encoding="utf-8")
        else:
            output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        if args.merge_accepted_with_rss_markdown:
            sys.stdout.write(markdown)
        else:
            sys.stdout.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
