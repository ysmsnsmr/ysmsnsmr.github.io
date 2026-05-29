#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from malaysia_rss_summary import MYT, SOURCES, clean, fetch_rss, parse_date
except ModuleNotFoundError:
    from scripts.malaysia_rss_summary import MYT, SOURCES, clean, fetch_rss, parse_date


SCHEMA_VERSION = "phase2f.0"
DEFAULT_CONFIG = "config/malaysia_news_feeds_phase2f.yml"
DEFAULT_JSON_OUTPUT = "/tmp/rss_source_set_comparison.json"
DEFAULT_MEMO_OUTPUT = "/tmp/rss_source_set_comparison_memo.md"
FEED_KEYS = {"id", "name", "url", "language", "source_type", "role", "priority", "enabled"}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Phase 2F candidate Malaysia RSS source sets without changing production feeds."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--memo-output", default=DEFAULT_MEMO_OUTPUT)
    parser.add_argument("--per-feed-limit", type=int, default=50)
    return parser.parse_args()


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_key_value(text: str, line_no: int) -> tuple[str, Any]:
    if ":" not in text:
        raise ValueError(f"Unsupported YAML at line {line_no}: expected key: value.")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Unsupported YAML at line {line_no}: empty key.")
    return key, parse_scalar(value)


def load_yaml_fallback(path: Path) -> dict[str, Any]:
    source_sets: dict[str, list[dict[str, Any]]] = {}
    current_set: str | None = None
    current_feed: dict[str, Any] | None = None
    saw_root = False

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line == "source_sets:":
            saw_root = True
            continue
        if not saw_root:
            raise ValueError(f"Unsupported YAML at line {line_no}: expected source_sets root.")

        if raw_line.startswith("  ") and not raw_line.startswith("    ") and raw_line.rstrip().endswith(":"):
            current_set = raw_line.strip()[:-1]
            if not current_set:
                raise ValueError(f"Unsupported YAML at line {line_no}: empty source set name.")
            if current_set in source_sets:
                raise ValueError(f"Duplicate source set at line {line_no}: {current_set}")
            source_sets[current_set] = []
            current_feed = None
            continue

        if raw_line.startswith("    - "):
            if current_set is None:
                raise ValueError(f"Unsupported YAML at line {line_no}: feed before source set.")
            current_feed = {}
            source_sets[current_set].append(current_feed)
            key, value = parse_key_value(raw_line[6:], line_no)
            current_feed[key] = value
            continue

        if raw_line.startswith("      "):
            if current_feed is None:
                raise ValueError(f"Unsupported YAML at line {line_no}: field before feed item.")
            key, value = parse_key_value(raw_line[6:], line_no)
            current_feed[key] = value
            continue

        raise ValueError(f"Unsupported YAML at line {line_no}: {raw_line}")

    return {"source_sets": source_sets}


def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except ModuleNotFoundError:
        loaded = load_yaml_fallback(config_path)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("source_sets"), dict):
        raise ValueError("Config must contain source_sets mapping.")
    validate_config(loaded)
    return loaded


def validate_config(config: dict[str, Any]) -> None:
    source_sets = config["source_sets"]
    for set_name, feeds in source_sets.items():
        if not isinstance(set_name, str) or not isinstance(feeds, list):
            raise ValueError("Each source set must be a list of feeds.")
        for index, feed in enumerate(feeds, start=1):
            if not isinstance(feed, dict):
                raise ValueError(f"{set_name} feed {index} must be a mapping.")
            keys = set(feed)
            if keys != FEED_KEYS:
                missing = ", ".join(sorted(FEED_KEYS - keys)) or "none"
                extra = ", ".join(sorted(keys - FEED_KEYS)) or "none"
                raise ValueError(
                    f"{set_name} feed {index} must contain exactly {sorted(FEED_KEYS)}; "
                    f"missing: {missing}; extra: {extra}"
                )
            if not isinstance(feed["enabled"], bool):
                raise ValueError(f"{set_name} feed {index} enabled must be true or false.")


def current_sources_snapshot() -> list[dict[str, str]]:
    return [{"source": source, "feed": feed, "url": url} for source, feed, url in SOURCES]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if local_name(child.tag) == name:
            return clean("".join(child.itertext()))
    return ""


def lenient_xml(data: bytes) -> ET.Element:
    text = data.strip().decode("utf-8", "ignore").strip()
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    return ET.fromstring(text.encode("utf-8"))


def parse_feed_items(data: bytes, per_feed_limit: int) -> tuple[list[dict[str, str]], bool, str]:
    bozo = False
    bozo_exception = ""
    try:
        root = ET.fromstring(data.strip())
    except Exception as exc:
        bozo = True
        bozo_exception = f"{type(exc).__name__}: {exc}"
        try:
            root = lenient_xml(data)
        except Exception as lenient_exc:
            return [], True, f"{bozo_exception}; lenient failed: {type(lenient_exc).__name__}: {lenient_exc}"

    rss_nodes = [node for node in root.iter() if local_name(node.tag) == "item"]
    if not rss_nodes:
        return [], True, bozo_exception or "no RSS item elements found"

    items: list[dict[str, str]] = []
    for node in rss_nodes[:per_feed_limit]:
        pub_raw = child_text(node, "pubDate")
        parsed_date = parse_date(pub_raw)
        items.append(
            {
                "title": child_text(node, "title"),
                "description": child_text(node, "description"),
                "link": child_text(node, "link"),
                "published": parsed_date.isoformat() if parsed_date else pub_raw,
            }
        )
    return items, bozo, bozo_exception


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    normalized = urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            urllib.parse.urlencode(sorted(query), doseq=True),
            "",
        )
    )
    return normalized


def duplicate_count(items: list[dict[str, Any]]) -> int:
    urls = [item["normalized_link"] for item in items if item.get("normalized_link")]
    return len(urls) - len(set(urls))


def collect_feed(set_name: str, feed: dict[str, Any], per_feed_limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_result = {
        "set": set_name,
        **feed,
        "fetched_count": 0,
        "error": "",
        "bozo": False,
        "bozo_exception": "",
        "elapsed_ms": 0,
        "status": "",
        "content_type": "",
        "method": "",
        "skipped": False,
    }
    if not feed["enabled"]:
        base_result["error"] = "disabled"
        base_result["skipped"] = True
        return base_result, []

    started = time.monotonic()
    fetch_result = fetch_rss(feed["url"])
    base_result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    base_result["status"] = fetch_result.status
    base_result["content_type"] = fetch_result.content_type
    base_result["method"] = fetch_result.method

    if not fetch_result.ok:
        base_result["error"] = fetch_result.error
        return base_result, []

    parsed_items, bozo, bozo_exception = parse_feed_items(fetch_result.data, per_feed_limit)
    base_result["bozo"] = bozo
    base_result["bozo_exception"] = bozo_exception
    base_result["fetched_count"] = len(parsed_items)
    if bozo and not parsed_items:
        base_result["error"] = bozo_exception

    items = []
    for item in parsed_items:
        link = item["link"]
        items.append(
            {
                "source_set": set_name,
                "feed_id": feed["id"],
                "title": item["title"],
                "description": item["description"],
                "link": link,
                "normalized_link": normalize_url(link) if link else "",
                "published": item["published"],
                "source": feed["name"],
                "language": feed["language"],
                "role": feed["role"],
                "priority": feed["priority"],
            }
        )
    return base_result, items


def compare_source_sets(source_sets: dict[str, list[dict[str, Any]]], per_feed_limit: int) -> dict[str, Any]:
    set_results: dict[str, Any] = {}
    all_feed_results: list[dict[str, Any]] = []

    for set_name, feeds in source_sets.items():
        feed_results: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        for feed in feeds:
            feed_result, feed_items = collect_feed(set_name, feed, per_feed_limit)
            feed_results.append(feed_result)
            items.extend(feed_items)
        set_results[set_name] = {
            "feeds": feed_results,
            "items": items,
            "counts": {
                "feeds_total": len(feeds),
                "feeds_enabled": sum(1 for feed in feeds if feed["enabled"]),
                "feeds_fetched": sum(1 for result in feed_results if result["enabled"] and not result["error"]),
                "items": len(items),
                "duplicate_url_count": duplicate_count(items),
                "bozo_feeds": sum(1 for result in feed_results if result["bozo"]),
                "error_feeds": sum(1 for result in feed_results if result["error"] and not result["skipped"]),
                "disabled_feeds": sum(1 for result in feed_results if result["skipped"]),
            },
        }
        all_feed_results.extend(feed_results)

    return {
        "sets": set_results,
        "feeds": all_feed_results,
        "set_diff": build_set_diff(set_results),
    }


def urls_for_set(set_payload: dict[str, Any]) -> set[str]:
    return {item["normalized_link"] for item in set_payload["items"] if item.get("normalized_link")}


def count_by_feed(items: list[dict[str, Any]]) -> Counter[str]:
    return Counter(item["feed_id"] for item in items)


def build_set_diff(set_results: dict[str, Any]) -> dict[str, Any]:
    if "current_set" not in set_results or "english_expansion_set" not in set_results:
        return {"error": "current_set and english_expansion_set are required for diff."}

    current_urls = urls_for_set(set_results["current_set"])
    expansion_urls = urls_for_set(set_results["english_expansion_set"])
    current_counts = count_by_feed(set_results["current_set"]["items"])
    expansion_counts = count_by_feed(set_results["english_expansion_set"]["items"])
    feed_ids = sorted(set(current_counts) | set(expansion_counts))

    return {
        "only_in_current_set": sorted(current_urls - expansion_urls),
        "only_in_english_expansion_set": sorted(expansion_urls - current_urls),
        "shared_urls": sorted(current_urls & expansion_urls),
        "duplicate_url_count_between_sets": len(current_urls & expansion_urls),
        "per_feed_count_deltas": [
            {
                "feed_id": feed_id,
                "current_set": current_counts.get(feed_id, 0),
                "english_expansion_set": expansion_counts.get(feed_id, 0),
                "delta": expansion_counts.get(feed_id, 0) - current_counts.get(feed_id, 0),
            }
            for feed_id in feed_ids
        ],
    }


def build_payload(config: dict[str, Any], comparison: dict[str, Any], per_feed_limit: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(MYT).isoformat(),
        "per_feed_limit": per_feed_limit,
        "production_sources_snapshot": current_sources_snapshot(),
        "source_sets": config["source_sets"],
        **comparison,
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return lines


def render_memo(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2F.0 RSSソースセット比較メモ",
        "",
        f"- 生成時刻: {payload['generated_at']}",
        f"- per-feed limit: {payload['per_feed_limit']}",
        "- Groq API: 未使用",
        "- 本文取得: 未使用",
        "",
        "## セット別サマリー",
    ]
    summary_rows = []
    for set_name, set_payload in payload["sets"].items():
        counts = set_payload["counts"]
        summary_rows.append(
            [
                set_name,
                counts["feeds_enabled"],
                counts["items"],
                counts["duplicate_url_count"],
                counts["bozo_feeds"],
                counts["error_feeds"],
                counts["disabled_feeds"],
            ]
        )
    lines.extend(
        markdown_table(
            ["set", "enabled feeds", "items", "duplicate URLs", "bozo feeds", "error feeds", "disabled"],
            summary_rows,
        )
    )

    lines.extend(["", "## Feed Health"])
    feed_rows = []
    for feed in payload["feeds"]:
        feed_rows.append(
            [
                feed["set"],
                feed["id"],
                feed["name"],
                feed["enabled"],
                feed["fetched_count"],
                feed["bozo"],
                feed["error"] or "-",
                feed["elapsed_ms"],
            ]
        )
    lines.extend(markdown_table(["set", "id", "name", "enabled", "items", "bozo", "error", "ms"], feed_rows))

    diff = payload["set_diff"]
    lines.extend(
        [
            "",
            "## current_set vs english_expansion_set",
            "",
            f"- current_setのみ: {len(diff.get('only_in_current_set', []))}",
            f"- english_expansion_setのみ: {len(diff.get('only_in_english_expansion_set', []))}",
            f"- 共通URL: {len(diff.get('shared_urls', []))}",
            f"- セット間duplicate URL count: {diff.get('duplicate_url_count_between_sets', 0)}",
            "",
            "### Feed Count Delta",
        ]
    )
    delta_rows = [
        [item["feed_id"], item["current_set"], item["english_expansion_set"], item["delta"]]
        for item in diff.get("per_feed_count_deltas", [])
    ]
    lines.extend(markdown_table(["feed_id", "current", "expansion", "delta"], delta_rows))

    lines.extend(["", "## Sample Titles"])
    for set_name, set_payload in payload["sets"].items():
        lines.extend(["", f"### {set_name}"])
        by_feed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in set_payload["items"]:
            by_feed[item["source"]].append(item)
        for source, items in by_feed.items():
            lines.extend(["", f"#### {source}"])
            for item in items[:5]:
                title = item["title"] or "(no title)"
                published = item["published"] or "-"
                lines.append(f"- {published} - {title}")

    disabled = [feed for feed in payload["feeds"] if feed["skipped"]]
    lines.extend(["", "## Disabled Feeds"])
    if disabled:
        for feed in disabled:
            lines.append(f"- {feed['set']} / {feed['id']} / {feed['name']} / {feed['url']}")
    else:
        lines.append("- なし")

    return "\n".join(lines) + "\n"


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str, value: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(value, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.per_feed_limit < 1:
        raise SystemExit("--per-feed-limit must be 1 or greater.")

    config = load_config(args.config)
    comparison = compare_source_sets(config["source_sets"], args.per_feed_limit)
    payload = build_payload(config, comparison, args.per_feed_limit)
    write_json(args.json_output, payload)
    write_text(args.memo_output, render_memo(payload))
    print(f"written JSON: {args.json_output}")
    print(f"written memo: {args.memo_output}")
    for set_name, set_payload in payload["sets"].items():
        counts = set_payload["counts"]
        print(
            f"{set_name}: items={counts['items']} duplicate_urls={counts['duplicate_url_count']} "
            f"bozo_feeds={counts['bozo_feeds']} error_feeds={counts['error_feeds']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
