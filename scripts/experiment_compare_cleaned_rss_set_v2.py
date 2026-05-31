#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
    )
except ModuleNotFoundError:
    from scripts.experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
    )


SCHEMA_VERSION = "phase2f.5"
DEFAULT_OUTPUT_DIR = "/tmp/malaysia_rss_phase2f5"
DEFAULT_PER_FEED_LIMIT = 50

V2_ADDED_FEEDS: list[dict[str, Any]] = [
    {
        "id": "paul_tan",
        "name": "Paul Tan",
        "url": "https://paultan.org/feed/",
        "language": "en",
        "source_type": "automotive_news",
        "role": "v2_transport_candidate",
        "priority": "medium",
        "enabled": True,
    },
    {
        "id": "lowyat_net",
        "name": "Lowyat.NET",
        "url": "https://www.lowyat.net/feed/",
        "language": "en",
        "source_type": "technology_news",
        "role": "v2_tech_life_candidate",
        "priority": "medium",
        "enabled": True,
    },
]

HOLD_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "free_malaysia_today",
        "name": "Free Malaysia Today",
        "url": "https://www.freemalaysiatoday.com/feed/",
        "reason": "hold: broad general feed with politics and incident noise",
    },
    {
        "id": "malay_mail_world",
        "name": "Malay Mail World",
        "url": "https://www.malaymail.com/feed/rss/world",
        "reason": "hold: mostly world context, not Malaysia daily-life default",
    },
    {
        "id": "says_malaysia",
        "name": "SAYS Malaysia",
        "url": "https://says.com/my/rss",
        "reason": "hold: Phase 2F.4 parse error candidate",
    },
    {
        "id": "bernama_english",
        "name": "BERNAMA English",
        "url": "https://www.bernama.com/en/index.php/rssfeed.php",
        "reason": "hold: unvalidated RSS endpoint",
    },
    {
        "id": "the_edge_malaysia",
        "name": "The Edge Malaysia",
        "url": "https://theedgemalaysia.com/feed",
        "reason": "hold: current RSS candidate produced no items",
    },
    {
        "id": "harian_metro_mutakhir",
        "name": "Harian Metro Mutakhir",
        "url": "https://www.hmetro.com.my/mutakhir.xml",
        "reason": "hold: Malay-language fallback only",
    },
]

GENERIC_LIFE_KEYWORDS = {
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

GENERIC_NOISE_KEYWORDS = {
    "arrest",
    "celebrity",
    "china",
    "court",
    "earnings",
    "football",
    "gaza",
    "gadget",
    "gaming",
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

SOURCE_SPECIFIC_SIGNALS = {
    "paul_tan": {
        "positive": {
            "driver",
            "enforcement",
            "jpj",
            "lrt",
            "mykad",
            "petrol",
            "public transport",
            "rail",
            "recall",
            "road",
            "safety",
            "toll",
            "train",
            "transport",
            "vehicle safety",
        },
        "noise": {
            "car launch",
            "ckd",
            "concept",
            "drive sale",
            "ev plant",
            "launch",
            "model",
            "priced at",
            "review",
            "sale",
            "suv",
        },
    },
    "lowyat_net": {
        "positive": {
            "budi95",
            "digital id",
            "fuel subsidy",
            "government",
            "internet",
            "lrt",
            "mydigital",
            "mykad",
            "payment",
            "petrol",
            "public transport",
            "rail",
            "subsidy",
            "telco",
            "touch 'n go",
            "transport",
        },
        "noise": {
            "acer",
            "apple",
            "call of duty",
            "gaming",
            "laptop",
            "launch",
            "phone",
            "razer",
            "redmagic",
            "review",
            "trailer",
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare cleaned RSS set v1 with local-only v2 adding Paul Tan and Lowyat.NET."
    )
    parser.add_argument("--date", help="Observation date in YYYYMMDD. Defaults to current Malaysia date.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
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
    feed_id = item.get("feed_id", "")
    text = text_blob(item)
    life_signals = set(matching_keywords(text, GENERIC_LIFE_KEYWORDS))
    noise_signals = set(matching_keywords(text, GENERIC_NOISE_KEYWORDS))
    source_signals = SOURCE_SPECIFIC_SIGNALS.get(feed_id)
    source_positive: list[str] = []
    source_noise: list[str] = []

    if source_signals:
        source_positive = matching_keywords(text, source_signals["positive"])
        source_noise = matching_keywords(text, source_signals["noise"])
        life_signals.update(source_positive)
        noise_signals.update(source_noise)

    if life_signals and not noise_signals:
        fit = "life_impact_candidate"
    elif life_signals and noise_signals:
        fit = "mixed"
    elif noise_signals:
        fit = "likely_noise"
    else:
        fit = "unclear"

    return {
        **item,
        "life_impact_signals": sorted(life_signals),
        "noise_signals": sorted(noise_signals),
        "source_specific_positive_signals": source_positive,
        "source_specific_noise_signals": source_noise,
        "source_fit": fit,
    }


def enabled_v1_feeds(config_path: str) -> list[dict[str, Any]]:
    config = load_config(config_path)
    return [
        feed for feed in config["source_sets"]["english_expansion_set"]
        if feed.get("enabled")
    ]


def retag_feed_result(feed: dict[str, Any], set_name: str) -> dict[str, Any]:
    copied = deepcopy(feed)
    copied["set"] = set_name
    return copied


def retag_item(item: dict[str, Any], set_name: str) -> dict[str, Any]:
    copied = deepcopy(item)
    copied["source_set"] = set_name
    return copied


def collect_v1(feeds: list[dict[str, Any]], per_feed_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feed_results: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for feed in feeds:
        feed_result, feed_items = collect_feed("cleaned_v1", feed, per_feed_limit)
        feed_results.append(feed_result)
        items.extend(classify_item(item) for item in feed_items)
    return feed_results, items


def collect_v2(
    v1_feed_results: list[dict[str, Any]],
    v1_items: list[dict[str, Any]],
    per_feed_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feed_results = [retag_feed_result(feed, "cleaned_v2") for feed in v1_feed_results]
    items = [retag_item(item, "cleaned_v2") for item in v1_items]
    for feed in V2_ADDED_FEEDS:
        feed_result, feed_items = collect_feed("cleaned_v2", feed, per_feed_limit)
        feed_results.append(feed_result)
        items.extend(classify_item(item) for item in feed_items)
    return feed_results, items


def duplicate_count(items: list[dict[str, Any]]) -> int:
    urls = [item.get("normalized_link", "") for item in items if item.get("normalized_link")]
    return len(urls) - len(set(urls))


def urls_for(items: list[dict[str, Any]]) -> set[str]:
    return {item["normalized_link"] for item in items if item.get("normalized_link")}


def counts_by_feed(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item.get("feed_id", "unknown") for item in items)
    return dict(sorted(counts.items()))


def fit_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item.get("source_fit", "unknown") for item in items)
    return dict(sorted(counts.items()))


def feed_fit_summary(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter[str]] = {}
    for item in items:
        feed_id = item.get("feed_id", "unknown")
        summary.setdefault(feed_id, Counter())[item.get("source_fit", "unknown")] += 1
    return {feed_id: dict(sorted(counter.items())) for feed_id, counter in sorted(summary.items())}


def set_summary(feed_results: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "feeds": feed_results,
        "items": items,
        "counts": {
            "feeds": len(feed_results),
            "feeds_fetched": sum(1 for feed in feed_results if feed.get("enabled") and not feed.get("error")),
            "items": len(items),
            "duplicate_url_count": duplicate_count(items),
            "bozo_feeds": sum(1 for feed in feed_results if feed.get("bozo")),
            "error_feeds": sum(1 for feed in feed_results if feed.get("error") and not feed.get("skipped")),
            "item_counts_by_feed": counts_by_feed(items),
            "fit_counts": fit_counts(items),
            "fit_counts_by_feed": feed_fit_summary(items),
        },
    }


def build_comparison(v1_items: list[dict[str, Any]], v2_items: list[dict[str, Any]]) -> dict[str, Any]:
    v1_urls = urls_for(v1_items)
    v2_urls = urls_for(v2_items)
    v1_counts = Counter(item.get("feed_id", "unknown") for item in v1_items)
    v2_counts = Counter(item.get("feed_id", "unknown") for item in v2_items)
    feed_ids = sorted(set(v1_counts) | set(v2_counts))
    return {
        "shared_urls": sorted(v1_urls & v2_urls),
        "only_in_v1": sorted(v1_urls - v2_urls),
        "only_in_v2": sorted(v2_urls - v1_urls),
        "counts": {
            "shared_urls": len(v1_urls & v2_urls),
            "only_in_v1": len(v1_urls - v2_urls),
            "only_in_v2": len(v2_urls - v1_urls),
        },
        "source_deltas": [
            {
                "feed_id": feed_id,
                "v1": v1_counts.get(feed_id, 0),
                "v2": v2_counts.get(feed_id, 0),
                "delta": v2_counts.get(feed_id, 0) - v1_counts.get(feed_id, 0),
            }
            for feed_id in feed_ids
        ],
    }


def build_payload(
    date: str,
    v1_feed_results: list[dict[str, Any]],
    v1_items: list[dict[str, Any]],
    v2_feed_results: list[dict[str, Any]],
    v2_items: list[dict[str, Any]],
    v1_feeds: list[dict[str, Any]],
    per_feed_limit: int,
) -> dict[str, Any]:
    source_specific_assumptions = {
        feed_id: {
            "positive": sorted(values["positive"]),
            "noise": sorted(values["noise"]),
        }
        for feed_id, values in SOURCE_SPECIFIC_SIGNALS.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_date": date,
        "generated_at": datetime.now(MYT).isoformat(),
        "per_feed_limit": per_feed_limit,
        "sets": {
            "v1": {
                "definition": v1_feeds,
                **set_summary(v1_feed_results, v1_items),
            },
            "v2": {
                "definition": v1_feeds + V2_ADDED_FEEDS,
                "added_feeds": V2_ADDED_FEEDS,
                **set_summary(v2_feed_results, v2_items),
            },
        },
        "hold_candidates": HOLD_CANDIDATES,
        "comparison": build_comparison(v1_items, v2_items),
        "source_specific_filter_assumptions": source_specific_assumptions,
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return lines


def sample_lines(items: list[dict[str, Any]], feed_id: str, limit: int = 8) -> list[str]:
    selected = [item for item in items if item.get("feed_id") == feed_id][:limit]
    if not selected:
        return ["- no parsed RSS items"]
    lines = []
    for item in selected:
        title = item.get("title") or "(no title)"
        fit = item.get("source_fit", "unknown")
        life = ", ".join(item.get("life_impact_signals", [])) or "-"
        noise = ", ".join(item.get("noise_signals", [])) or "-"
        source_positive = ", ".join(item.get("source_specific_positive_signals", [])) or "-"
        source_noise = ", ".join(item.get("source_specific_noise_signals", [])) or "-"
        lines.append(f"- `{fit}` {item.get('published') or '-'} - {title}")
        lines.append(f"  - life: {life}; noise: {noise}")
        if feed_id in SOURCE_SPECIFIC_SIGNALS:
            lines.append(f"  - source-specific positive: {source_positive}; source-specific noise: {source_noise}")
    return lines


def render_memo(payload: dict[str, Any]) -> str:
    v1 = payload["sets"]["v1"]
    v2 = payload["sets"]["v2"]
    comparison = payload["comparison"]
    lines = [
        "# Phase 2F.5 cleaned RSS set v2 comparison",
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
    ]
    lines.extend(
        markdown_table(
            ["set", "feeds", "items", "duplicate URLs", "bozo feeds", "error feeds", "fit counts"],
            [
                [
                    "v1",
                    v1["counts"]["feeds"],
                    v1["counts"]["items"],
                    v1["counts"]["duplicate_url_count"],
                    v1["counts"]["bozo_feeds"],
                    v1["counts"]["error_feeds"],
                    v1["counts"]["fit_counts"],
                ],
                [
                    "v2",
                    v2["counts"]["feeds"],
                    v2["counts"]["items"],
                    v2["counts"]["duplicate_url_count"],
                    v2["counts"]["bozo_feeds"],
                    v2["counts"]["error_feeds"],
                    v2["counts"]["fit_counts"],
                ],
            ],
        )
    )
    lines.extend(
        [
            "",
            "## v1 vs v2",
            "",
            f"- shared URLs: {comparison['counts']['shared_urls']}",
            f"- only in v1: {comparison['counts']['only_in_v1']}",
            f"- only in v2: {comparison['counts']['only_in_v2']}",
            "",
            "### Source Deltas",
        ]
    )
    lines.extend(
        markdown_table(
            ["feed_id", "v1", "v2", "delta"],
            [[row["feed_id"], row["v1"], row["v2"], row["delta"]] for row in comparison["source_deltas"]],
        )
    )
    lines.extend(["", "## Feed Health"])
    feed_rows = []
    for set_name in ["v1", "v2"]:
        for feed in payload["sets"][set_name]["feeds"]:
            feed_rows.append(
                [
                    set_name,
                    feed["id"],
                    feed["name"],
                    feed["fetched_count"],
                    feed["bozo"],
                    feed["error"] or "-",
                ]
            )
    lines.extend(markdown_table(["set", "id", "name", "items", "bozo", "error"], feed_rows))

    lines.extend(
        [
            "",
            "## Added Source Samples",
            "",
            "### Paul Tan",
            "",
            "Source-specific filter premise: keep only transport/public-service/driver-impact items; treat launches, sales, reviews, and model-price-only items as noise.",
        ]
    )
    lines.extend(sample_lines(v2["items"], "paul_tan"))
    lines.extend(
        [
            "",
            "### Lowyat.NET",
            "",
            "Source-specific filter premise: keep telco, public internet, MyKad, payments, fuel subsidy, Touch 'n Go, public transport tech, or government digital-service items; treat product launches and gadget reviews as noise.",
        ]
    )
    lines.extend(sample_lines(v2["items"], "lowyat_net"))

    lines.extend(["", "## Hold Candidates"])
    for candidate in payload["hold_candidates"]:
        lines.append(f"- `{candidate['id']}` {candidate['name']}: {candidate['reason']}")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- v2 is not a production source set.",
            "- Paul Tan and Lowyat.NET should be evaluated only with source-specific filters.",
            "- This comparison labels RSS metadata for observation; it does not select final articles.",
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


def index_entry(payload: dict[str, Any], json_path: Path, memo_path: Path) -> dict[str, Any]:
    return {
        "date": payload["observation_date"],
        "generated_at": payload["generated_at"],
        "json_output": str(json_path),
        "memo_output": str(memo_path),
        "v1_counts": payload["sets"]["v1"]["counts"],
        "v2_counts": payload["sets"]["v2"]["counts"],
        "comparison_counts": payload["comparison"]["counts"],
        "source_deltas": payload["comparison"]["source_deltas"],
    }


def update_index(index_path: Path, payload: dict[str, Any], json_path: Path, memo_path: Path) -> dict[str, Any]:
    index = read_index(index_path)
    entry = index_entry(payload, json_path, memo_path)
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
    json_path = output_dir / f"cleaned_rss_v2_comparison_{date}.json"
    memo_path = output_dir / f"cleaned_rss_v2_comparison_memo_{date}.md"
    index_path = output_dir / "observation_index.json"

    v1_feeds = enabled_v1_feeds(args.config)
    v1_feed_results, v1_items = collect_v1(v1_feeds, args.per_feed_limit)
    v2_feed_results, v2_items = collect_v2(v1_feed_results, v1_items, args.per_feed_limit)
    payload = build_payload(
        date,
        v1_feed_results,
        v1_items,
        v2_feed_results,
        v2_items,
        v1_feeds,
        args.per_feed_limit,
    )
    write_json(json_path, payload)
    write_text(memo_path, render_memo(payload))
    index = update_index(index_path, payload, json_path, memo_path)

    print(f"written JSON: {json_path}")
    print(f"written memo: {memo_path}")
    print(f"updated index: {index_path}")
    print(f"observation date: {date}")
    print(
        f"v1: items={payload['sets']['v1']['counts']['items']} "
        f"duplicates={payload['sets']['v1']['counts']['duplicate_url_count']} "
        f"errors={payload['sets']['v1']['counts']['error_feeds']}"
    )
    print(
        f"v2: items={payload['sets']['v2']['counts']['items']} "
        f"duplicates={payload['sets']['v2']['counts']['duplicate_url_count']} "
        f"errors={payload['sets']['v2']['counts']['error_feeds']}"
    )
    print(f"only_in_v2={payload['comparison']['counts']['only_in_v2']}")
    print(f"indexed runs: {len(index['runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
