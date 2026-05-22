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

SYSTEM_PROMPT = """あなたはマレーシア在住者向けニュースダッシュボードの日本語編集者です。
入力はRSSのtitle、description、既存summaryだけです。
記事本文は読んでいません。
RSSにない事実を追加しないでください。
カテゴリ、出典、URL、日付は変更しないでください。
英語またはマレー語の文を、自然で短い日本語に整えてください。
dateline（例: KUALA LUMPUR, May 17 — / クアラルンプール、5月17日 -）は出力しないでください。
人名や機関名は必要な場合だけ短く使ってください。
conclusionは30〜45字程度の自然な日本語にしてください。
titleにある主要な具体要素を落とさないでください。
what_happenedはRSS title/descriptionにある事実だけで、最大2文にしてください。
life_impactでは「生活・仕事・家計に関わる背景ニュース」のような汎用文を避けてください。
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
        "背景ニュースとして",
        "把握しておく価値があります",
        "rssでは",
        "rssの情報では",
    ]
    lower_text = text.lower()
    return any(phrase.lower() in lower_text for phrase in generic_phrases)


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
    return {
        "category": item.get("category"),
        "source": item.get("source"),
        "published_date": item.get("published_date"),
        "title": item.get("title"),
        "description": item.get("description"),
        "selected_summary": normalize_summary(item.get("selected_summary")),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "flags": item.get("flags") if isinstance(item.get("flags"), dict) else {},
    }


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

    topic = normalize_topic(fallback_renderer.detect_topic(item))
    reason = reject_life_impact_reason(topic, item, summary["life_impact"])
    if reason:
        raise ValueError(f"life_impact topic mismatch: {reason}")


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
        "response_format": {"type": "json_object"},
    }
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
        requested += 1
        try:
            original_summary = copy.deepcopy(item.get("selected_summary", {}))
            improved_summary = request_groq_summary(item, api_key, model, debug, index)
            item["selected_summary"] = improved_summary
            accepted_records.append(
                {
                    "index": index,
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
    args = parser.parse_args()

    data = fallback_renderer.load_json(args.json_input)
    model = args.model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    api_key = os.environ.get("GROQ_API_KEY", "")
    rendered_data, accepted_records, stats = render_with_groq(data, api_key, model, args.force_all, args.debug_groq)
    if args.improved_items_output:
        payload = build_improved_items_payload(accepted_records, model, stats, datetime.now().astimezone())
        write_json(args.improved_items_output, payload)
    markdown = fallback_renderer.render(rendered_data)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
