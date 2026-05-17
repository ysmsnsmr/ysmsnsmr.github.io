#!/usr/bin/env python3
import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_malaysia_news_from_json as fallback_renderer


DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_RESPONSE_CHARS = 4000
TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = """あなたはマレーシア在住者向けニュースダッシュボードの日本語編集者です。
入力はRSSのtitle、description、既存summaryだけです。
記事本文は読んでいません。
RSSにない事実を追加しないでください。
カテゴリ、出典、URL、日付は変更しないでください。
英語またはマレー語の文を、自然で短い日本語に整えてください。
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


def request_groq_summary(item: dict[str, Any], api_key: str, model: str) -> dict[str, Any]:
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
    return validate_groq_summary(json.loads(content))


def validate_groq_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Groq summary is not an object")
    conclusion = clean_text(value.get("conclusion"))
    what_happened = summary_lines(value.get("what_happened"))
    life_impact = clean_text(value.get("life_impact"))
    next_action = clean_text(value.get("next_action"))
    if not conclusion:
        raise ValueError("Groq summary conclusion is empty")
    if not isinstance(value.get("what_happened"), list):
        raise ValueError("Groq summary what_happened is not a list")
    if not what_happened:
        raise ValueError("Groq summary what_happened is empty")
    if not life_impact:
        raise ValueError("Groq summary life_impact is empty")
    return {
        "conclusion": conclusion,
        "what_happened": what_happened[:2],
        "life_impact": life_impact,
        "next_action": next_action,
    }


def safe_log(message: str) -> None:
    print(message, file=sys.stderr)


def render_with_groq(data: dict[str, Any], api_key: str, model: str, force_all: bool) -> dict[str, Any]:
    rendered_data = copy.deepcopy(data)
    items = rendered_data.get("items", [])
    if not isinstance(items, list):
        return rendered_data
    if not api_key:
        safe_log("groq: GROQ_API_KEY is not set; using fallback renderer for all items.")
        return rendered_data

    requested = 0
    accepted = 0
    failed = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if not force_all and not item_needs_groq(item):
            continue
        requested += 1
        try:
            item["selected_summary"] = request_groq_summary(item, api_key, model)
            accepted += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            failed += 1
            safe_log(f"groq: item {index + 1} fallback ({error.__class__.__name__}).")
    safe_log(f"groq: requested={requested} accepted={accepted} fallback={failed}")
    return rendered_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True, help="Read selected Malaysia news items JSON from this path.")
    parser.add_argument("--output", help="Write rendered Markdown to this path. Defaults to stdout.")
    parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or llama-3.3-70b-versatile.")
    parser.add_argument("--force-all", action="store_true", help="Send all items to Groq for local comparison.")
    args = parser.parse_args()

    data = fallback_renderer.load_json(args.json_input)
    model = args.model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    api_key = os.environ.get("GROQ_API_KEY", "")
    rendered_data = render_with_groq(data, api_key, model, args.force_all)
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
