#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CATEGORIES = ["【速報】", "【生活インパクト】", "【知っておくと得】"]
TOPIC_ORDER = [
    "flood",
    "storm_weather",
    "heat_weather",
    "oil_spill",
    "road_closure",
    "public_transport",
    "cost_of_living",
    "health",
    "currency",
    "market",
]

TOPIC_TEXT = {
    "storm_weather": {
        "conclusion": "雷雨や大雨への注意が必要です。",
        "what_happened": ["RSSでは、雷雨・大雨などの天候リスクが伝えられています。"],
        "life_impact": "外出や移動は、急な雨や強風による遅れに注意が必要です。",
        "next_action": "外出前に最新の気象情報を確認してください。",
    },
    "heat_weather": {
        "conclusion": "暑さによる健康リスクに注意が必要です。",
        "what_happened": ["RSSでは、暑さや熱中症リスクに関する情報が伝えられています。"],
        "life_impact": "屋外活動や通勤・通学では、体調管理に注意が必要です。",
        "next_action": "水分補給を意識し、体調不良時は無理な外出を避けてください。",
    },
    "flood": {
        "conclusion": "洪水や冠水への注意が必要です。",
        "what_happened": ["RSSでは、洪水・冠水に関する注意情報が伝えられています。"],
        "life_impact": "低地や冠水しやすい道路では、移動に時間がかかる可能性があります。",
        "next_action": "移動前に自治体や交通情報を確認してください。",
    },
    "oil_spill": {
        "conclusion": "油流出による道路影響に注意が必要です。",
        "what_happened": ["RSSでは、タンクローリー事故などによる油流出が伝えられています。"],
        "life_impact": "対象道路では滑りやすさや渋滞、迂回が発生する可能性があります。",
        "next_action": "周辺を通る場合は交通情報を確認してください。",
    },
    "road_closure": {
        "conclusion": "道路閉鎖や交通規制に注意が必要です。",
        "what_happened": ["RSSでは、道路閉鎖や交通規制に関する情報が伝えられています。"],
        "life_impact": "対象エリアを通る移動では、迂回や遅延を見込む必要があります。",
        "next_action": "出発前にルートと所要時間を確認してください。",
    },
    "public_transport": {
        "conclusion": "公共交通や移動計画に影響する可能性があります。",
        "what_happened": ["RSSでは、公共交通や移動需要に関する情報が伝えられています。"],
        "life_impact": "通勤・通学・帰省の移動時間に影響する可能性があります。",
        "next_action": "利用前に運行情報と混雑状況を確認してください。",
    },
    "cost_of_living": {
        "conclusion": "生活費や日用品価格に関わる動きです。",
        "what_happened": ["RSSでは、生活費支援や日用品価格に関する情報が伝えられています。"],
        "life_impact": "家計や買い物先の選択に関わる可能性があります。",
        "next_action": "",
    },
    "health": {
        "conclusion": "健康や公衆衛生に関わる注意情報です。",
        "what_happened": ["RSSでは、健康リスクや医療に関する情報が伝えられています。"],
        "life_impact": "体調管理や医療機関の利用判断に関わる可能性があります。",
        "next_action": "症状や不安がある場合は、公式情報や医療機関の案内を確認してください。",
    },
    "currency": {
        "conclusion": "為替動向に関するニュースです。",
        "what_happened": ["RSSでは、リンギット相場の動きが伝えられています。"],
        "life_impact": "海外送金、両替、輸入品価格などの判断材料になります。",
        "next_action": "",
    },
    "market": {
        "conclusion": "市場動向に関するニュースです。",
        "what_happened": ["RSSでは、株式市場や金融市場の動きが伝えられています。"],
        "life_impact": "投資環境や景気感を把握する材料になります。",
        "next_action": "",
    },
}
PUBLIC_TRANSPORT_ENTITY_PHRASES = [
    "rapid kl",
    "mrt",
    "lrt",
    "ktmb",
    "public transport",
    "train",
    "rail",
    "bus",
]
PUBLIC_TRANSPORT_SERVICE_CONTEXT_PHRASES = [
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


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def summary_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [line for line in (text_value(item).strip() for item in value) if line][:2]
    if isinstance(value, str):
        return [line for line in value.splitlines() if line.strip()][:2]
    return []


def clean_display_text(value: Any) -> str:
    text = text_value(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalized_lines(value: Any) -> list[str]:
    return [clean_display_text(line) for line in summary_lines(value) if clean_display_text(line)]


def normalized_text_blob(item: dict[str, Any]) -> str:
    parts = [
        text_value(item.get("title")),
        text_value(item.get("description")),
    ]
    summary = item.get("selected_summary")
    if isinstance(summary, dict):
        parts.extend(
            [
                text_value(summary.get("conclusion")),
                text_value(summary.get("life_impact")),
                text_value(summary.get("next_action")),
                " ".join(summary_lines(summary.get("what_happened"))),
            ]
        )
    return re.sub(r"\s+", " ", " ".join(parts)).strip().lower()


def has_phrase(text: str, phrase: str) -> bool:
    phrase = re.sub(r"\s+", " ", phrase.strip().lower())
    if not phrase:
        return False
    if re.search(r"[a-z0-9]", phrase):
        pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return phrase in text


def has_any_phrase(text: str, phrases: list[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def item_tokens(item: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    raw_tags = item.get("tags", [])
    if isinstance(raw_tags, list):
        tokens.update(clean_display_text(tag).lower() for tag in raw_tags if clean_display_text(tag))
    raw_flags = item.get("flags", {})
    if isinstance(raw_flags, dict):
        tokens.update(clean_display_text(key).lower() for key, value in raw_flags.items() if value and clean_display_text(key))
    return tokens


def has_topic_token(tokens: set[str], phrases: set[str]) -> bool:
    return bool(tokens & phrases)


def looks_english_heavy(text: str) -> bool:
    if not text:
        return True
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    japanese_chars = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    if japanese_chars == 0 and ascii_letters >= 12:
        return True
    return ascii_letters >= 24 and ascii_letters > japanese_chars * 2


def looks_generic(text: str) -> bool:
    generic_phrases = [
        "背景ニュースとして",
        "把握しておく価値があります",
        "rssでは",
        "rssの情報では",
    ]
    return has_any_phrase(text.lower(), generic_phrases)


def should_replace_with_topic_text(text: str) -> bool:
    return not text or looks_english_heavy(text) or looks_generic(text)


def should_replace_lines_with_topic_text(lines: list[str]) -> bool:
    if not lines:
        return True
    joined = " ".join(lines)
    if not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", joined) and re.search(r"[A-Za-z]", joined):
        return True
    return all(should_replace_with_topic_text(line) for line in lines)


def is_storm_weather_topic(text: str, tokens: set[str]) -> bool:
    return (
        has_topic_token(tokens, {"storm_weather", "weather_storm", "thunderstorm", "heavy_rain"})
        or has_any_phrase(text, ["thunderstorm", "heavy rain", "ribut petir", "hujan lebat", "amaran ribut", "amaran hujan"])
    )


def is_heat_weather_topic(text: str, tokens: set[str]) -> bool:
    return (
        has_topic_token(tokens, {"heat_weather", "heat", "is_heat"})
        or has_any_phrase(text, ["hot weather", "cuaca panas", "tahap 1", "heatstroke", "heat stroke", "strok haba", "heat-related illness", "熱中症"])
    )


def is_maritime_context(text: str) -> bool:
    return has_any_phrase(text, ["selat hormuz", "strait", "kapal", "vessel", "shipping lane", "laluan kapal", "maritime"])


def is_road_closure_topic(text: str, tokens: set[str]) -> bool:
    if is_maritime_context(text):
        return False
    road_context = has_topic_token(tokens, {"road_closure", "road_issue", "is_road_issue"}) or has_any_phrase(
        text,
        ["road", "jalan", "lane", "traffic"],
    )
    closure_context = has_any_phrase(
        text,
        ["closure", "closed", "tutup", "ditutup", "sesak", "congestion", "road closure", "jalan ditutup", "traffic congestion"],
    )
    return road_context and closure_context


def is_oil_spill_topic(text: str, tokens: set[str]) -> bool:
    if has_any_phrase(text, ["sawit", "oil palm"]) and not has_any_phrase(text, ["spill", "tumpah", "tanker", "accident"]):
        return False
    spill_context = has_topic_token(tokens, {"oil_spill"}) or has_any_phrase(text, ["spill", "tumpah"])
    incident_context = has_any_phrase(text, ["accident", "tanker", "lorry", "truck", "overturned"])
    road_context = has_any_phrase(text, ["road", "jalan", "klang"])
    return spill_context and incident_context and road_context


def is_public_transport_crime_context(text: str) -> bool:
    return has_any_phrase(text, ["molester", "harassment", "crime", "jail", "caning", "sexual assault", "assault"])


def is_public_transport_service_topic(text: str, tokens: set[str]) -> bool:
    if is_public_transport_crime_context(text):
        return False
    public_transport_context = (
        has_topic_token(tokens, {"public_transport", "is_public_transport"})
        or has_any_phrase(text, PUBLIC_TRANSPORT_ENTITY_PHRASES)
    )
    service_context = has_any_phrase(text, PUBLIC_TRANSPORT_SERVICE_CONTEXT_PHRASES)
    return public_transport_context and service_context


def detect_topic(item: dict[str, Any]) -> str:
    tokens = item_tokens(item)
    text = normalized_text_blob(item)
    checks = {
        "flood": (
            {"flood", "flood_impact", "is_flood_impact"} & tokens
            or has_any_phrase(text, ["flash flood", "flash floods", "flood hotline", "banjir", "冠水", "洪水"])
        ),
        "storm_weather": is_storm_weather_topic(text, tokens),
        "heat_weather": is_heat_weather_topic(text, tokens),
        "oil_spill": is_oil_spill_topic(text, tokens),
        "road_closure": is_road_closure_topic(text, tokens),
        "public_transport": is_public_transport_service_topic(text, tokens),
        "cost_of_living": (
            {"cost_of_living", "prices", "social_support", "aid", "subsidy", "is_cost_of_living"} & tokens
            or has_any_phrase(text, ["jualan rahmah", "kos sara hidup", "cost of living", "barang keperluan", "harga lebih rendah", "jualan murah", "日用品", "生活費"])
        ),
        "health": (
            {"health", "public_health", "healthcare", "is_health"} & tokens
            or has_any_phrase(text, ["moh", "health ministry", "public health", "heat-related illness", "strok haba", "感染症", "医療"])
        ),
        "currency": (
            {"currency", "is_currency"} & tokens
            or has_any_phrase(text, ["ringgit", "rm3", "foreign exchange", "為替"])
        ),
        "market": (
            {"market", "is_market"} & tokens
            or has_any_phrase(text, ["bursa", "stock market", "株式市場", "市場"])
        ),
    }
    for topic in TOPIC_ORDER:
        if checks[topic]:
            return topic
    return ""


def normalize_selected_summary(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("selected_summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "conclusion": clean_display_text(summary.get("conclusion")),
        "what_happened": normalized_lines(summary.get("what_happened")),
        "life_impact": clean_display_text(summary.get("life_impact")),
        "next_action": clean_display_text(summary.get("next_action")),
    }


def build_display_summary(item: dict[str, Any]) -> dict[str, Any]:
    display = normalize_selected_summary(item)
    topic = detect_topic(item)
    if topic:
        topic_text = TOPIC_TEXT[topic]
        if should_replace_with_topic_text(display["conclusion"]):
            display["conclusion"] = topic_text["conclusion"]
        if should_replace_lines_with_topic_text(display["what_happened"]):
            display["what_happened"] = topic_text["what_happened"]
        if should_replace_with_topic_text(display["life_impact"]):
            display["life_impact"] = topic_text["life_impact"]
        if not display["next_action"] and not item.get("_suppress_topic_next_action"):
            display["next_action"] = topic_text["next_action"]
    display["what_happened"] = display["what_happened"][:2]
    return display


def render_item(item: dict[str, Any]) -> list[str]:
    summary = build_display_summary(item)
    lines: list[str] = []
    conclusion = text_value(summary.get("conclusion")).strip()
    life_impact = text_value(summary.get("life_impact")).strip()
    next_action = text_value(summary.get("next_action")).strip()
    source = text_value(item.get("source")).strip()
    published_date = text_value(item.get("published_date")).strip()
    link = text_value(item.get("link")).strip()

    lines.append(f"- 結論：{conclusion}")
    for line in summary_lines(summary.get("what_happened")):
        lines.append(f"- 何が起きた：{line}")
    lines.append(f"- 生活への影響：{life_impact}")
    if next_action:
        lines.append(f"- 次アクション：{next_action}")
    lines.append(f"- 出典：{source}（{published_date}）")
    lines.append(f"- 出典元URL：{link}")
    lines.append("")
    return lines


def selected_items_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    return [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []


def semantic_duplicate_bucket(item: dict[str, Any]) -> str:
    text = normalized_text_blob(item)
    if has_any_phrase(text, ["mykad", "kad pengenalan", "national registration identity card"]):
        return "MyKad BM/English"
    if has_phrase(text, "dbkl") and has_any_phrase(text, ["bus stop", "hentian bas", "bas stop"]):
        return "DBKL bus stop BM/English"
    if has_phrase(text, "ringgit"):
        return "Ringgit multiple items"
    if has_any_phrase(text, ["ron95", "budi95", "budi 95"]):
        return "RON95/BUDI95 multiple items"
    return ""


def print_diagnostics(data: dict[str, Any]) -> None:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in selected_items_from_data(data):
        bucket = semantic_duplicate_bucket(item)
        if bucket:
            buckets.setdefault(bucket, []).append(item)

    duplicate_buckets = {name: items for name, items in buckets.items() if len(items) > 1}
    if not duplicate_buckets:
        print("diagnostics: semantic_duplicate_candidates=0", file=sys.stderr)
        return

    print("diagnostics: semantic_duplicate_candidates:", file=sys.stderr)
    for name, items in duplicate_buckets.items():
        print(f"- {name}: {len(items)} items", file=sys.stderr)
        for item in items:
            title = clean_display_text(item.get("title")) or clean_display_text(item.get("link"))
            source = clean_display_text(item.get("source"))
            published_date = clean_display_text(item.get("published_date"))
            print(f"  - {source} {published_date}: {title}", file=sys.stderr)


def render(data: dict[str, Any]) -> str:
    items = selected_items_from_data(data)
    counts = data.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    failed_sources = data.get("failed_sources", [])
    if not isinstance(failed_sources, list):
        failed_sources = []

    lines: list[str] = []
    for category in CATEGORIES:
        lines.append(category)
        lines.append("")
        for item in items:
            if item.get("category") == category:
                lines.extend(render_item(item))

    processed = counts.get("processed", 0)
    selected = counts.get("selected", len(items))
    lines.append(f"処理対象件数：{processed}件")
    lines.append(f"要約対象件数：{selected}件")
    failed_text = ", ".join(text_value(source) for source in failed_sources if text_value(source)) or "なし"
    lines.append(f"失敗したソース一覧：{failed_text}")
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read selected Malaysia news items JSON from this path.")
    parser.add_argument("--output", help="Write rendered Markdown to this path. Defaults to stdout.")
    parser.add_argument("--diagnostics", action="store_true", help="Write semantic duplicate candidates to stderr.")
    args = parser.parse_args()

    data = load_json(args.json_input)
    if args.diagnostics:
        print_diagnostics(data)

    markdown = render(data)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
