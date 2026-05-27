#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "phase2d.groq_rss_vs_body_context.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TEMPERATURE = 0.2
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
MAX_RESPONSE_CHARS = 5000
RAW_PREVIEW_CHARS = 500
TIMEOUT_SECONDS = 30
ARTICLE_BODY = "article_body"
FORBIDDEN_PATTERNS = [
    "gsk_",
    "GROQ_API_KEY",
    "Authorization",
    "Bearer",
    "api_key",
]

SYSTEM_PROMPT = """あなたはマレーシア在住者向けニュースダッシュボードの日本語編集者です。
入力はRSS summaryまたは記事本文excerptを含む短いニュース文脈だけです。
入力にない事実、対象者、影響、次アクションを追加しないでください。
カテゴリ、出典、URL、日付は変更しないでください。
英語またはマレー語の文を、自然で短い日本語に整えてください。
dateline（例: KUALA LUMPUR, May 17 —）は出力しないでください。
conclusionは30〜45字程度の自然な日本語にしてください。
what_happenedは入力にある事実だけで、最大2件にしてください。
life_impactは入力から言える範囲に留め、分からない場合は控えめな背景情報として表現してください。
出力はJSON objectのみです。
必ず次のキーだけを返してください: conclusion, what_happened, life_impact, next_action。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Groq summaries for RSS-only context vs article-body excerpt context."
    )
    parser.add_argument("--json-input", required=True, help="Path to Phase 2D.2 comparison JSON.")
    parser.add_argument(
        "--output",
        default="/tmp/groq_rss_vs_body_comparison.json",
        help="Path to write Groq A/B comparison JSON.",
    )
    parser.add_argument(
        "--memo-output",
        default="/tmp/groq_rss_vs_body_comparison_memo.md",
        help="Path to write Markdown observation memo.",
    )
    parser.add_argument("--limit", type=int, default=3, help="Maximum article_body items to compare.")
    parser.add_argument("--model", help="Groq model. Defaults to GROQ_MODEL or llama-3.3-70b-versatile.")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Groq temperature.")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + "\n", encoding="utf-8")


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def redact(text: str) -> str:
    redacted = text
    for pattern in FORBIDDEN_PATTERNS:
        redacted = redacted.replace(pattern, "[redacted]")
    return redacted


def safe_text(value: Any, *, empty: str = "") -> str:
    return redact(clean_text(value)) or empty


def block_text(value: Any, *, empty: str = "（空）") -> str:
    return redact(text_value(value).strip()) or empty


def strip_json_code_fence(content: str) -> str:
    text = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def summary_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)][:2]
    if isinstance(value, str):
        return [clean_text(value)] if clean_text(value) else []
    return []


def validate_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("summary is not object")
    conclusion = clean_text(value.get("conclusion"))
    what_happened = summary_lines(value.get("what_happened"))
    life_impact = clean_text(value.get("life_impact"))
    next_action = clean_text(value.get("next_action"))
    if not conclusion:
        raise ValueError("missing conclusion")
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


def parse_groq_content(content: str) -> dict[str, Any]:
    cleaned = strip_json_code_fence(content)
    return validate_summary(json.loads(cleaned))


def raw_preview(text: str) -> str:
    return redact(re.sub(r"\s+", " ", text).strip()[:RAW_PREVIEW_CHARS])


def skipped_result(status: str, error: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "summary": {},
        "error": error,
        "raw_text_preview": "",
    }


def groq_user_payload(item: dict[str, Any], variant: str, context: str) -> dict[str, Any]:
    return {
        "variant": variant,
        "title": item.get("title", ""),
        "source": item.get("source", ""),
        "feed": item.get("feed", ""),
        "published": item.get("published", ""),
        "context": context,
        "expected_json": {
            "conclusion": "",
            "what_happened": [],
            "life_impact": "",
            "next_action": "",
        },
    }


def request_groq_summary(
    item: dict[str, Any],
    variant: str,
    context: str,
    api_key: str,
    model: str,
    temperature: float,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(groq_user_payload(item, variant, context), ensure_ascii=False)},
        ],
        "temperature": temperature,
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
        return {
            "status": "error",
            "summary": {},
            "error": "response_too_long",
            "raw_text_preview": "",
        }
    try:
        payload = json.loads(response_body)
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty response content")
        return {
            "status": "ok",
            "summary": parse_groq_content(content),
            "error": "",
            "raw_text_preview": "",
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "parse_error",
            "summary": {},
            "error": f"JSONDecodeError: {exc.msg}",
            "raw_text_preview": raw_preview(response_body),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        preview = ""
        try:
            parsed = json.loads(response_body)
            content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
            preview = raw_preview(text_value(content))
        except Exception:
            preview = raw_preview(response_body)
        return {
            "status": "error",
            "summary": {},
            "error": f"{exc.__class__.__name__}: {exc}",
            "raw_text_preview": preview,
        }


def run_variant(
    item: dict[str, Any],
    variant: str,
    context: str,
    api_key: str,
    model: str,
    temperature: float,
) -> dict[str, Any]:
    if not api_key:
        return skipped_result("skipped_no_key")
    try:
        return request_groq_summary(item, variant, context, api_key, model, temperature)
    except urllib.error.HTTPError as exc:
        return skipped_result("http_error", f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        return skipped_result("request_error", exc.__class__.__name__)


def comparison_items(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("Input JSON must contain an items array.")
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if item.get("content_source") != ARTICLE_BODY:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def build_result_item(
    item: dict[str, Any],
    api_key: str,
    model: str,
    temperature: float,
) -> dict[str, Any]:
    rss_only = text_value(item.get("rss_only"))
    with_body_excerpt = text_value(item.get("with_body_excerpt"))
    return {
        "index": item.get("index", ""),
        "source": item.get("source", ""),
        "feed": item.get("feed", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published": item.get("published", ""),
        "rss_only_result": run_variant(item, "rss_only", rss_only, api_key, model, temperature),
        "with_body_excerpt_result": run_variant(
            item,
            "with_body_excerpt",
            with_body_excerpt,
            api_key,
            model,
            temperature,
        ),
    }


def build_payload(
    source_data: dict[str, Any],
    source_json: str,
    model: str,
    temperature: float,
    limit: int,
    api_key: str,
) -> dict[str, Any]:
    targets = comparison_items(source_data, limit)
    items = [build_result_item(item, api_key, model, temperature) for item in targets]
    ok_results = sum(
        1
        for item in items
        for key in ("rss_only_result", "with_body_excerpt_result")
        if item.get(key, {}).get("status") == "ok"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "model": model,
        "temperature": temperature,
        "source_json": source_json,
        "counts": {
            "available_article_body_items": sum(
                1
                for item in source_data.get("items", [])
                if isinstance(item, dict) and item.get("content_source") == ARTICLE_BODY
            ),
            "compared_items": len(items),
            "requested_results": len(items) * 2 if api_key else 0,
            "ok_results": ok_results,
            "skipped_no_key": sum(
                1
                for item in items
                for key in ("rss_only_result", "with_body_excerpt_result")
                if item.get(key, {}).get("status") == "skipped_no_key"
            ),
        },
        "items": items,
    }


def render_summary_result(label: str, result: Any) -> list[str]:
    if not isinstance(result, dict):
        result = {}
    summary = result.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    lines = [
        f"### {label}",
        "",
        f"- status：{safe_text(result.get('status'))}",
    ]
    if result.get("error"):
        lines.append(f"- error：{safe_text(result.get('error'))}")
    if result.get("raw_text_preview"):
        lines.append(f"- raw_text_preview：{safe_text(result.get('raw_text_preview'))}")
    if summary:
        lines.append(f"- 結論：{safe_text(summary.get('conclusion'))}")
        what_happened = summary.get("what_happened")
        if isinstance(what_happened, list):
            for line in what_happened[:2]:
                lines.append(f"- 何が起きた：{safe_text(line)}")
        lines.append(f"- 生活への影響：{safe_text(summary.get('life_impact'))}")
        next_action = safe_text(summary.get("next_action"))
        lines.append(f"- 次アクション：{next_action or 'なし'}")
    lines.append("")
    return lines


def render_item(item: dict[str, Any]) -> list[str]:
    lines = [
        f"## Item {safe_text(item.get('index'))}",
        "",
        f"- source：{safe_text(item.get('source'))}",
        f"- feed：{safe_text(item.get('feed'))}",
        f"- published：{safe_text(item.get('published'))}",
        f"- title：{safe_text(item.get('title'))}",
        f"- URL：{safe_text(item.get('url'))}",
        "",
    ]
    lines.extend(render_summary_result("A: RSS summaryのみ", item.get("rss_only_result")))
    lines.extend(render_summary_result("B: 本文excerptあり", item.get("with_body_excerpt_result")))
    lines.extend(
        [
            "### 観察メモ",
            "",
            "- OK: ",
            "- 要注意: ",
            "- NG: ",
            "- 次回確認: ",
            "",
            "見る観点: 具体性、余計な詳細、生活影響の自然さ、RSSだけで十分か。",
            "",
        ]
    )
    return lines


def render_memo(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    raw_items = payload.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    lines = [
        "# Groq RSS summaryのみ vs 本文excerptあり A/B観察メモ",
        "",
        f"- generated_at：{safe_text(payload.get('generated_at'))}",
        f"- model：{safe_text(payload.get('model'))}",
        f"- temperature：{safe_text(payload.get('temperature'))}",
        f"- source_json：{safe_text(payload.get('source_json'))}",
        f"- available_article_body_items：{safe_text(counts.get('available_article_body_items', 0))}",
        f"- compared_items：{safe_text(counts.get('compared_items', 0))}",
        f"- requested_results：{safe_text(counts.get('requested_results', 0))}",
        f"- ok_results：{safe_text(counts.get('ok_results', 0))}",
        f"- skipped_no_key：{safe_text(counts.get('skipped_no_key', 0))}",
        "",
    ]
    if not items:
        lines.append("比較対象itemはありません。")
        return "\n".join(lines).strip()
    for item in items:
        lines.extend(render_item(item))
    return "\n".join(lines).strip()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be 1 or greater.")

    source_data = load_json(args.json_input)
    model = args.model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    api_key = os.environ.get("GROQ_API_KEY", "")
    payload = build_payload(source_data, args.json_input, model, args.temperature, args.limit, api_key)
    write_json(args.output, payload)
    write_text(args.memo_output, render_memo(payload))
    print(f"written: {args.output}")
    print(f"written: {args.memo_output}")
    print(
        "groq comparison: "
        f"compared_items={payload['counts']['compared_items']}, "
        f"requested_results={payload['counts']['requested_results']}, "
        f"ok_results={payload['counts']['ok_results']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
