#!/usr/bin/env python3
import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from malaysia_groq_body_focus import life_impact_matches_body_focus
from malaysia_groq_common import (
    clean_text,
    collect_item_text,
    contains_any,
    has_any_text,
    item_needs_groq,
    item_source_text,
    normalize_topic,
    summary_lines,
    summary_text,
)
from malaysia_groq_force_all_policy import (
    force_all_gate_reason,
    force_all_pre_request_skip_reason,
    force_all_request_cap,
    force_all_request_priority,
    groq_exclusion_reason,
    ordered_force_all_entries,
)
from malaysia_groq_markdown_merge import merge_accepted_with_rss_markdown
from malaysia_groq_term_normalization import normalize_malaysia_terms
import render_malaysia_news_from_json as fallback_renderer


DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
MAX_RESPONSE_CHARS = 4000
TIMEOUT_SECONDS = 30
MAX_429_RETRY_AFTER_SECONDS = 5
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


def normalize_summary(value: Any) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    return {
        "conclusion": clean_text(summary.get("conclusion")),
        "what_happened": summary_lines(summary.get("what_happened")),
        "life_impact": clean_text(summary.get("life_impact")),
        "next_action": clean_text(summary.get("next_action")),
    }


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


def retry_after_seconds(error: urllib.error.HTTPError) -> int | None:
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if not retry_after:
        return None
    retry_after = retry_after.strip()
    if not retry_after.isdigit():
        return None
    seconds = int(retry_after)
    if 0 <= seconds <= MAX_429_RETRY_AFTER_SECONDS:
        return seconds
    return None


def request_groq_summary_with_retry(
    item: dict[str, Any],
    api_key: str,
    model: str,
    debug: bool = False,
    index: int = 0,
) -> dict[str, Any]:
    try:
        return request_groq_summary(item, api_key, model, debug, index)
    except urllib.error.HTTPError as error:
        retry_after = retry_after_seconds(error)
        if error.code != 429 or retry_after is None:
            raise
        safe_log(f"groq: item {index + 1} retrying after HTTP 429 Retry-After={retry_after}s.")
        time.sleep(retry_after)
        return request_groq_summary(item, api_key, model, debug, index)


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


def diagnostic_focus_values(item: dict[str, Any]) -> list[str]:
    focus = item.get("body_evidence_focus")
    if not isinstance(focus, list):
        return []
    return [clean_text(value) for value in focus if clean_text(value)]


def build_decision_record(
    index: int,
    item: dict[str, Any],
    force_all: bool,
    needs_groq: bool | None = None,
) -> dict[str, Any]:
    if needs_groq is None:
        needs_groq = item_needs_groq(item)
    return {
        "index": index + 1,
        "link": clean_text(item.get("link")),
        "source": clean_text(item.get("source")),
        "category": clean_text(item.get("category")),
        "title": clean_text(item.get("title")),
        "body_excerpt_policy": clean_text(item.get("body_excerpt_policy")),
        "body_evidence_focus": diagnostic_focus_values(item),
        "item_needs_groq": needs_groq,
        "force_all_priority": force_all_request_priority(item) if force_all else None,
        "decision": "pending",
        "reason": "",
        "requested": False,
        "accepted": False,
    }


def decision_record_counts(decision_records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "records": len(decision_records),
        "requested": sum(1 for record in decision_records if record.get("requested") is True),
        "accepted": sum(1 for record in decision_records if record.get("accepted") is True),
        "fallback": sum(1 for record in decision_records if record.get("decision") == "fallback"),
        "skipped": sum(1 for record in decision_records if record.get("decision") == "skipped"),
    }


def build_improved_items_payload(
    accepted_records: list[dict[str, Any]],
    model: str,
    stats: dict[str, int],
    now: datetime,
    decision_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    if decision_records is not None:
        payload["diagnostics"] = {
            "decision_counts": decision_record_counts(decision_records),
            "decision_records": decision_records,
        }
    return payload


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


def render_with_groq(
    data: dict[str, Any],
    api_key: str,
    model: str,
    force_all: bool,
    debug: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    rendered_data = copy.deepcopy(data)
    accepted_records: list[dict[str, Any]] = []
    decision_records: list[dict[str, Any]] = []
    stats = {"requested": 0, "accepted": 0, "fallback": 0}
    items = rendered_data.get("items", [])
    if not isinstance(items, list):
        return rendered_data, accepted_records, stats, decision_records
    if not api_key:
        safe_log("groq: GROQ_API_KEY is not set; using fallback renderer for all items.")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            record = build_decision_record(index, item, force_all)
            record["decision"] = "skipped"
            record["reason"] = "missing_groq_api_key"
            decision_records.append(record)
        return rendered_data, accepted_records, stats, decision_records

    requested = 0
    accepted = 0
    failed = 0
    entries = ordered_force_all_entries(items) if force_all else [
        (index, item) for index, item in enumerate(items) if isinstance(item, dict)
    ]
    request_cap = force_all_request_cap() if force_all else 0
    if force_all and debug:
        safe_log(f"groq-debug: force_all request cap={request_cap}")
    for index, item in entries:
        if not isinstance(item, dict):
            continue
        needs_groq = item_needs_groq(item)
        decision_record = build_decision_record(index, item, force_all, needs_groq)
        decision_records.append(decision_record)
        reason = groq_exclusion_reason(item)
        if reason:
            decision_record["decision"] = "skipped"
            decision_record["reason"] = f"groq_exclusion:{reason}"
            if debug:
                safe_log(f"groq-debug: item={index + 1} skipped {reason}")
            continue
        if force_all:
            reason = force_all_pre_request_skip_reason(item)
            if reason:
                decision_record["decision"] = "skipped"
                decision_record["reason"] = f"pre_request_skip:{reason}"
                if debug:
                    safe_log(f"groq-debug: item={index + 1} skipped force_all_pre_request {reason}")
                continue
            if requested >= request_cap:
                decision_record["decision"] = "skipped"
                decision_record["reason"] = "request_cap"
                if debug:
                    safe_log(f"groq-debug: item={index + 1} skipped force_all_request_cap")
                continue
        if not force_all and not needs_groq:
            decision_record["decision"] = "skipped"
            decision_record["reason"] = "not_needed"
            continue
        if is_enforcement_or_misuse_item(item):
            decision_record["decision"] = "skipped"
            decision_record["reason"] = "enforcement_misuse"
            if debug:
                safe_log(f"groq-debug: item={index + 1} skipped enforcement_misuse")
            continue

        requested += 1
        decision_record["decision"] = "requested"
        decision_record["requested"] = True
        try:
            original_summary = copy.deepcopy(item.get("selected_summary", {}))
            improved_summary = request_groq_summary_with_retry(item, api_key, model, debug, index)
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
            decision_record["decision"] = "accepted"
            decision_record["accepted"] = True
            accepted += 1
        except urllib.error.HTTPError as error:
            failed += 1
            decision_record["decision"] = "fallback"
            decision_record["reason"] = f"HTTP {error.code}"
            safe_log(f"groq: item {index + 1} fallback (HTTP {error.code}).")
        except ValueError as error:
            failed += 1
            reason = str(error) or "validation failed"
            decision_record["decision"] = "fallback"
            decision_record["reason"] = f"ValueError: {reason}"
            safe_log(f"groq: item {index + 1} fallback (ValueError: {reason}).")
            if debug:
                debug_groq_payload(index, item, reason=reason)
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError) as error:
            failed += 1
            decision_record["decision"] = "fallback"
            decision_record["reason"] = error.__class__.__name__
            safe_log(f"groq: item {index + 1} fallback ({error.__class__.__name__}).")
    safe_log(f"groq: requested={requested} accepted={accepted} fallback={failed}")
    stats = {"requested": requested, "accepted": accepted, "fallback": failed}
    accepted_records.sort(key=lambda record: record.get("index", 0))
    decision_records.sort(key=lambda record: record.get("index", 0))
    return rendered_data, accepted_records, stats, decision_records


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
    rendered_data, accepted_records, stats, decision_records = render_with_groq(
        data,
        api_key,
        model,
        args.force_all,
        args.debug_groq,
    )
    if args.improved_items_output:
        payload = build_improved_items_payload(
            accepted_records,
            model,
            stats,
            datetime.now().astimezone(),
            decision_records,
        )
        write_json(args.improved_items_output, payload)
    if args.accepted_only_markdown:
        if accepted_records:
            markdown = fallback_renderer.render(accepted_only_render_data(rendered_data, accepted_records))
        else:
            markdown = accepted_only_empty_markdown(model, stats)
    elif args.merge_accepted_with_rss_markdown:
        rss_markdown = Path(args.rss_markdown_input).read_text(encoding="utf-8")
        markdown = merge_accepted_with_rss_markdown(rss_markdown, accepted_records, data)
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
