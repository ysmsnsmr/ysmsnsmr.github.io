#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
        normalize_url,
    )
except ModuleNotFoundError:
    from scripts.experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
        normalize_url,
    )


SCHEMA_VERSION = "phase2f.4"
DEFAULT_OUTPUT_DIR = "/tmp/malaysia_rss_phase2f4"
DEFAULT_PER_FEED_LIMIT = 50

BACKLOG_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "malay_mail_world",
        "name": "Malay Mail World",
        "url": "https://www.malaymail.com/feed/rss/world",
        "language": "en",
        "source_type": "world_news",
        "role": "backlog_context_candidate",
        "priority": "low",
        "enabled": True,
    },
    {
        "id": "free_malaysia_today",
        "name": "Free Malaysia Today",
        "url": "https://www.freemalaysiatoday.com/feed/",
        "language": "en",
        "source_type": "general_news",
        "role": "backlog_general_candidate",
        "priority": "medium",
        "enabled": True,
    },
    {
        "id": "says_malaysia",
        "name": "SAYS Malaysia",
        "url": "https://says.com/my/rss",
        "language": "en",
        "source_type": "lifestyle_news",
        "role": "backlog_lifestyle_candidate",
        "priority": "medium",
        "enabled": True,
    },
    {
        "id": "lowyat_net",
        "name": "Lowyat.NET",
        "url": "https://www.lowyat.net/feed/",
        "language": "en",
        "source_type": "technology_news",
        "role": "backlog_tech_candidate",
        "priority": "medium",
        "enabled": True,
    },
    {
        "id": "paul_tan",
        "name": "Paul Tan",
        "url": "https://paultan.org/feed/",
        "language": "en",
        "source_type": "automotive_news",
        "role": "backlog_transport_candidate",
        "priority": "medium",
        "enabled": True,
    },
]

LIFE_IMPACT_KEYWORDS = {
    "airport",
    "bank",
    "clinic",
    "cost of living",
    "diesel",
    "electricity",
    "epf",
    "flood",
    "fuel",
    "health",
    "hospital",
    "immigration",
    "internet",
    "jpj",
    "lrt",
    "mrt",
    "mykad",
    "passport",
    "petrol",
    "price",
    "public transport",
    "rail",
    "rain",
    "recall",
    "road",
    "school",
    "scam",
    "storm",
    "tax",
    "tng",
    "toll",
    "touch 'n go",
    "traffic",
    "train",
    "transport",
    "water",
    "weather",
}

NOISE_KEYWORDS = {
    "ai",
    "arrest",
    "celebrity",
    "china",
    "court",
    "deal",
    "earnings",
    "football",
    "gaza",
    "gadget",
    "gaming",
    "geopolitical",
    "iran",
    "israel",
    "market",
    "murder",
    "police",
    "politics",
    "review",
    "stock",
    "trump",
    "ukraine",
    "war",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Observe Phase 2F.4 RSS backlog candidates without adding them to cleaned or production sets."
    )
    parser.add_argument("--date", help="Observation date in YYYYMMDD. Defaults to current Malaysia date.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Cleaned set config used only for duplicate reference.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-feed-limit", type=int, default=DEFAULT_PER_FEED_LIMIT)
    return parser.parse_args()


def observation_date(value: str | None) -> str:
    if value is None:
        return datetime.now(MYT).strftime("%Y%m%d")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise SystemExit("--date must use YYYYMMDD format.") from exc
    return value


def text_blob(item: dict[str, Any]) -> str:
    return f"{item.get('title', '')} {item.get('description', '')}".lower()


def matching_keywords(text: str, keywords: set[str]) -> list[str]:
    matches = []
    for keyword in keywords:
        parts = re.findall(r"[a-z0-9]+", keyword.lower())
        if not parts:
            continue
        pattern = r"\b" + r"[^a-z0-9]+".join(re.escape(part) for part in parts) + r"\b"
        if re.search(pattern, text):
            matches.append(keyword)
    return sorted(matches)


def classify_item(item: dict[str, Any]) -> dict[str, Any]:
    text = text_blob(item)
    life_signals = matching_keywords(text, LIFE_IMPACT_KEYWORDS)
    noise_signals = matching_keywords(text, NOISE_KEYWORDS)
    if life_signals and not noise_signals:
        fit = "life_impact_candidate"
    elif life_signals and noise_signals:
        fit = "mixed"
    elif noise_signals:
        fit = "likely_noise"
    else:
        fit = "unclear"
    return {
        "life_impact_signals": life_signals,
        "noise_signals": noise_signals,
        "source_fit": fit,
    }


def duplicate_count(urls: list[str]) -> int:
    filtered = [url for url in urls if url]
    return len(filtered) - len(set(filtered))


def collect_backlog(per_feed_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feed_results: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for feed in BACKLOG_CANDIDATES:
        feed_result, feed_items = collect_feed("candidate_backlog_set", feed, per_feed_limit)
        feed_results.append(feed_result)
        for item in feed_items:
            classified = classify_item(item)
            items.append({**item, **classified})
    return feed_results, items


def collect_cleaned_reference(config_path: str, per_feed_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = load_config(config_path)
    feeds = [
        feed for feed in config["source_sets"]["english_expansion_set"]
        if feed.get("enabled")
    ]
    feed_results: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for feed in feeds:
        feed_result, feed_items = collect_feed("cleaned_reference_set", feed, per_feed_limit)
        feed_results.append(feed_result)
        items.extend(feed_items)
    return feed_results, items


def fit_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item.get("source_fit", "unknown") for item in items)
    return dict(sorted(counts.items()))


def counts_by_feed(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item.get("feed_id", "unknown") for item in items)
    return dict(sorted(counts.items()))


def feed_fit_summary(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter[str]] = {}
    for item in items:
        feed_id = item.get("feed_id", "unknown")
        summary.setdefault(feed_id, Counter())[item.get("source_fit", "unknown")] += 1
    return {feed_id: dict(sorted(counter.items())) for feed_id, counter in sorted(summary.items())}


def build_payload(
    date: str,
    backlog_feed_results: list[dict[str, Any]],
    backlog_items: list[dict[str, Any]],
    reference_feed_results: list[dict[str, Any]],
    reference_items: list[dict[str, Any]],
    per_feed_limit: int,
) -> dict[str, Any]:
    backlog_urls = [item.get("normalized_link", "") for item in backlog_items]
    reference_urls = {item.get("normalized_link", "") for item in reference_items if item.get("normalized_link")}
    duplicate_vs_cleaned = sorted({url for url in backlog_urls if url and url in reference_urls})
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_date": date,
        "generated_at": datetime.now(MYT).isoformat(),
        "per_feed_limit": per_feed_limit,
        "candidate_feeds": BACKLOG_CANDIDATES,
        "cleaned_reference": {
            "feeds": reference_feed_results,
            "counts": {
                "feeds": len(reference_feed_results),
                "items": len(reference_items),
                "error_feeds": sum(1 for feed in reference_feed_results if feed.get("error") and not feed.get("skipped")),
                "bozo_feeds": sum(1 for feed in reference_feed_results if feed.get("bozo")),
            },
        },
        "candidate_backlog": {
            "feeds": backlog_feed_results,
            "items": backlog_items,
            "counts": {
                "feeds": len(backlog_feed_results),
                "feeds_fetched": sum(1 for feed in backlog_feed_results if feed.get("enabled") and not feed.get("error")),
                "items": len(backlog_items),
                "duplicate_url_count": duplicate_count(backlog_urls),
                "duplicate_vs_cleaned_count": len(duplicate_vs_cleaned),
                "bozo_feeds": sum(1 for feed in backlog_feed_results if feed.get("bozo")),
                "error_feeds": sum(1 for feed in backlog_feed_results if feed.get("error") and not feed.get("skipped")),
                "fit_counts": fit_counts(backlog_items),
                "item_counts_by_feed": counts_by_feed(backlog_items),
                "fit_counts_by_feed": feed_fit_summary(backlog_items),
            },
            "duplicate_urls_vs_cleaned": duplicate_vs_cleaned,
        },
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return lines


def render_memo(payload: dict[str, Any]) -> str:
    backlog = payload["candidate_backlog"]
    counts = backlog["counts"]
    lines = [
        "# Phase 2F.4 RSS候補バックログ観察メモ",
        "",
        f"- 観察日: {payload['observation_date']}",
        f"- 生成時刻: {payload['generated_at']}",
        f"- per-feed limit: {payload['per_feed_limit']}",
        "- Groq API: 未使用",
        "- 本文取得: 未使用",
        "- 本番RSS設定・Phase 2F.3A cleaned set: 未変更",
        "",
        "## Summary",
        "",
        f"- candidate feeds: {counts['feeds']}",
        f"- fetched feeds: {counts['feeds_fetched']}",
        f"- items: {counts['items']}",
        f"- duplicate URLs within backlog: {counts['duplicate_url_count']}",
        f"- duplicate URLs vs cleaned set: {counts['duplicate_vs_cleaned_count']}",
        f"- bozo feeds: {counts['bozo_feeds']}",
        f"- error feeds: {counts['error_feeds']}",
        f"- fit counts: {counts['fit_counts']}",
        "",
        "## Feed Health",
    ]

    feed_rows = []
    fit_by_feed = counts["fit_counts_by_feed"]
    for feed in backlog["feeds"]:
        feed_rows.append(
            [
                feed["id"],
                feed["name"],
                feed["fetched_count"],
                feed["bozo"],
                feed["error"] or "-",
                fit_by_feed.get(feed["id"], {}),
            ]
        )
    lines.extend(markdown_table(["id", "name", "items", "bozo", "error", "fit counts"], feed_rows))

    lines.extend(["", "## Sample Items"])
    items_by_feed: dict[str, list[dict[str, Any]]] = {}
    for item in backlog["items"]:
        items_by_feed.setdefault(item["feed_id"], []).append(item)
    for feed in backlog["feeds"]:
        feed_items = items_by_feed.get(feed["id"], [])
        lines.extend(["", f"### {feed['name']}"])
        if not feed_items:
            lines.append("- no parsed RSS items")
            continue
        for item in feed_items[:8]:
            title = item.get("title") or "(no title)"
            fit = item.get("source_fit", "unknown")
            life = ", ".join(item.get("life_impact_signals", [])) or "-"
            noise = ", ".join(item.get("noise_signals", [])) or "-"
            lines.append(f"- `{fit}` {item.get('published') or '-'} - {title}")
            lines.append(f"  - life: {life}; noise: {noise}")

    lines.extend(
        [
            "",
            "## Day1 Review Notes",
            "",
            "- 生活インパクト適性: RSS title/descriptionから見える範囲で判断する。",
            "- ノイズ量: world/politics/market/gadget/review/incidentなどのRSS語彙で暫定観察する。",
            "- 採用判断: このDay1だけではcleaned setへ追加しない。",
        ]
    )
    return "\n".join(lines) + "\n"


def read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "runs": []}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("runs"), list):
        raise ValueError(f"Invalid observation index: {path}")
    return loaded


def build_index_entry(payload: dict[str, Any], json_path: Path, memo_path: Path) -> dict[str, Any]:
    backlog = payload["candidate_backlog"]
    return {
        "date": payload["observation_date"],
        "generated_at": payload["generated_at"],
        "json_output": str(json_path),
        "memo_output": str(memo_path),
        "counts": backlog["counts"],
        "feed_health": [
            {
                "id": feed["id"],
                "name": feed["name"],
                "fetched_count": feed["fetched_count"],
                "bozo": feed["bozo"],
                "error": feed["error"],
            }
            for feed in backlog["feeds"]
        ],
    }


def update_index(index_path: Path, payload: dict[str, Any], json_path: Path, memo_path: Path) -> dict[str, Any]:
    index = read_index(index_path)
    entry = build_index_entry(payload, json_path, memo_path)
    runs = [run for run in index["runs"] if run.get("date") != payload["observation_date"]]
    runs.append(entry)
    runs.sort(key=lambda run: run.get("date", ""))
    index["schema_version"] = SCHEMA_VERSION
    index["updated_at"] = datetime.now(MYT).isoformat()
    index["runs"] = runs
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.per_feed_limit < 1:
        raise SystemExit("--per-feed-limit must be 1 or greater.")

    date = observation_date(args.date)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"rss_candidate_backlog_{date}.json"
    memo_path = output_dir / f"rss_candidate_backlog_memo_{date}.md"
    index_path = output_dir / "observation_index.json"

    backlog_feed_results, backlog_items = collect_backlog(args.per_feed_limit)
    reference_feed_results, reference_items = collect_cleaned_reference(args.config, args.per_feed_limit)
    payload = build_payload(
        date,
        backlog_feed_results,
        backlog_items,
        reference_feed_results,
        reference_items,
        args.per_feed_limit,
    )
    write_json(json_path, payload)
    write_text(memo_path, render_memo(payload))
    index = update_index(index_path, payload, json_path, memo_path)

    counts = payload["candidate_backlog"]["counts"]
    print(f"written JSON: {json_path}")
    print(f"written memo: {memo_path}")
    print(f"updated index: {index_path}")
    print(f"observation date: {date}")
    print(
        f"candidate_backlog: items={counts['items']} duplicate_urls={counts['duplicate_url_count']} "
        f"duplicate_vs_cleaned={counts['duplicate_vs_cleaned_count']} "
        f"bozo_feeds={counts['bozo_feeds']} error_feeds={counts['error_feeds']}"
    )
    print(f"fit_counts: {counts['fit_counts']}")
    print(f"indexed runs: {len(index['runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
