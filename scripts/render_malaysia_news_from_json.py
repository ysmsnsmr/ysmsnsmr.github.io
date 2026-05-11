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
    "weather",
    "road_closure",
    "public_transport",
    "cost_of_living",
    "health",
    "currency",
    "market",
]

TOPIC_TEXT = {
    "weather": {
        "conclusion": "天候悪化への注意が必要です。",
        "what_happened": ["RSSでは、雷雨・大雨などの天候リスクが伝えられています。"],
        "life_impact": "外出や移動は、急な雨や強風による遅れに注意が必要です。",
        "next_action": "外出前に最新の気象情報を確認してください。",
    },
    "flood": {
        "conclusion": "洪水や冠水への注意が必要です。",
        "what_happened": ["RSSでは、洪水・冠水に関する注意情報が伝えられています。"],
        "life_impact": "低地や冠水しやすい道路では、移動に時間がかかる可能性があります。",
        "next_action": "移動前に自治体や交通情報を確認してください。",
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


def detect_topic(item: dict[str, Any]) -> str:
    tokens = item_tokens(item)
    text = normalized_text_blob(item)
    checks = {
        "flood": (
            {"flood", "flood_impact", "is_flood_impact"} & tokens
            or has_any_phrase(text, ["flash flood", "flash floods", "flood hotline", "banjir", "冠水", "洪水"])
        ),
        "weather": (
            {"weather", "is_weather", "heat", "is_heat"} & tokens
            or has_any_phrase(text, ["metmalaysia", "thunderstorm", "heavy rain", "ribut petir", "hujan lebat", "heatstroke", "heat stroke", "熱中症"])
        ),
        "road_closure": (
            {"road_closure", "road_issue", "is_road_issue"} & tokens
            or has_any_phrase(text, ["road closed", "road closure", "jalan ditutup", "traffic congestion", "closed from midnight", "道路閉鎖", "交通規制"])
        ),
        "public_transport": (
            {"public_transport", "is_public_transport"} & tokens
            or has_any_phrase(text, ["public transport", "ktmb", "extra trains", "train services", "commuting", "grab group ride"])
        ),
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
        if not display["next_action"]:
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


def render(data: dict[str, Any]) -> str:
    raw_items = data.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
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
    args = parser.parse_args()

    markdown = render(load_json(args.json_input))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
