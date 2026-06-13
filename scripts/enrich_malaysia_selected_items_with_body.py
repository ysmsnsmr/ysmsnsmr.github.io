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

CRIME_OR_COURT_PHRASES = [
    "court",
    "charged",
    "pleaded",
    "remanded",
    "jail",
    "caning",
    "lawsuit",
    "saman",
    "mahkamah",
    "arrested",
    "police arrested",
    "drug",
    "dadah",
    "molest",
    "sexual misconduct",
    "macc",
    "sprm",
    "probe",
]
INCIDENT_PHRASES = [
    "killed",
    "dies",
    "died",
    "dead",
    "fatal",
    "accident",
    "crash",
    "collision",
    "drowned",
    "lemas",
    "feared drowned",
    "search underway",
]
MARKET_OR_OVERSEAS_PHRASES = [
    "business as usual",
    "counterfeit",
    "job market",
    "work culture",
    "shepherd job",
    "hanoi",
    "vietnam",
    "ringgit",
    "bursa",
    "stock market",
    "forex",
    "currency",
    "greenback",
    "earnings",
    "shares",
    "equities",
]
OIL_PRICE_PHRASES = [
    "oil prices",
    "oil jumps",
    "crude",
    "brent",
]
GEOPOLITICS_NOISE_PHRASES = [
    "middle east",
    "iran",
    "military",
    "conflict",
    "strikes",
    "strike",
    "war",
    "ceasefire",
    "strait of hormuz",
]
COST_OR_SUBSIDY_PHRASES = [
    "ron95",
    "ron97",
    "diesel",
    "fuel prices",
    "petrol",
    "price",
    "prices",
    "tariff",
    "fare",
    "subsidy",
    "subsidised",
    "budi95",
    "rahmah",
    "kos sara hidup",
    "cost of living",
]
FINANCIAL_SERVICE_ACCESS_PHRASES = [
    "bank",
    "banking",
    "branch",
    "premier centre",
    "premier center",
    "wealth",
    "financial service",
    "financial services",
    "investment service",
    "investment services",
    "customer service",
    "hsbc",
]
PUBLIC_SERVICE_PHRASES = [
    "ministry",
    "mof",
    "lhdn",
    "tax",
    "tax exemption",
    "e-derma",
    "jpj",
    "myjpj",
    "mykad",
    "immigration",
    "application",
    "applications",
    "permit",
    "permits",
    "licence",
    "license",
    "renewal",
    "deadline",
    "counter",
    "public service",
    "government",
    "dbkl",
    "mbpj",
    "mcmc",
]
TRANSPORT_OR_INFRA_PHRASES = [
    "road",
    "jalan",
    "traffic",
    "train",
    "bus",
    "mrt",
    "lrt",
    "ktmb",
    "public transport",
    "airport",
    "stadium",
    "facilities",
    "venue",
    "venues",
    "infrastructure",
    "concert",
]
TRANSPORT_CLOSURE_PHRASES = [
    "closure",
    "closed",
    "tutup",
]
TRANSPORT_CONTEXT_PHRASES = [
    "road",
    "lane",
    "jalan",
    "traffic",
    "route",
    "highway",
    "bridge",
    "station",
]
AGRICULTURE_OR_PUBLIC_HEALTH_PHRASES = [
    "pig farm",
    "pig farms",
    "farm",
    "farms",
    "livestock",
    "animals",
    "veterinary",
    "agriculture",
    "public health",
    "environment",
    "tanjong sepat",
]
CONSUMER_OR_CROSSBORDER_SERVICE_PHRASES = [
    "payment",
    "payments",
    "paypal",
    "wechat pay",
    "alipay",
    "qr-code",
    "qr code",
    "e-wallet",
    "ewallet",
    "bank card",
    "foreign bank cards",
    "card",
    "mobile payments",
    "ecommerce",
    "e-commerce",
    "platform",
    "app",
]
VEHICLE_OR_TRANSPORT_SERVICE_PHRASES = [
    "vehicle",
    "vehicles",
    "car",
    "cars",
    "connected vehicles",
    "ev",
    "airline",
    "airport",
    "travel",
    "visa",
]
HEALTH_OR_EDUCATION_PHRASES = [
    "health",
    "medical",
    "hospital",
    "moh",
    "disease",
    "infection",
    "school",
    "education",
    "student",
    "university",
    "spm",
]
POLITICAL_CONTEXT_PHRASES = [
    "election",
    "party",
    "parties",
    "dap",
    "barisan nasional",
    "bn",
    "pakatan harapan",
    "ph",
    "chairman",
    "secretary-general",
    "menteri besar",
    "caretaker",
    "campaign",
    "political",
]
TRANSPORT_OPERATIONAL_PHRASES = [
    "service disruption",
    "service launch",
    "launch of",
    "starts",
    "begins",
    "route",
    "routes",
    "schedule",
    "timetable",
    "fare",
    "station",
    "stations",
    "closure",
    "closed",
    "open",
    "opens",
    "frequency",
    "operation",
    "operations",
]
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


def has_phrase(text: str, phrase: str) -> bool:
    normalized = re.sub(r"\s+", " ", phrase.strip().lower())
    if not normalized:
        return False
    if re.search(r"[a-z0-9]", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None
    return normalized in text


def has_any(text: str, phrases: list[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def matched_phrases(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if has_phrase(text, phrase)]


def normalized_blob(item: dict[str, Any]) -> str:
    parts = [
        item_title(item),
        item_rss_summary(item),
        item.get("body_evidence_excerpt"),
        item.get("body_excerpt"),
    ]
    return clean_text(" ".join(text_value(part) for part in parts)).lower()


def is_oil_geopolitics_market_noise(text: str) -> bool:
    return has_any(text, OIL_PRICE_PHRASES) and has_any(text, GEOPOLITICS_NOISE_PHRASES)


def is_transport_or_infra(text: str) -> bool:
    if has_any(text, TRANSPORT_CLOSURE_PHRASES):
        return has_any(text, TRANSPORT_CONTEXT_PHRASES)
    return has_any(text, TRANSPORT_OR_INFRA_PHRASES)


def classify_body_excerpt_policy(item: dict[str, Any]) -> tuple[str, str]:
    content_source = clean_text(item.get("content_source"))
    if content_source == RSS_FALLBACK:
        return RSS_FALLBACK, "rss_fallback"
    if content_source != ARTICLE_BODY:
        return RSS_FALLBACK, "invalid_content_source"

    text = normalized_blob(item)
    if has_any(text, CRIME_OR_COURT_PHRASES):
        return RSS_ONLY, "blocked_crime_or_court"
    if has_any(text, INCIDENT_PHRASES):
        return RSS_ONLY, "blocked_incident"
    if is_oil_geopolitics_market_noise(text):
        return RSS_ONLY, "blocked_oil_geopolitics"
    if has_any(text, POLITICAL_CONTEXT_PHRASES) and not has_any(text, TRANSPORT_OPERATIONAL_PHRASES):
        return RSS_ONLY, "blocked_political_context"
    if has_any(text, FINANCIAL_SERVICE_ACCESS_PHRASES):
        return USE_BODY, "allowed_financial_service_access"
    if has_any(text, AGRICULTURE_OR_PUBLIC_HEALTH_PHRASES):
        return USE_BODY, "allowed_agriculture_or_public_health"
    if has_any(text, COST_OR_SUBSIDY_PHRASES):
        return USE_BODY, "allowed_cost_or_subsidy"
    if has_any(text, CONSUMER_OR_CROSSBORDER_SERVICE_PHRASES):
        return USE_BODY, "allowed_consumer_or_crossborder_service"
    if has_any(text, VEHICLE_OR_TRANSPORT_SERVICE_PHRASES):
        return USE_BODY, "allowed_vehicle_or_transport_service"
    if is_transport_or_infra(text):
        return USE_BODY, "allowed_transport_or_infra"
    if has_any(text, PUBLIC_SERVICE_PHRASES):
        return USE_BODY, "allowed_public_service"
    if has_any(text, MARKET_OR_OVERSEAS_PHRASES):
        return RSS_ONLY, "blocked_market_or_overseas"
    if has_any(text, HEALTH_OR_EDUCATION_PHRASES):
        return USE_BODY, "allowed_health_or_education"
    return RSS_ONLY, "fallback_uncertain"


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


def body_evidence_focus(item: dict[str, Any]) -> list[str]:
    text = normalized_blob(item)
    focus_groups = [
        ("procedure_or_public_service", PUBLIC_SERVICE_PHRASES),
        ("cost_or_subsidy", COST_OR_SUBSIDY_PHRASES),
        ("transport_or_infra", TRANSPORT_OR_INFRA_PHRASES + TRANSPORT_OPERATIONAL_PHRASES),
        ("consumer_or_payment", CONSUMER_OR_CROSSBORDER_SERVICE_PHRASES),
        ("vehicle_or_transport_service", VEHICLE_OR_TRANSPORT_SERVICE_PHRASES),
        ("health_or_education", HEALTH_OR_EDUCATION_PHRASES),
        ("financial_service_access", FINANCIAL_SERVICE_ACCESS_PHRASES),
        ("agriculture_or_public_health", AGRICULTURE_OR_PUBLIC_HEALTH_PHRASES),
    ]
    return [name for name, phrases in focus_groups if matched_phrases(text, phrases)]


def apply_body_evidence_fields(item: dict[str, Any], excerpt_chars: int) -> None:
    if item.get("content_source") != ARTICLE_BODY:
        item["body_evidence_excerpt"] = ""
        item["body_evidence_focus"] = []
        item["body_evidence_forbidden"] = BODY_EVIDENCE_FORBIDDEN
        return
    evidence = cleanup_body_evidence(clean_text(item.get("body_excerpt")), excerpt_chars)
    item["body_evidence_excerpt"] = evidence
    item["body_evidence_focus"] = body_evidence_focus(item)
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
