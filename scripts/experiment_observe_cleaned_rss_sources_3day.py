#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        build_payload,
        compare_source_sets,
        load_config,
        render_memo,
        write_json,
        write_text,
    )
except ModuleNotFoundError:
    from scripts.experiment_compare_rss_source_sets import (
        DEFAULT_CONFIG,
        MYT,
        build_payload,
        compare_source_sets,
        load_config,
        render_memo,
        write_json,
        write_text,
    )


DEFAULT_OUTPUT_DIR = "/tmp/malaysia_rss_phase2f3a"
DEFAULT_PER_FEED_LIMIT = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one day of the Phase 2F.3A cleaned RSS candidate-set observation."
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


def summarize_feed(feed: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": feed["id"],
        "name": feed["name"],
        "enabled": feed["enabled"],
        "skipped": feed["skipped"],
        "fetched_count": feed["fetched_count"],
        "bozo": feed["bozo"],
        "error": feed["error"],
        "role": feed["role"],
        "priority": feed["priority"],
    }


def item_counts_by_feed(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        feed_id = item.get("feed_id", "")
        if not feed_id:
            continue
        counts[feed_id] = counts.get(feed_id, 0) + 1
    return dict(sorted(counts.items()))


def cleaned_set_pass(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    expansion = payload["sets"].get("english_expansion_set", {})
    counts = expansion.get("counts", {})
    feeds = expansion.get("feeds", [])
    items = expansion.get("items", [])
    expected_disabled = {"bernama_english", "the_edge_malaysia", "harian_metro_mutakhir"}
    expected_enabled = {"malay_mail_malaysia", "malay_mail_money", "imoney_articles"}

    if counts.get("feeds_enabled") != 3:
        errors.append(f"english_expansion_set feeds_enabled={counts.get('feeds_enabled')}, expected 3")
    if counts.get("disabled_feeds") != 3:
        errors.append(f"english_expansion_set disabled_feeds={counts.get('disabled_feeds')}, expected 3")
    if counts.get("bozo_feeds") != 0:
        errors.append(f"english_expansion_set bozo_feeds={counts.get('bozo_feeds')}, expected 0")
    if counts.get("error_feeds") != 0:
        errors.append(f"english_expansion_set error_feeds={counts.get('error_feeds')}, expected 0")

    by_id = {feed["id"]: feed for feed in feeds}
    for feed_id in expected_disabled:
        feed = by_id.get(feed_id)
        if not feed or feed.get("enabled") or not feed.get("skipped"):
            errors.append(f"{feed_id} should be disabled and skipped")
    for feed_id in expected_enabled:
        feed = by_id.get(feed_id)
        if not feed or not feed.get("enabled") or feed.get("skipped"):
            errors.append(f"{feed_id} should be enabled and fetched")

    observed_item_feeds = {item.get("feed_id") for item in items}
    unexpected_item_feeds = observed_item_feeds - expected_enabled
    if unexpected_item_feeds:
        errors.append(f"unexpected expansion item feeds: {sorted(unexpected_item_feeds)}")

    return not errors, errors


def build_observation_entry(date: str, payload: dict[str, Any], json_path: Path, memo_path: Path) -> dict[str, Any]:
    passed, errors = cleaned_set_pass(payload)
    sets: dict[str, Any] = {}
    for set_name, set_payload in payload["sets"].items():
        sets[set_name] = {
            "counts": set_payload["counts"],
            "feed_health": [summarize_feed(feed) for feed in set_payload["feeds"]],
            "item_counts_by_feed": item_counts_by_feed(set_payload["items"]),
        }

    return {
        "date": date,
        "generated_at": payload["generated_at"],
        "json_output": str(json_path),
        "memo_output": str(memo_path),
        "pass": passed,
        "pass_errors": errors,
        "sets": sets,
        "set_diff_summary": {
            "only_in_current_set": len(payload["set_diff"].get("only_in_current_set", [])),
            "only_in_english_expansion_set": len(payload["set_diff"].get("only_in_english_expansion_set", [])),
            "shared_urls": len(payload["set_diff"].get("shared_urls", [])),
            "duplicate_url_count_between_sets": payload["set_diff"].get("duplicate_url_count_between_sets", 0),
            "per_feed_count_deltas": payload["set_diff"].get("per_feed_count_deltas", []),
        },
    }


def read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "phase2f.3a", "updated_at": "", "runs": []}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("runs"), list):
        raise ValueError(f"Invalid observation index: {path}")
    return loaded


def update_index(index_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    index = read_index(index_path)
    runs = [run for run in index["runs"] if run.get("date") != entry["date"]]
    runs.append(entry)
    runs.sort(key=lambda run: run.get("date", ""))
    index["schema_version"] = "phase2f.3a"
    index["updated_at"] = datetime.now(MYT).isoformat()
    index["runs"] = runs
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def main() -> int:
    args = parse_args()
    if args.per_feed_limit < 1:
        raise SystemExit("--per-feed-limit must be 1 or greater.")

    date = observation_date(args.date)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"rss_source_set_comparison_{date}.json"
    memo_path = output_dir / f"rss_source_set_comparison_memo_{date}.md"
    index_path = output_dir / "observation_index.json"

    config = load_config(args.config)
    comparison = compare_source_sets(config["source_sets"], args.per_feed_limit)
    payload = build_payload(config, comparison, args.per_feed_limit)
    write_json(str(json_path), payload)
    write_text(str(memo_path), render_memo(payload))
    entry = build_observation_entry(date, payload, json_path, memo_path)
    index = update_index(index_path, entry)

    print(f"written JSON: {json_path}")
    print(f"written memo: {memo_path}")
    print(f"updated index: {index_path}")
    print(f"observation date: {date}")
    print(f"cleaned set pass: {entry['pass']}")
    if entry["pass_errors"]:
        for error in entry["pass_errors"]:
            print(f"- {error}")
    print(f"indexed runs: {len(index['runs'])}")
    return 0 if entry["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
