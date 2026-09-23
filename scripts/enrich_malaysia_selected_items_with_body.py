#!/usr/bin/env python3
import argparse
import copy
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "phase2e.selected_items_enriched.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
USER_AGENT = "Mozilla/5.0 (compatible; ysmsnsmr-malaysia-news/0.1; +https://ysmsnsmr.github.io/news/malaysia/)"
ARTICLE_BODY = "article_body"
RSS_FALLBACK = "rss_fallback"
USE_BODY = "use_body"
RSS_ONLY = "rss_only"
SELECTED_ARTICLE_BODY = "article_body"
SELECTED_RSS_SUMMARY = "rss_summary"
CONTENT_SOURCE_VALUES = {ARTICLE_BODY, RSS_FALLBACK}
POLICY_VALUES = {USE_BODY, RSS_ONLY, RSS_FALLBACK}
SELECTED_CONTEXT_SOURCE_VALUES = {SELECTED_ARTICLE_BODY, SELECTED_RSS_SUMMARY}

BODY_EVIDENCE_FORBIDDEN = [
    "dateline",
    "wire_credit",
    "advertisement",
    "related_links",
    "unsupported_conditions",
]
DATELINE_PREFIX_RE = re.compile(
    r"^(?:KUALA LUMPUR|PUTRAJAYA|MELAKA|GEORGE TOWN|IPOH|ALOR SETAR|JOHOR BARU|KOTA KINABALU|KUCHING),\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2}\s+[—–-]\s*",
    flags=re.IGNORECASE,
)
WIRE_CREDIT_RE = re.compile(r"\s+[—–-]\s*(?:Bernama|Reuters|AFP|Malay Mail)\s*$", flags=re.IGNORECASE)
BODY_NOISE_RE = re.compile(
    r"\b(?:Advertisement|Related Articles|You May Also Like|Read more|Subscribe to our newsletter)\b",
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Malaysia selected_items JSON with article-body excerpts.")
    parser.add_argument("--json-input", required=True, help="Path to selected_items.json.")
    parser.add_argument("--output", required=True, help="Path to write enriched selected_items JSON.")
    parser.add_argument("--timeout-sec", type=float, default=20.0, help="Per-article newspaper3k timeout.")
    parser.add_argument("--excerpt-chars", type=int, default=1200, help="Maximum body excerpt characters.")
    return parser.parse_args()


def load_dependencies() -> tuple[Any, Any]:
    try:
        from newspaper import Article, Config  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: newspaper3k/lxml_html_clean. Install locally with "
            "`python3.12 -m pip install newspaper3k lxml_html_clean`."
        ) from exc
    return Article, Config


def load_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def write_json(path: str, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def excerpt(text: str, max_chars: int) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    if max_chars <= 3:
        return cleaned[:max_chars]
    return cleaned[: max_chars - 3].rstrip() + "..."


def split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def cleanup_body_evidence(text: str, max_chars: int) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    cleaned = DATELINE_PREFIX_RE.sub("", cleaned)
    cleaned = WIRE_CREDIT_RE.sub("", cleaned)
    cleaned = BODY_NOISE_RE.split(cleaned)[0]
    cleaned = WIRE_CREDIT_RE.sub("", cleaned)
    sentences: list[str] = []
    for sentence in split_sentences(cleaned):
        sentence = DATELINE_PREFIX_RE.sub("", sentence).strip()
        sentence = WIRE_CREDIT_RE.sub("", sentence).strip()
        if not sentence or BODY_NOISE_RE.search(sentence):
            continue
        sentences.append(sentence)
        if len(clean_text(" ".join(sentences))) >= max_chars:
            break
    evidence = " ".join(sentences) if sentences else cleaned
    evidence = WIRE_CREDIT_RE.sub("", evidence).strip()
    return excerpt(evidence, max_chars)


def selected_items_payload(data: Any) -> tuple[list[dict[str, Any]], bool]:
    if isinstance(data, dict):
        items = data.get("items", [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError("Object input must contain an items array of objects.")
        return items, False
    if isinstance(data, list):
        if not all(isinstance(item, dict) for item in data):
            raise ValueError("List input must contain objects.")
        return data, True
    raise ValueError("Input JSON root must be an object with items or a list.")


def item_link(item: dict[str, Any]) -> str:
    return clean_text(item.get("link"))


def item_title(item: dict[str, Any]) -> str:
    return clean_text(item.get("title"))


def item_rss_summary(item: dict[str, Any]) -> str:
    return clean_text(item.get("description")) or clean_text(item.get("summary")) or item_title(item)


def is_malaymail_body_candidate(item: dict[str, Any]) -> bool:
    if clean_text(item.get("source")) != "Malay Mail":
        return False
    link = item_link(item)
    if not link:
        return False
    host = urlparse(link).hostname or ""
    return host == "malaymail.com" or host.endswith(".malaymail.com")


def is_astro_awani(item: dict[str, Any]) -> bool:
    return clean_text(item.get("source")) == "Astro Awani"


def classify_body_excerpt_policy(item: dict[str, Any]) -> tuple[str, str]:
    content_source = clean_text(item.get("content_source"))
    if content_source == RSS_FALLBACK:
        return RSS_FALLBACK, "rss_fallback"
    if content_source != ARTICLE_BODY:
        return RSS_FALLBACK, "invalid_content_source"

    if not clean_text(item.get("body_evidence_excerpt")):
        return RSS_ONLY, "empty_body_evidence"
    return USE_BODY, "clean_article_body"


def base_body_fields(error: str = "") -> dict[str, Any]:
    return {
        "content_source": RSS_FALLBACK,
        "body_fetched": False,
        "body_text_length": 0,
        "body_excerpt": "",
        "body_evidence_excerpt": "",
        "body_evidence_focus": [],
        "body_evidence_forbidden": BODY_EVIDENCE_FORBIDDEN,
        "body_error": error,
    }


def apply_body_evidence_fields(item: dict[str, Any], excerpt_chars: int) -> None:
    if item.get("content_source") != ARTICLE_BODY:
        item["body_evidence_excerpt"] = ""
        item["body_evidence_focus"] = []
        item["body_evidence_forbidden"] = BODY_EVIDENCE_FORBIDDEN
        return
    evidence = cleanup_body_evidence(clean_text(item.get("body_excerpt")), excerpt_chars)
    item["body_evidence_excerpt"] = evidence
    item["body_evidence_focus"] = []
    item["body_evidence_forbidden"] = BODY_EVIDENCE_FORBIDDEN


def fetch_article_body(
    item: dict[str, Any],
    Article: Any,
    Config: Any,
    timeout_sec: float,
    excerpt_chars: int,
) -> dict[str, Any]:
    fields = base_body_fields()
    link = item_link(item)
    if not link:
        fields["body_error"] = "missing_link"
        return fields
    try:
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = timeout_sec
        article = Article(link, config=config)
        article.download()
        article.parse()
        text = clean_text(article.text)
        if not text:
            fields["body_error"] = "empty_text"
            return fields
        fields["content_source"] = ARTICLE_BODY
        fields["body_fetched"] = True
        fields["body_text_length"] = len(text)
        fields["body_excerpt"] = excerpt(text, excerpt_chars)
        return fields
    except Exception as exc:
        fields["body_error"] = f"{type(exc).__name__}: {exc}"
        return fields


def enrich_item(
    item: dict[str, Any],
    Article: Any,
    Config: Any,
    timeout_sec: float,
    excerpt_chars: int,
) -> dict[str, Any]:
    output = copy.deepcopy(item)
    try:
        if is_astro_awani(output):
            output.update(base_body_fields("skipped_by_policy"))
        elif is_malaymail_body_candidate(output):
            output.update(fetch_article_body(output, Article, Config, timeout_sec, excerpt_chars))
        else:
            output.update(base_body_fields("skipped_by_policy"))

        apply_body_evidence_fields(output, excerpt_chars)
        policy, reason = classify_body_excerpt_policy(output)
    except Exception as exc:
        output.update(base_body_fields(f"classification_error: {type(exc).__name__}: {exc}"))
        policy, reason = RSS_FALLBACK, "classification_error"

    selected_context_source = SELECTED_ARTICLE_BODY if policy == USE_BODY else SELECTED_RSS_SUMMARY
    output["body_excerpt_policy"] = policy
    output["body_excerpt_used"] = policy == USE_BODY
    output["body_excerpt_reason"] = reason
    output["selected_context_source"] = selected_context_source
    return output


def validate_item(item: dict[str, Any]) -> None:
    content_source = item.get("content_source")
    policy = item.get("body_excerpt_policy")
    selected_context_source = item.get("selected_context_source")
    if content_source not in CONTENT_SOURCE_VALUES:
        raise ValueError(f"Invalid content_source: {content_source!r}")
    if policy not in POLICY_VALUES:
        raise ValueError(f"Invalid body_excerpt_policy: {policy!r}")
    if selected_context_source not in SELECTED_CONTEXT_SOURCE_VALUES:
        raise ValueError(f"Invalid selected_context_source: {selected_context_source!r}")
    if item.get("body_excerpt_used") != (policy == USE_BODY):
        raise ValueError("body_excerpt_used does not match body_excerpt_policy.")
    if selected_context_source != (SELECTED_ARTICLE_BODY if policy == USE_BODY else SELECTED_RSS_SUMMARY):
        raise ValueError("selected_context_source does not match body_excerpt_policy.")
    if not isinstance(item.get("body_evidence_focus"), list):
        raise ValueError("body_evidence_focus must be a list.")
    if not isinstance(item.get("body_evidence_forbidden"), list):
        raise ValueError("body_evidence_forbidden must be a list.")
    if policy == USE_BODY and not clean_text(item.get("body_evidence_excerpt")):
        raise ValueError("body_evidence_excerpt is required when body excerpt is used.")


def enrich_payload(data: Any, Article: Any, Config: Any, timeout_sec: float, excerpt_chars: int) -> Any:
    items, is_list_root = selected_items_payload(data)
    enriched_items = [enrich_item(item, Article, Config, timeout_sec, excerpt_chars) for item in items]
    for item in enriched_items:
        validate_item(item)

    if is_list_root:
        return enriched_items

    output = copy.deepcopy(data)
    output["items"] = enriched_items
    output["body_enrichment"] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "content_source_values": sorted(CONTENT_SOURCE_VALUES),
        "body_excerpt_policy_values": sorted(POLICY_VALUES),
        "selected_context_source_values": sorted(SELECTED_CONTEXT_SOURCE_VALUES),
        "body_evidence_forbidden": BODY_EVIDENCE_FORBIDDEN,
        "excerpt_chars": excerpt_chars,
        "counts": {
            "items": len(enriched_items),
            "article_body": sum(1 for item in enriched_items if item.get("content_source") == ARTICLE_BODY),
            "rss_fallback": sum(1 for item in enriched_items if item.get("content_source") == RSS_FALLBACK),
            "use_body": sum(1 for item in enriched_items if item.get("body_excerpt_policy") == USE_BODY),
            "rss_only": sum(1 for item in enriched_items if item.get("body_excerpt_policy") == RSS_ONLY),
            "policy_rss_fallback": sum(1 for item in enriched_items if item.get("body_excerpt_policy") == RSS_FALLBACK),
        },
    }
    return output


def main() -> int:
    args = parse_args()
    if args.excerpt_chars < 1:
        raise SystemExit("--excerpt-chars must be 1 or greater.")
    if args.timeout_sec <= 0:
        raise SystemExit("--timeout-sec must be greater than 0.")

    Article, Config = load_dependencies()
    data = load_json(args.json_input)
    payload = enrich_payload(data, Article, Config, args.timeout_sec, args.excerpt_chars)
    write_json(args.output, payload)

    items, _ = selected_items_payload(payload)
    print(f"written: {args.output}")
    print(
        "body enrichment: "
        f"items={len(items)}, "
        f"article_body={sum(1 for item in items if item.get('content_source') == ARTICLE_BODY)}, "
        f"rss_fallback={sum(1 for item in items if item.get('content_source') == RSS_FALLBACK)}, "
        f"use_body={sum(1 for item in items if item.get('body_excerpt_policy') == USE_BODY)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
