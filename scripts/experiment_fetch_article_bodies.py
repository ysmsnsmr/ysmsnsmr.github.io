#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "phase2d.article_body_fetch.v1"
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
USER_AGENT = "Mozilla/5.0 (compatible; ysmsnsmr-malaysia-news/0.1; +https://ysmsnsmr.github.io/news/malaysia/)"
EXCERPT_CHARS = 700

SOURCES = [
    {
        "source": "Malay Mail",
        "feed": "Malay Mail Malaysia",
        "url": "https://www.malaymail.com/feed/rss/malaysia",
    },
    {
        "source": "Malay Mail",
        "feed": "Malay Mail Money",
        "url": "https://www.malaymail.com/feed/rss/money",
    },
    {
        "source": "Astro Awani",
        "feed": "Astro Awani National",
        "url": "https://www.astroawani.com/rss/national/public",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimentally fetch article body text from Malaysia RSS article URLs."
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum unique article URLs to fetch.")
    parser.add_argument(
        "--output",
        default="/tmp/article_body_fetch_test.json",
        help="Path to write the experiment JSON output.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=20.0,
        help="Per-article newspaper3k download timeout.",
    )
    return parser.parse_args()


def load_dependencies() -> tuple[Any, Any, Any]:
    try:
        import feedparser  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: feedparser. Install locally with "
            "`python3.12 -m pip install feedparser newspaper3k lxml_html_clean`."
        ) from exc

    try:
        from newspaper import Article, Config  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: newspaper3k/lxml_html_clean. Install locally with "
            "`python3.12 -m pip install feedparser newspaper3k lxml_html_clean`."
        ) from exc

    return feedparser, Article, Config


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def clean_html_text(value: Any) -> str:
    text = text_value(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def entry_link(entry: Any) -> str:
    link = text_value(entry.get("link", "") if hasattr(entry, "get") else "")
    if link:
        return link.strip()
    links = entry.get("links", []) if hasattr(entry, "get") else []
    if isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and item.get("href"):
                return text_value(item.get("href")).strip()
    return ""


def entry_published(entry: Any) -> str:
    for key in ("published", "updated", "pubDate"):
        value = text_value(entry.get(key, "") if hasattr(entry, "get") else "")
        if value:
            return value.strip()
    return ""


def collect_candidates(feedparser: Any, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen_urls: set[str] = set()
    candidates: list[dict[str, Any]] = []
    feed_results: list[dict[str, Any]] = []
    feed_candidate_buckets: list[list[dict[str, Any]]] = []

    for source in SOURCES:
        started = time.monotonic()
        parsed = feedparser.parse(source["url"], agent=USER_AGENT)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        entries = parsed.get("entries", []) if hasattr(parsed, "get") else []
        bozo = bool(parsed.get("bozo", False) if hasattr(parsed, "get") else False)
        bozo_exception = parsed.get("bozo_exception", "") if hasattr(parsed, "get") else ""

        feed_results.append(
            {
                "source": source["source"],
                "feed": source["feed"],
                "url": source["url"],
                "ok": bool(entries),
                "entry_count": len(entries) if isinstance(entries, list) else 0,
                "bozo": bozo,
                "bozo_exception": str(bozo_exception) if bozo_exception else "",
                "elapsed_ms": elapsed_ms,
            }
        )

        source_candidates: list[dict[str, Any]] = []
        if not isinstance(entries, list):
            feed_candidate_buckets.append(source_candidates)
            continue

        for entry in entries:
            url = entry_link(entry)
            if not url:
                continue
            source_candidates.append(
                {
                    "source": source["source"],
                    "feed": source["feed"],
                    "title": clean_html_text(entry.get("title", "") if hasattr(entry, "get") else ""),
                    "url": url,
                    "published": entry_published(entry),
                    "rss_summary": clean_html_text(
                        entry.get("summary", entry.get("description", "")) if hasattr(entry, "get") else ""
                    ),
                }
            )
        feed_candidate_buckets.append(source_candidates)

    positions = [0 for _ in feed_candidate_buckets]
    while len(candidates) < limit:
        added = False
        for bucket_index, bucket in enumerate(feed_candidate_buckets):
            while positions[bucket_index] < len(bucket):
                candidate = bucket[positions[bucket_index]]
                positions[bucket_index] += 1
                if candidate["url"] in seen_urls:
                    continue
                seen_urls.add(candidate["url"])
                candidates.append(candidate)
                added = True
                break
            if len(candidates) >= limit:
                break
        if not added:
            break

    return candidates, feed_results


def excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= EXCERPT_CHARS:
        return cleaned
    return cleaned[:EXCERPT_CHARS].rstrip() + "..."


def fetch_article_body(candidate: dict[str, Any], Article: Any, Config: Any, timeout_sec: float) -> dict[str, Any]:
    item = {
        **candidate,
        "fetched": False,
        "text_length": 0,
        "excerpt": "",
        "error": "",
        "elapsed_ms": 0,
    }
    started = time.monotonic()
    try:
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = timeout_sec
        article = Article(candidate["url"], config=config)
        article.download()
        article.parse()
        text = re.sub(r"\s+", " ", text_value(article.text)).strip()
        if not text:
            item["error"] = "empty_text"
            return item
        item["fetched"] = True
        item["text_length"] = len(text)
        item["excerpt"] = excerpt(text)
        return item
    except Exception as exc:
        item["error"] = f"{type(exc).__name__}: {exc}"
        return item
    finally:
        item["elapsed_ms"] = int((time.monotonic() - started) * 1000)


def build_payload(
    feed_results: list[dict[str, Any]],
    items: list[dict[str, Any]],
    limit: int,
    output_path: str,
) -> dict[str, Any]:
    fetched = sum(1 for item in items if item.get("fetched"))
    failed = len(items) - fetched
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TIMEZONE).isoformat(),
        "output_path": output_path,
        "limit": limit,
        "feeds": feed_results,
        "counts": {
            "feeds": len(feed_results),
            "rss_items_seen": sum(int(feed.get("entry_count", 0)) for feed in feed_results),
            "attempted": len(items),
            "fetched": fetched,
            "failed": failed,
        },
        "items": items,
    }


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be 1 or greater.")
    if args.timeout_sec <= 0:
        raise SystemExit("--timeout-sec must be greater than 0.")

    feedparser, Article, Config = load_dependencies()
    candidates, feed_results = collect_candidates(feedparser, args.limit)
    print(f"Collected {len(candidates)} unique article URLs from {len(feed_results)} feeds.")

    items: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        result = fetch_article_body(candidate, Article, Config, args.timeout_sec)
        items.append(result)
        status = "fetched" if result.get("fetched") else f"failed: {result.get('error', 'unknown')}"
        print(f"item {index}: {status}")

    payload = build_payload(feed_results, items, args.limit, args.output)
    write_json(args.output, payload)
    print(f"written: {args.output}")
    print(f"success: {payload['counts']['fetched']}/{payload['counts']['attempted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
