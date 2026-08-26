#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import types
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    from experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
        normalize_url,
        parse_feed_items,
    )
except ModuleNotFoundError:
    from scripts.experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        collect_feed,
        load_config,
        normalize_url,
        parse_feed_items,
    )

try:
    from malaysia_rss_summary import fetch_rss as fetch_raw_rss
except ModuleNotFoundError:
    from scripts.malaysia_rss_summary import fetch_rss as fetch_raw_rss


SCHEMA_VERSION = "phase2f.4"
DEFAULT_OUTPUT_DIR = "/tmp/malaysia_rss_phase2f4"
DEFAULT_PER_FEED_LIMIT = 50

DAY1_SCHEMA_VERSION = "malaysia-news-source-shadow/business-today-day1/v1"
DAY1_DEFAULT_OUTPUT_ROOT = "/tmp/malaysia_news_source_shadow/business_today"
DAY1_SOURCE_ID = "business_today"
DAY1_PUBLISHER = "BusinessToday"
DAY1_FEED_URL = "https://www.businesstoday.com.my/feed/"
DAY1_ARTIFACT_NAMES = {
    "response.xml",
    "raw_manifest.json",
    "raw_items.json",
    "annotations.json",
    "selector_diagnostics.json",
    "comparison.md",
}
ANNOTATION_RELEVANCE_VALUES = {"useful", "unclear", "noise"}
ANNOTATION_RELATIONSHIP_VALUES = {"original", "syndication", "same_event", "unknown"}
ANNOTATION_SOURCE_HINT_VALUES = {"Bernama", "government", "Reuters", "other", "unknown"}
REPO_ROOT = Path(__file__).resolve().parents[1]

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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--business-today-day1",
        action="store_true",
        help="Create the no-overwrite BusinessToday Day-1 raw shadow artifact set.",
    )
    mode.add_argument(
        "--validate-business-today-run",
        metavar="RUN_DIR",
        help="Validate an existing BusinessToday Day-1 artifact directory, including manual annotations.",
    )
    parser.add_argument("--date", help="Observation date in YYYYMMDD. Defaults to current Malaysia date.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Cleaned set config used only for duplicate reference.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-feed-limit", type=int, default=DEFAULT_PER_FEED_LIMIT)
    parser.add_argument("--run-id", help="Filesystem-safe Day-1 run id. Defaults to the Malaysia retrieval timestamp.")
    parser.add_argument("--baseline-ref", help="Local git ref for the scheduled production baseline.")
    parser.add_argument("--day1-output-root", default=DAY1_DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--business-today-feed-url", default=DAY1_FEED_URL)
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_item_id(source_id: str, normalized_article_url: str) -> str:
    return sha256_bytes(f"{source_id}\n{normalized_article_url}".encode("utf-8"))


def git_bytes(*args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        error = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {error}")
    return proc.stdout


def default_baseline_ref() -> str:
    try:
        value = git_bytes("symbolic-ref", "--short", "refs/remotes/origin/HEAD").decode("utf-8").strip()
    except RuntimeError:
        value = ""
    return value or "origin/main"


def scheduled_cli_args(workflow_text: str) -> list[str]:
    lines = workflow_text.splitlines()
    marker = "python3 -B scripts/malaysia_rss_summary.py"
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        command_lines = [line.strip().removesuffix("\\").strip()]
        while line.rstrip().endswith("\\"):
            index += 1
            if index >= len(lines):
                raise ValueError("Scheduled production command ends with an incomplete continuation.")
            line = lines[index]
            command_lines.append(line.strip().removesuffix("\\").strip())
        tokens = shlex.split(" ".join(command_lines))
        try:
            script_index = tokens.index("scripts/malaysia_rss_summary.py")
        except ValueError as exc:
            raise ValueError("Scheduled production command does not invoke the expected selector.") from exc
        return tokens[script_index + 1 :]
    raise ValueError("Scheduled production selector command was not found in the workflow.")


def load_baseline_selector(selector_bytes: bytes, commit: str) -> types.ModuleType:
    module_name = f"_malaysia_news_baseline_{commit[:12]}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    module = types.ModuleType(module_name)
    module.__file__ = f"{commit}:scripts/malaysia_rss_summary.py"
    sys.modules[module_name] = module
    try:
        exec(compile(selector_bytes, module.__file__, "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def baseline_snapshot(ref: str) -> tuple[dict[str, Any], types.ModuleType]:
    commit = git_bytes("rev-parse", "--verify", f"{ref}^{{commit}}").decode("utf-8").strip()
    workflow_path = ".github/workflows/malaysia-rss-summary.yml"
    selector_path = "scripts/malaysia_rss_summary.py"
    workflow_bytes = git_bytes("show", f"{commit}:{workflow_path}")
    selector_bytes = git_bytes("show", f"{commit}:{selector_path}")
    cli_args = scheduled_cli_args(workflow_bytes.decode("utf-8"))
    selector = load_baseline_selector(selector_bytes, commit)

    include_paul_tan = "--include-paul-tan" in cli_args
    source_tuples = list(selector.SOURCES)
    if include_paul_tan:
        source_tuples.append(selector.PAUL_TAN_SOURCE)
    sources = [
        {"source": source, "feed": feed, "url": url}
        for source, feed, url in source_tuples
    ]
    if len(sources) != 4 or not include_paul_tan:
        raise ValueError(
            "The scheduled production baseline must resolve to the three default feeds plus Paul Tan opt-in."
        )
    return (
        {
            "git_ref": ref,
            "repository_commit": commit,
            "workflow_path": workflow_path,
            "workflow_sha256": sha256_bytes(workflow_bytes),
            "selector_path": selector_path,
            "selector_sha256": sha256_bytes(selector_bytes),
            "cli_args": cli_args,
            "sources": sources,
        },
        selector,
    )


def parse_raw_candidate_items(
    response: bytes,
    feed_url: str,
    retrieved_at: str,
) -> tuple[list[dict[str, Any]], bool, str]:
    parsed_items, bozo, parse_warning = parse_feed_items(response, 1_000_000)
    raw_items: list[dict[str, Any]] = []
    for item in parsed_items:
        article_url = item.get("link", "").strip()
        normalized_article_url = normalize_url(article_url) if article_url else ""
        raw_items.append(
            {
                "item_id": stable_item_id(DAY1_SOURCE_ID, normalized_article_url),
                "source_id": DAY1_SOURCE_ID,
                "publisher": DAY1_PUBLISHER,
                "feed_url": feed_url,
                "article_url": article_url,
                "normalized_url": normalized_article_url,
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "published_at": item.get("published", ""),
                "retrieved_at": retrieved_at,
            }
        )
    return raw_items, bozo, parse_warning


def selector_datetime(value: str, selector: types.ModuleType) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = selector.parse_date(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=selector.MYT)
    return parsed.astimezone(selector.MYT)


def candidate_selector_items(
    raw_items: list[dict[str, Any]],
    selector: types.ModuleType,
) -> tuple[list[Any], dict[int, str]]:
    items: list[Any] = []
    item_ids: dict[int, str] = {}
    for raw_item in raw_items:
        published = selector_datetime(str(raw_item.get("published_at", "")), selector)
        if published is None:
            continue
        item = selector.Item(
            DAY1_PUBLISHER,
            DAY1_PUBLISHER,
            str(raw_item.get("title", "")),
            str(raw_item.get("description", "")),
            published,
            str(raw_item.get("published_at", "")),
            str(raw_item.get("article_url", "")),
        )
        items.append(item)
        item_ids[id(item)] = str(raw_item["item_id"])
    return items, item_ids


def collect_baseline_items(
    baseline: dict[str, Any],
    selector: types.ModuleType,
    fetcher: Callable[[str], Any],
) -> tuple[list[dict[str, Any]], list[Any]]:
    feed_health: list[dict[str, Any]] = []
    baseline_items: list[Any] = []
    for source in baseline["sources"]:
        result = fetcher(source["url"])
        health = {
            **source,
            "http_status": str(getattr(result, "status", "")),
            "content_type": str(getattr(result, "content_type", "")),
            "fetch_method": str(getattr(result, "method", "")),
            "error": str(getattr(result, "error", "")),
            "item_count": 0,
        }
        if not result.ok:
            feed_health.append(health)
            continue
        try:
            items = selector.parse_items(source["source"], source["feed"], result.data)
        except Exception as exc:
            health["error"] = f"parse failed: {type(exc).__name__}: {exc}"
            feed_health.append(health)
            continue
        health["item_count"] = len(items)
        feed_health.append(health)
        baseline_items.extend(items)
    return feed_health, baseline_items


def pre_cap_selector_status(
    items: list[Any],
    selector: types.ModuleType,
    now: datetime,
) -> dict[int, dict[str, Any]]:
    cutoff = now - timedelta(hours=selector.RECENT_WINDOW_HOURS)
    recent = [item for item in items if cutoff <= item.pub_date <= now]
    by_key: dict[str, Any] = {}
    for item in items:
        selector.evaluate_item(item)
    for item in recent:
        key = selector.key_for(item)
        current = by_key.get(key)
        if current is None or (item.score, item.pub_date) > (current.score, current.pub_date):
            by_key[key] = item

    status: dict[int, dict[str, Any]] = {}
    for item in items:
        reasons: list[str] = []
        eligible = True
        key = selector.key_for(item)
        if not (cutoff <= item.pub_date <= now):
            eligible = False
            reasons.append("outside_recent_window")
        elif by_key.get(key) is not item:
            eligible = False
            reasons.append("duplicate_canonical_event")
        elif item.score < 3:
            eligible = False
            reasons.append("selector_score_below_3")
        elif selector.should_exclude_item(item):
            eligible = False
            reasons.append("production_selector_excluded")
        elif selector.is_forced_final_noise(item):
            eligible = False
            reasons.append("production_final_noise_gate")
        if not eligible:
            reasons.extend(reason for reason in item.penalties if reason not in reasons)
        status[id(item)] = {
            "selector_score": item.score,
            "selector_category": selector.category_for(item),
            "selector_eligible": eligible,
            "exclusion_reasons": reasons,
        }
    return status


def final_duplicate_reason(item: Any, selected: list[Any], selector: types.ModuleType) -> str:
    item_url = normalize_url(item.link) if item.link else ""
    item_key = selector.key_for(item)
    for selected_item in selected:
        if item_url and normalize_url(selected_item.link) == item_url:
            return "duplicate_url_finalization"
        if item_key and selector.key_for(selected_item) == item_key:
            return "duplicate_canonical_event_finalization"
    return ""


def build_selector_diagnostics(
    raw_items: list[dict[str, Any]],
    candidate_items: list[Any],
    candidate_item_ids: dict[int, str],
    baseline_items: list[Any],
    selector: types.ModuleType,
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_selected = selector.select_items(baseline_items, now)
    baseline_selected_ids = {id(item) for item in baseline_selected}
    combined_items = [*baseline_items, *candidate_items]
    combined_selected = selector.select_items(combined_items, now)
    combined_selected_ids = {id(item) for item in combined_selected}
    status = pre_cap_selector_status(combined_items, selector, now)

    item_by_stable_id = {candidate_item_ids[id(item)]: item for item in candidate_items}
    diagnostics: list[dict[str, Any]] = []
    for raw_item in raw_items:
        item_id = str(raw_item["item_id"])
        selector_item = item_by_stable_id.get(item_id)
        if selector_item is None:
            diagnostics.append(
                {
                    "item_id": item_id,
                    "source_gate_eligible": True,
                    "source_gate_reason": "not_applicable_no_business_today_gate",
                    "selector_score": None,
                    "selector_category": "",
                    "exclusion_reasons": ["missing_or_invalid_published_at"],
                    "selector_eligible": False,
                    "selected_after_caps": False,
                    "displaced_by_cap": False,
                }
            )
            continue
        item_status = status[id(selector_item)]
        selected_after_caps = id(selector_item) in combined_selected_ids
        duplicate_reason = ""
        if item_status["selector_eligible"] and not selected_after_caps:
            duplicate_reason = final_duplicate_reason(selector_item, combined_selected, selector)
        exclusion_reasons = list(item_status["exclusion_reasons"])
        if duplicate_reason:
            exclusion_reasons.append(duplicate_reason)
        diagnostics.append(
            {
                "item_id": item_id,
                "source_gate_eligible": True,
                "source_gate_reason": "not_applicable_no_business_today_gate",
                "selector_score": item_status["selector_score"],
                "selector_category": item_status["selector_category"],
                "exclusion_reasons": exclusion_reasons,
                "selector_eligible": item_status["selector_eligible"],
                "selected_after_caps": selected_after_caps,
                "displaced_by_cap": bool(
                    item_status["selector_eligible"] and not selected_after_caps and not duplicate_reason
                ),
            }
        )

    displaced_baseline: list[dict[str, Any]] = []
    for item in baseline_items:
        if id(item) not in baseline_selected_ids or id(item) in combined_selected_ids:
            continue
        item_status = status[id(item)]
        duplicate_reason = ""
        if item_status["selector_eligible"]:
            duplicate_reason = final_duplicate_reason(item, combined_selected, selector)
        displaced_baseline.append(
            {
                "source": item.source,
                "feed": item.feed,
                "title": item.title,
                "article_url": item.link,
                "selector_category": item_status["selector_category"],
                "reason": duplicate_reason or (
                    "cap_or_request_limit" if item_status["selector_eligible"] else "selector_or_deduplication"
                ),
                "displaced_by_cap": bool(item_status["selector_eligible"] and not duplicate_reason),
            }
        )

    summary = {
        "baseline_items_parsed": len(baseline_items),
        "baseline_selected_without_candidate": len(baseline_selected),
        "combined_selected": len(combined_selected),
        "candidate_selected_after_caps": sum(1 for row in diagnostics if row["selected_after_caps"]),
        "candidate_displaced_by_cap": sum(1 for row in diagnostics if row["displaced_by_cap"]),
        "baseline_displaced_by_cap": sum(1 for row in displaced_baseline if row["displaced_by_cap"]),
        "baseline_removed_after_candidate_addition": displaced_baseline,
    }
    return diagnostics, summary


def render_day1_comparison(
    manifest: dict[str, Any],
    diagnostics: list[dict[str, Any]],
    selector_summary: dict[str, Any],
    baseline_feed_health: list[dict[str, Any]],
) -> str:
    eligible = sum(1 for row in diagnostics if row["selector_eligible"])
    selected = sum(1 for row in diagnostics if row["selected_after_caps"])
    errors = sum(1 for feed in baseline_feed_health if feed["error"])
    lines = [
        "# BusinessToday Shadow Day-1 Comparison",
        "",
        "- validation: PASS",
        f"- run_id: `{manifest['run_id']}`",
        f"- retrieved_at: `{manifest['retrieved_at']}`",
        f"- baseline commit: `{manifest['baseline']['repository_commit']}`",
        f"- baseline sources: {len(manifest['baseline']['sources'])} (scheduled production)",
        f"- BusinessToday raw items before selector: {manifest['item_count']}",
        f"- selector eligible: {eligible}",
        f"- selected after caps: {selected}",
        f"- BusinessToday cap drops: {selector_summary['candidate_displaced_by_cap']}",
        f"- baseline cap displacement: {selector_summary['baseline_displaced_by_cap']}",
        f"- baseline feed errors: {errors}",
        "- production / Pages / Groq changes: none",
        "",
        "## Baseline feed health",
        "",
        "| Feed | HTTP | Parsed items | Error |",
        "| --- | --- | ---: | --- |",
    ]
    for feed in baseline_feed_health:
        error = str(feed["error"] or "-").replace("|", "\\|")
        lines.append(f"| {feed['feed']} | {feed['http_status'] or '-'} | {feed['item_count']} | {error} |")
    lines.extend(
        [
            "",
            "## Manual review",
            "",
            "`annotations.json` is intentionally separate from raw data. Add `useful`, `unclear`, or `noise`",
            "labels there, then run the validator again. `useful` and `unclear` require an `event_group`.",
            "",
            "Day-1 proves collection and replay only. It does not approve BusinessToday for production.",
        ]
    )
    return "\n".join(lines) + "\n"


def atomic_write_bytes(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    value = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, value)


def load_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return loaded


def validate_business_today_run(run_dir: Path) -> list[str]:
    errors: list[str] = []
    missing = sorted(name for name in DAY1_ARTIFACT_NAMES if not (run_dir / name).is_file())
    if missing:
        return [f"missing_artifacts:{','.join(missing)}"]

    try:
        manifest = load_json_object(run_dir / "raw_manifest.json")
        raw_payload = load_json_object(run_dir / "raw_items.json")
        annotation_payload = load_json_object(run_dir / "annotations.json")
        diagnostics_payload = load_json_object(run_dir / "selector_diagnostics.json")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"invalid_json:{type(exc).__name__}:{exc}"]

    response = (run_dir / "response.xml").read_bytes()
    if manifest.get("schema_version") != DAY1_SCHEMA_VERSION:
        errors.append("manifest_schema_version")
    if manifest.get("run_id") != run_dir.name:
        errors.append("manifest_run_id")
    if manifest.get("source_id") != DAY1_SOURCE_ID:
        errors.append("manifest_source_id")
    if manifest.get("response_sha256") != sha256_bytes(response):
        errors.append("response_sha256")

    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("baseline_object")
        baseline = {}
    sources = baseline.get("sources")
    if not isinstance(sources, list) or len(sources) != 4:
        errors.append("baseline_source_count")
    cli_args = baseline.get("cli_args")
    if not isinstance(cli_args, list) or "--include-paul-tan" not in cli_args:
        errors.append("baseline_cli_args")
    for hash_field in ("workflow_sha256", "selector_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(baseline.get(hash_field, ""))):
            errors.append(f"baseline_{hash_field}")

    raw_items = raw_payload.get("items")
    if not isinstance(raw_items, list):
        errors.append("raw_items_list")
        raw_items = []
    if raw_payload.get("run_id") != manifest.get("run_id"):
        errors.append("raw_items_run_id")
    if manifest.get("item_count") != len(raw_items):
        errors.append("raw_item_count")
    known_item_ids: set[str] = set()
    required_raw_fields = {
        "item_id", "source_id", "publisher", "feed_url", "article_url", "normalized_url",
        "title", "description", "published_at", "retrieved_at",
    }
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            errors.append(f"raw_item_{index}_object")
            continue
        if not required_raw_fields <= set(item):
            errors.append(f"raw_item_{index}_fields")
            continue
        normalized_article_url = str(item.get("normalized_url", ""))
        if not normalized_article_url:
            errors.append(f"raw_item_{index}_normalized_url")
        expected_id = stable_item_id(str(item.get("source_id", "")), normalized_article_url)
        item_id = str(item.get("item_id", ""))
        if item_id != expected_id:
            errors.append(f"raw_item_{index}_item_id")
        if item_id in known_item_ids:
            errors.append(f"raw_item_{index}_duplicate_item_id")
        known_item_ids.add(item_id)

    annotations = annotation_payload.get("annotations")
    if not isinstance(annotations, list):
        errors.append("annotations_list")
        annotations = []
    if annotation_payload.get("run_id") != manifest.get("run_id"):
        errors.append("annotations_run_id")
    seen_annotations: set[str] = set()
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            errors.append(f"annotation_{index}_object")
            continue
        item_id = str(annotation.get("item_id", ""))
        relevance = annotation.get("manual_relevance")
        if item_id not in known_item_ids:
            errors.append(f"annotation_{index}_unknown_item_id")
        if item_id in seen_annotations:
            errors.append(f"annotation_{index}_duplicate_item_id")
        seen_annotations.add(item_id)
        required_annotation_fields = {
            "item_id", "manual_relevance", "event_group", "relationship_hint",
            "source_hint", "review_note", "reviewed_at",
        }
        if not required_annotation_fields <= set(annotation):
            errors.append(f"annotation_{index}_fields")
        if relevance not in ANNOTATION_RELEVANCE_VALUES:
            errors.append(f"annotation_{index}_manual_relevance")
        if relevance in {"useful", "unclear"} and not str(annotation.get("event_group", "")).strip():
            errors.append(f"annotation_{index}_event_group")
        if annotation.get("relationship_hint") not in ANNOTATION_RELATIONSHIP_VALUES:
            errors.append(f"annotation_{index}_relationship_hint")
        if annotation.get("source_hint") not in ANNOTATION_SOURCE_HINT_VALUES:
            errors.append(f"annotation_{index}_source_hint")
        if not str(annotation.get("reviewed_at", "")).strip():
            errors.append(f"annotation_{index}_reviewed_at")

    diagnostics = diagnostics_payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        errors.append("diagnostics_list")
        diagnostics = []
    diagnostic_ids = {
        str(row.get("item_id", ""))
        for row in diagnostics
        if isinstance(row, dict)
    }
    if diagnostic_ids != known_item_ids or len(diagnostics) != len(raw_items):
        errors.append("diagnostics_item_coverage")
    required_diagnostic_fields = {
        "item_id", "source_gate_eligible", "source_gate_reason", "selector_score",
        "selector_category", "exclusion_reasons", "selector_eligible", "selected_after_caps",
        "displaced_by_cap",
    }
    for index, row in enumerate(diagnostics):
        if not isinstance(row, dict) or not required_diagnostic_fields <= set(row):
            errors.append(f"diagnostic_{index}_fields")

    if not (run_dir / "comparison.md").read_text(encoding="utf-8").strip():
        errors.append("comparison_empty")
    return errors


def assert_valid_business_today_run(run_dir: Path) -> None:
    errors = validate_business_today_run(run_dir)
    if errors:
        raise ValueError("BusinessToday Day-1 validation failed: " + ", ".join(errors))


def run_business_today_day1(
    output_root: Path,
    run_id: str | None = None,
    baseline_ref: str | None = None,
    feed_url: str = DAY1_FEED_URL,
    fetcher: Callable[[str], Any] | None = None,
    now: datetime | None = None,
) -> Path:
    resolved_fetcher = fetcher or fetch_raw_rss
    retrieved = now or datetime.now(MYT)
    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=MYT)
    retrieved = retrieved.astimezone(MYT)
    # The timestamp is already normalized to MYT above; keep the default id
    # filesystem-safe instead of appending the `+0800` timezone suffix.
    resolved_run_id = run_id or retrieved.strftime("%Y%m%dT%H%M%S%f")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", resolved_run_id):
        raise ValueError("run_id must be 1-128 characters using only letters, digits, dot, underscore, or hyphen.")
    run_dir = output_root / resolved_run_id
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    try:
        baseline, selector = baseline_snapshot(baseline_ref or default_baseline_ref())
        candidate_result = resolved_fetcher(feed_url)
        if not candidate_result.ok or not candidate_result.data:
            raise RuntimeError(f"BusinessToday RSS fetch failed: {candidate_result.error}")
        candidate_content_type = str(getattr(candidate_result, "content_type", ""))
        if "html" in candidate_content_type.lower():
            raise RuntimeError(
                f"BusinessToday endpoint returned HTML instead of RSS/XML: {candidate_content_type}"
            )
        retrieved_at = retrieved.isoformat()
        raw_items, bozo, parse_warning = parse_raw_candidate_items(
            candidate_result.data,
            feed_url,
            retrieved_at,
        )
        if not raw_items:
            raise RuntimeError(f"BusinessToday RSS contained no parseable item elements: {parse_warning}")

        baseline_feed_health, baseline_items = collect_baseline_items(baseline, selector, resolved_fetcher)
        candidate_items, candidate_item_ids = candidate_selector_items(raw_items, selector)
        diagnostics, selector_summary = build_selector_diagnostics(
            raw_items,
            candidate_items,
            candidate_item_ids,
            baseline_items,
            selector,
            retrieved,
        )

        manifest = {
            "schema_version": DAY1_SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "source_id": DAY1_SOURCE_ID,
            "feed_url": feed_url,
            "retrieved_at": retrieved_at,
            "http_status": str(getattr(candidate_result, "status", "")),
            "content_type": candidate_content_type,
            "fetch_method": str(getattr(candidate_result, "method", "")),
            "response_sha256": sha256_bytes(candidate_result.data),
            "item_count": len(raw_items),
            "rss_parse_warning": parse_warning if bozo else "",
            "baseline": baseline,
        }
        raw_payload = {
            "schema_version": DAY1_SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "source_id": DAY1_SOURCE_ID,
            "items": raw_items,
        }
        annotation_payload = {
            "schema_version": DAY1_SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "allowed_values": {
                "manual_relevance": sorted(ANNOTATION_RELEVANCE_VALUES),
                "relationship_hint": sorted(ANNOTATION_RELATIONSHIP_VALUES),
                "source_hint": sorted(ANNOTATION_SOURCE_HINT_VALUES),
            },
            "required_fields": [
                "item_id", "manual_relevance", "event_group", "relationship_hint",
                "source_hint", "review_note", "reviewed_at",
            ],
            "annotations": [],
        }
        diagnostics_payload = {
            "schema_version": DAY1_SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "baseline_feed_health": baseline_feed_health,
            "selection_summary": selector_summary,
            "diagnostics": diagnostics,
        }
        comparison = render_day1_comparison(
            manifest,
            diagnostics,
            selector_summary,
            baseline_feed_health,
        )

        atomic_write_bytes(run_dir / "response.xml", candidate_result.data)
        atomic_write_json(run_dir / "raw_manifest.json", manifest)
        atomic_write_json(run_dir / "raw_items.json", raw_payload)
        atomic_write_json(run_dir / "annotations.json", annotation_payload)
        atomic_write_json(run_dir / "selector_diagnostics.json", diagnostics_payload)
        atomic_write_bytes(run_dir / "comparison.md", comparison.encode("utf-8"))
        assert_valid_business_today_run(run_dir)
    except Exception:
        shutil.rmtree(run_dir)
        raise
    return run_dir


def main() -> int:
    args = parse_args()
    if args.validate_business_today_run:
        run_dir = Path(args.validate_business_today_run)
        errors = validate_business_today_run(run_dir)
        if errors:
            print("BusinessToday Day-1 validation: FAIL")
            for error in errors:
                print(f"- {error}")
            return 1
        print("BusinessToday Day-1 validation: PASS")
        print(f"run directory: {run_dir}")
        return 0

    if args.business_today_day1:
        try:
            run_dir = run_business_today_day1(
                Path(args.day1_output_root),
                run_id=args.run_id,
                baseline_ref=args.baseline_ref,
                feed_url=args.business_today_feed_url,
            )
        except (FileExistsError, RuntimeError, ValueError) as exc:
            print("BusinessToday Day-1 validation: FAIL", file=sys.stderr)
            print(f"reason: {exc}", file=sys.stderr)
            return 1
        manifest = load_json_object(run_dir / "raw_manifest.json")
        print("BusinessToday Day-1 validation: PASS")
        print(f"run directory: {run_dir}")
        print(f"raw items: {manifest['item_count']}")
        print(f"response sha256: {manifest['response_sha256']}")
        return 0

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
