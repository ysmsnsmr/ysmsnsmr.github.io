#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from experiment_compare_rss_source_sets import MYT, collect_feed
except ModuleNotFoundError:
    from scripts.experiment_compare_rss_source_sets import MYT, collect_feed


SCHEMA_VERSION = "phase2f.7"
DEFAULT_OUTPUT_DIR = "/tmp/malaysia_rss_phase2f7"
DEFAULT_PER_FEED_LIMIT = 50
SOURCE_CAP = 1

PAUL_TAN_FEED: dict[str, Any] = {
    "id": "paul_tan",
    "name": "Paul Tan",
    "url": "https://paultan.org/feed/",
    "language": "en",
    "source_type": "automotive_transport",
    "role": "transport_driver_impact_candidate",
    "priority": "medium",
    "enabled": True,
}

LOWYAT_WATCH = {
    "id": "lowyat_net",
    "name": "Lowyat.NET",
    "role": "digital_life_watch",
    "status": "not_fetched_in_phase2f7",
}

POSITIVE_SIGNAL_GROUPS: dict[str, set[str]] = {
    "public_transport": {
        "bus",
        "ktmb",
        "lrt",
        "mrt",
        "public transport",
        "rail",
        "rapid kl",
        "service disruption",
        "service update",
        "train",
    },
    "road_toll": {
        "highway",
        "lane closure",
        "rfid",
        "road closure",
        "road closures",
        "road users",
        "smart tag",
        "smarttag",
        "toll",
        "traffic diversion",
        "traffic enforcement",
    },
    "driver_obligations": {
        "insurance",
        "jpj",
        "licence",
        "license",
        "puspakom",
        "road tax",
        "saman",
        "summons",
        "vehicle inspection",
    },
    "fuel_subsidy": {
        "b15",
        "biodiesel",
        "budi madani",
        "budi95",
        "diesel",
        "fuel subsidy",
        "petrol",
        "ron95",
        "subsidy",
    },
    "safety_recall": {
        "airbag",
        "brake",
        "recall",
        "safety defect",
        "safety recall",
        "vehicle recall",
    },
}

NOISE_SIGNAL_GROUPS: dict[str, set[str]] = {
    "launch_review": {
        "first drive",
        "launch",
        "launched",
        "preview",
        "review",
        "spied",
        "spyshot",
        "test drive",
    },
    "sales_pricing": {
        "drive sale",
        "mega drive sale",
        "priced at",
        "pricing",
        "pre-owned",
        "promotion",
        "rebate",
        "sale",
        "sales event",
        "showroom",
        "specs",
        "variant",
        "variants",
    },
    "enthusiast_business": {
        "brand",
        "cbu",
        "ckd",
        "concept",
        "factory",
        "motorsport",
        "plant",
        "production capacity",
        "teaser",
    },
    "ordinary_vehicle": {
        "ev",
        "hatchback",
        "mpv",
        "pickup",
        "sedan",
        "suv",
    },
}

PUBLIC_SERVICE_GROUPS = {
    "public_transport",
    "road_toll",
    "driver_obligations",
    "fuel_subsidy",
    "safety_recall",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-only Phase 2F.7 test for a Paul Tan source-specific RSS gate."
    )
    parser.add_argument("--date", help="Observation date in YYYYMMDD. Defaults to current Malaysia date.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-feed-limit", type=int, default=DEFAULT_PER_FEED_LIMIT)
    parser.add_argument("--self-test", action="store_true", help="Run fixture tests without fetching RSS.")
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


def phrase_matches(text: str, phrases: set[str]) -> list[str]:
    matches = []
    for phrase in phrases:
        parts = re.findall(r"[a-z0-9]+", phrase.lower())
        if not parts:
            continue
        pattern = r"\b" + r"[^a-z0-9]+".join(re.escape(part) for part in parts) + r"\b"
        if re.search(pattern, text):
            matches.append(phrase)
    return sorted(matches)


def grouped_matches(text: str, groups: dict[str, set[str]]) -> dict[str, list[str]]:
    matched = {}
    for group, phrases in groups.items():
        matches = phrase_matches(text, phrases)
        if matches:
            matched[group] = matches
    return matched


def flatten_signals(grouped: dict[str, list[str]]) -> list[str]:
    signals = []
    for matches in grouped.values():
        signals.extend(matches)
    return sorted(set(signals))


def gate_item(item: dict[str, Any]) -> dict[str, Any]:
    text = text_blob(item)
    positive_groups = grouped_matches(text, POSITIVE_SIGNAL_GROUPS)
    noise_groups = grouped_matches(text, NOISE_SIGNAL_GROUPS)
    positive_signals = flatten_signals(positive_groups)
    noise_signals = flatten_signals(noise_groups)
    positive_group_names = set(positive_groups)
    noise_group_names = set(noise_groups)

    if positive_signals and not noise_signals:
        decision = "accept"
        reason = "positive transport or driver-impact signal with no automotive-noise signal"
    elif positive_signals and noise_signals:
        if positive_group_names & PUBLIC_SERVICE_GROUPS and not (noise_group_names - {"ordinary_vehicle"}):
            decision = "accept"
            reason = "mixed item accepted because public-service signal outweighs ordinary vehicle wording"
        elif positive_group_names & {"driver_obligations", "fuel_subsidy", "safety_recall", "public_transport", "road_toll"}:
            decision = "review"
            reason = "mixed public-service and automotive-noise signals; RSS metadata needs human review"
        else:
            decision = "reject"
            reason = "mixed signals without a clear public-service group"
    elif noise_signals:
        decision = "reject"
        reason = "automotive-noise signal without transport or driver-impact signal"
    else:
        decision = "reject"
        reason = "no transport or driver-impact signal in RSS metadata"

    return {
        **item,
        "gate_decision": decision,
        "positive_signals": positive_signals,
        "noise_signals": noise_signals,
        "matched_signal_groups": {
            "positive": positive_groups,
            "noise": noise_groups,
        },
        "gate_reason": reason,
        "gate_score": len(positive_signals) * 2 + len(positive_groups) - len(noise_signals),
    }


def item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return (int(item.get("gate_score", 0)), str(item.get("published") or ""))


def selected_after_cap(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted = [item for item in items if item.get("gate_decision") == "accept"]
    return sorted(accepted, key=item_sort_key, reverse=True)[:SOURCE_CAP]


def counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = Counter(item.get("gate_decision", "unknown") for item in items)
    positive_groups = Counter()
    noise_groups = Counter()
    for item in items:
        for group in item.get("matched_signal_groups", {}).get("positive", {}):
            positive_groups[group] += 1
        for group in item.get("matched_signal_groups", {}).get("noise", {}):
            noise_groups[group] += 1
    selected = selected_after_cap(items)
    return {
        "items": len(items),
        "accepted_count": decisions.get("accept", 0),
        "rejected_count": decisions.get("reject", 0),
        "review_count": decisions.get("review", 0),
        "decision_counts": dict(sorted(decisions.items())),
        "positive_group_counts": dict(sorted(positive_groups.items())),
        "noise_group_counts": dict(sorted(noise_groups.items())),
        "source_cap": SOURCE_CAP,
        "would_select_count": len(selected),
    }


def build_payload(
    date: str,
    feed_result: dict[str, Any],
    items: list[dict[str, Any]],
    per_feed_limit: int,
) -> dict[str, Any]:
    gated_items = [gate_item(item) for item in items]
    selected = selected_after_cap(gated_items)
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_date": date,
        "generated_at": datetime.now(MYT).isoformat(),
        "per_feed_limit": per_feed_limit,
        "rss_metadata_only": True,
        "uses_groq": False,
        "fetches_article_bodies": False,
        "feed": PAUL_TAN_FEED,
        "feed_result": feed_result,
        "lowyat_net": LOWYAT_WATCH,
        "gate": {
            "source_cap": SOURCE_CAP,
            "positive_signal_groups": {key: sorted(value) for key, value in sorted(POSITIVE_SIGNAL_GROUPS.items())},
            "noise_signal_groups": {key: sorted(value) for key, value in sorted(NOISE_SIGNAL_GROUPS.items())},
        },
        "counts": counts(gated_items),
        "items": gated_items,
        "would_select_items": selected,
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return lines


def item_samples(items: list[dict[str, Any]], decision: str, limit: int = 8) -> list[str]:
    selected = [item for item in items if item.get("gate_decision") == decision][:limit]
    if not selected:
        return [f"- no `{decision}` items"]
    lines = []
    for item in selected:
        title = item.get("title") or "(no title)"
        positive = ", ".join(item.get("positive_signals", [])) or "-"
        noise = ", ".join(item.get("noise_signals", [])) or "-"
        lines.append(f"- {item.get('published') or '-'} - {title}")
        lines.append(f"  - positive: {positive}; noise: {noise}")
        lines.append(f"  - reason: {item.get('gate_reason')}")
    return lines


def render_memo(payload: dict[str, Any]) -> str:
    feed_result = payload["feed_result"]
    count_payload = payload["counts"]
    lines = [
        "# Phase 2F.7 Paul Tan source-specific gate local test",
        "",
        f"- 観察日: {payload['observation_date']}",
        f"- 生成時刻: {payload['generated_at']}",
        f"- feed: {payload['feed']['name']} ({payload['feed']['url']})",
        "- RSS metadata only: yes",
        "- Groq API: not used",
        "- article body fetching: not used",
        "- production RSS / workflow / Pages: not changed",
        "- Lowyat.NET: not fetched; remains `digital_life_watch`",
        "",
        "## Feed Health",
        "",
    ]
    lines.extend(
        markdown_table(
            ["fetched", "bozo", "error", "status", "content_type", "elapsed_ms"],
            [
                [
                    feed_result.get("fetched_count", 0),
                    feed_result.get("bozo", False),
                    feed_result.get("error") or "-",
                    feed_result.get("status") or "-",
                    feed_result.get("content_type") or "-",
                    feed_result.get("elapsed_ms", 0),
                ]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Gate Summary",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["items", "accept", "reject", "review", "source cap", "would select"],
            [
                [
                    count_payload["items"],
                    count_payload["accepted_count"],
                    count_payload["rejected_count"],
                    count_payload["review_count"],
                    count_payload["source_cap"],
                    count_payload["would_select_count"],
                ]
            ],
        )
    )
    lines.extend(
        [
            "",
            f"- decision counts: `{count_payload['decision_counts']}`",
            f"- positive group counts: `{count_payload['positive_group_counts']}`",
            f"- noise group counts: `{count_payload['noise_group_counts']}`",
            "",
            "## Would Select After Cap",
            "",
        ]
    )
    if payload["would_select_items"]:
        for item in payload["would_select_items"]:
            lines.append(f"- {item.get('published') or '-'} - {item.get('title') or '(no title)'}")
            lines.append(f"  - link: {item.get('link') or '-'}")
            lines.append(f"  - reason: {item.get('gate_reason')}")
    else:
        lines.append("- no items would be selected")

    lines.extend(["", "## Accepted Samples", ""])
    lines.extend(item_samples(payload["items"], "accept"))
    lines.extend(["", "## Review Samples", ""])
    lines.extend(item_samples(payload["items"], "review"))
    lines.extend(["", "## Rejected Samples", ""])
    lines.extend(item_samples(payload["items"], "reject"))
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This helper tests the gate only; it does not select production articles.",
            "- A future adoption phase should keep Paul Tan behind this kind of source-specific gate.",
            "- Lowyat.NET remains separate from this path as `digital_life_watch`.",
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
        "feed_result": payload["feed_result"],
        "counts": payload["counts"],
        "would_select_titles": [item.get("title", "") for item in payload["would_select_items"]],
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


def fixture_item(title: str, description: str = "") -> dict[str, Any]:
    return {
        "source_set": "self_test",
        "feed_id": "paul_tan",
        "title": title,
        "description": description,
        "link": "https://paultan.org/example",
        "normalized_link": "https://paultan.org/example",
        "published": "2026-06-02T08:00:00+08:00",
        "source": "Paul Tan",
        "language": "en",
        "role": "transport_driver_impact_candidate",
        "priority": "medium",
    }


def run_self_test() -> int:
    cases = [
        (
            "positive transport item",
            fixture_item("Rapid KL LRT service disruption affects commuters this morning"),
            "accept",
        ),
        (
            "noise launch item",
            fixture_item("New SUV launched in Malaysia, priced at RM120k"),
            "reject",
        ),
        (
            "mixed recall item",
            fixture_item("Honda SUV recall in Malaysia over airbag safety defect"),
            "accept",
        ),
        (
            "mixed model pricing item",
            fixture_item("New EV variant pricing and specs announced for Malaysia"),
            "reject",
        ),
        (
            "lowyat absent",
            {"feed_id": "lowyat_net", "title": "Touch 'n Go app update", "description": ""},
            "reject",
        ),
    ]
    failures = []
    for name, item, expected in cases:
        actual = gate_item(item)["gate_decision"]
        if actual != expected:
            failures.append(f"{name}: expected {expected}, got {actual}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"self-test ok: {len(cases)} cases")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()
    if args.per_feed_limit < 1:
        raise SystemExit("--per-feed-limit must be 1 or greater.")

    date = observation_date(args.date)
    output_dir = Path(args.output_dir)
    json_path = output_dir / f"paul_tan_source_gate_{date}.json"
    memo_path = output_dir / f"paul_tan_source_gate_memo_{date}.md"
    index_path = output_dir / "observation_index.json"

    feed_result, items = collect_feed("phase2f7_paul_tan_gate", PAUL_TAN_FEED, args.per_feed_limit)
    payload = build_payload(date, feed_result, items, args.per_feed_limit)
    write_json(json_path, payload)
    write_text(memo_path, render_memo(payload))
    index = update_index(index_path, payload, json_path, memo_path)

    print(f"written JSON: {json_path}")
    print(f"written memo: {memo_path}")
    print(f"updated index: {index_path}")
    print(f"observation date: {date}")
    print(
        "gate: "
        f"items={payload['counts']['items']} "
        f"accept={payload['counts']['accepted_count']} "
        f"reject={payload['counts']['rejected_count']} "
        f"review={payload['counts']['review_count']} "
        f"would_select={payload['counts']['would_select_count']}"
    )
    print(f"indexed runs: {len(index['runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
