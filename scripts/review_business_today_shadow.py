#!/usr/bin/env python3
"""Export, import, and summarize human review for a BusinessToday shadow run."""

import argparse
import csv
import io
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from experiment_observe_rss_candidate_backlog import (
        ANNOTATION_RELATIONSHIP_VALUES,
        ANNOTATION_RELEVANCE_VALUES,
        ANNOTATION_SOURCE_HINT_VALUES,
        MYT,
        assert_valid_business_today_run,
    )
except ModuleNotFoundError:
    from scripts.experiment_observe_rss_candidate_backlog import (
        ANNOTATION_RELATIONSHIP_VALUES,
        ANNOTATION_RELEVANCE_VALUES,
        ANNOTATION_SOURCE_HINT_VALUES,
        MYT,
        assert_valid_business_today_run,
    )


REVIEW_SCHEMA_VERSION = "malaysia-news-source-shadow/review/v1"
QUEUE_FIELDS = [
    "item_id",
    "published_at",
    "title",
    "article_url",
    "selector_score",
    "selector_category",
    "selector_eligible",
    "selected_after_caps",
    "displaced_by_cap",
    "exclusion_reasons",
    "manual_relevance",
    "event_group",
    "relationship_hint",
    "source_hint",
    "review_note",
    "reviewed_at",
]
ANNOTATION_FIELDS = [
    "item_id",
    "manual_relevance",
    "event_group",
    "relationship_hint",
    "source_hint",
    "review_note",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review a BusinessToday shadow run through an editable CSV queue."
    )
    parser.add_argument("--run-dir", required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--export-csv", metavar="PATH")
    action.add_argument("--import-csv", metavar="PATH")
    parser.add_argument("--write-summary", metavar="PATH")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must be a JSON object.")
    return loaded


def load_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    raw_payload = load_json(run_dir / "raw_items.json")
    annotation_payload = load_json(run_dir / "annotations.json")
    diagnostics_payload = load_json(run_dir / "selector_diagnostics.json")
    raw_items = raw_payload.get("items")
    annotations = annotation_payload.get("annotations")
    diagnostics = diagnostics_payload.get("diagnostics")
    if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
        raise ValueError("raw_items.json must contain an items list.")
    if not isinstance(annotations, list) or not all(isinstance(item, dict) for item in annotations):
        raise ValueError("annotations.json must contain an annotations list.")
    if not isinstance(diagnostics, list) or not all(isinstance(item, dict) for item in diagnostics):
        raise ValueError("selector_diagnostics.json must contain a diagnostics list.")
    annotation_by_id = {str(item.get("item_id", "")): item for item in annotations}
    diagnostic_by_id = {str(item.get("item_id", "")): item for item in diagnostics}
    raw_ids = {str(item.get("item_id", "")) for item in raw_items}
    if "" in raw_ids or set(diagnostic_by_id) != raw_ids:
        raise ValueError("Raw items and selector diagnostics must have the same non-empty item IDs.")
    if not set(annotation_by_id) <= raw_ids:
        raise ValueError("annotations.json contains an unknown item ID.")
    return raw_items, annotation_by_id, diagnostic_by_id, annotation_payload


def atomic_write_bytes(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def queue_rows(run_dir: Path) -> list[dict[str, str]]:
    raw_items, annotations, diagnostics, _ = load_run(run_dir)
    rows: list[dict[str, str]] = []
    for raw in raw_items:
        item_id = str(raw["item_id"])
        annotation = annotations.get(item_id, {})
        diagnostic = diagnostics[item_id]
        rows.append(
            {
                "item_id": item_id,
                "published_at": str(raw.get("published_at", "")),
                "title": str(raw.get("title", "")),
                "article_url": str(raw.get("article_url", "")),
                "selector_score": str(diagnostic.get("selector_score", "")),
                "selector_category": str(diagnostic.get("selector_category", "")),
                "selector_eligible": str(bool(diagnostic.get("selector_eligible"))).lower(),
                "selected_after_caps": str(bool(diagnostic.get("selected_after_caps"))).lower(),
                "displaced_by_cap": str(bool(diagnostic.get("displaced_by_cap"))).lower(),
                "exclusion_reasons": " | ".join(str(value) for value in diagnostic.get("exclusion_reasons", [])),
                "manual_relevance": str(annotation.get("manual_relevance", "")),
                "event_group": str(annotation.get("event_group", "")),
                "relationship_hint": str(annotation.get("relationship_hint", "")),
                "source_hint": str(annotation.get("source_hint", "")),
                "review_note": str(annotation.get("review_note", "")),
                "reviewed_at": str(annotation.get("reviewed_at", "")),
            }
        )
    return rows


def export_queue_csv(run_dir: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=QUEUE_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(queue_rows(run_dir))
    atomic_write_bytes(output_path, buffer.getvalue().encode("utf-8"))
    return len(queue_rows(run_dir))


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(QUEUE_FIELDS) <= set(reader.fieldnames):
            raise ValueError("Review CSV is missing one or more required queue columns.")
        return [{field: (row.get(field) or "").strip() for field in QUEUE_FIELDS} for row in reader]


def review_annotation(row: dict[str, str], reviewed_at: str) -> dict[str, str] | None:
    relevance = row["manual_relevance"].lower()
    annotation_values = [row[field] for field in ANNOTATION_FIELDS if field != "item_id"]
    if not relevance:
        if any(annotation_values):
            raise ValueError(f"{row['item_id']}: manual_relevance is required when review fields are present.")
        return None
    if relevance not in ANNOTATION_RELEVANCE_VALUES:
        raise ValueError(f"{row['item_id']}: manual_relevance must be useful, unclear, or noise.")
    event_group = row["event_group"]
    if relevance in {"useful", "unclear"} and not event_group:
        raise ValueError(f"{row['item_id']}: useful and unclear require event_group.")
    relationship_hint = row["relationship_hint"] or "unknown"
    source_hint = row["source_hint"] or "unknown"
    if relationship_hint not in ANNOTATION_RELATIONSHIP_VALUES:
        raise ValueError(f"{row['item_id']}: invalid relationship_hint.")
    if source_hint not in ANNOTATION_SOURCE_HINT_VALUES:
        raise ValueError(f"{row['item_id']}: invalid source_hint.")
    return {
        "item_id": row["item_id"],
        "manual_relevance": relevance,
        "event_group": event_group,
        "relationship_hint": relationship_hint,
        "source_hint": source_hint,
        "review_note": row["review_note"],
        "reviewed_at": row["reviewed_at"] or reviewed_at,
    }


def import_queue_csv(run_dir: Path, input_path: Path, now: datetime | None = None) -> tuple[int, int]:
    raw_items, existing, _diagnostics, annotation_payload = load_run(run_dir)
    known_ids = {str(item["item_id"]) for item in raw_items}
    rows = csv_rows(input_path)
    seen_ids: set[str] = set()
    reviewed_at = (now or datetime.now(MYT)).astimezone(MYT).isoformat()
    merged = dict(existing)
    updates = 0
    for row in rows:
        item_id = row["item_id"]
        if item_id not in known_ids:
            raise ValueError(f"Unknown item_id in review CSV: {item_id}")
        if item_id in seen_ids:
            raise ValueError(f"Duplicate item_id in review CSV: {item_id}")
        seen_ids.add(item_id)
        annotation = review_annotation(row, reviewed_at)
        if annotation is None:
            continue
        if merged.get(item_id) != annotation:
            updates += 1
        merged[item_id] = annotation

    new_payload = dict(annotation_payload)
    new_payload["annotations"] = [merged[item_id] for item_id in sorted(merged)]
    annotation_path = run_dir / "annotations.json"
    previous_bytes = annotation_path.read_bytes()
    atomic_write_json(annotation_path, new_payload)
    try:
        assert_valid_business_today_run(run_dir)
    except Exception:
        atomic_write_bytes(annotation_path, previous_bytes)
        raise
    return updates, len(merged)


def percentage(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a"
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})"


def review_summary(run_dir: Path) -> dict[str, Any]:
    raw_items, annotations, diagnostics, _ = load_run(run_dir)
    relevance_counts = Counter(str(annotation.get("manual_relevance", "")) for annotation in annotations.values())
    annotated_ids = set(annotations)
    useful_ids = {
        item_id for item_id, annotation in annotations.items()
        if annotation.get("manual_relevance") == "useful"
    }
    selector_eligible_ids = {
        item_id for item_id, diagnostic in diagnostics.items()
        if diagnostic.get("selector_eligible")
    }
    useful_eligible = useful_ids & selector_eligible_ids
    reviewed_eligible = annotated_ids & selector_eligible_ids
    event_groups = {
        str(annotation.get("event_group", ""))
        for annotation in annotations.values()
        if annotation.get("manual_relevance") in {"useful", "unclear"} and annotation.get("event_group")
    }
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "raw_items": len(raw_items),
        "annotated_items": len(annotated_ids),
        "pending_items": len(raw_items) - len(annotated_ids),
        "relevance_counts": dict(sorted(relevance_counts.items())),
        "reviewed_event_groups": len(event_groups),
        "noise_rate": percentage(relevance_counts["noise"], len(annotated_ids)),
        "selector_recall_useful": percentage(len(useful_eligible), len(useful_ids)),
        "selector_precision_reviewed": percentage(len(useful_eligible), len(reviewed_eligible)),
        "selected_after_caps_useful": percentage(
            sum(1 for item_id in useful_ids if diagnostics[item_id].get("selected_after_caps")),
            len(useful_ids),
        ),
    }


def render_summary(summary: dict[str, Any]) -> str:
    counts = summary["relevance_counts"]
    lines = [
        "# BusinessToday Shadow Review Summary",
        "",
        f"- raw items: {summary['raw_items']}",
        f"- annotated: {summary['annotated_items']}",
        f"- pending: {summary['pending_items']}",
        f"- useful: {counts.get('useful', 0)}",
        f"- unclear: {counts.get('unclear', 0)}",
        f"- noise: {counts.get('noise', 0)}",
        f"- reviewed event groups: {summary['reviewed_event_groups']}",
        f"- noise rate: {summary['noise_rate']}",
        f"- selector recall (useful): {summary['selector_recall_useful']}",
        f"- selector precision (reviewed): {summary['selector_precision_reviewed']}",
        f"- useful selected after caps: {summary['selected_after_caps_useful']}",
        "",
        "Metrics use only manually annotated rows; finish all rows before making the 7-day decision.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir)
    try:
        if args.export_csv:
            count = export_queue_csv(run_dir, Path(args.export_csv))
            print(f"Exported review queue: {args.export_csv} ({count} rows)")
        if args.import_csv:
            updates, annotations = import_queue_csv(run_dir, Path(args.import_csv))
            print(f"Imported review queue: updates={updates}, annotations={annotations}")
        summary = render_summary(review_summary(run_dir))
        if args.write_summary:
            atomic_write_bytes(Path(args.write_summary), summary.encode("utf-8"))
            print(f"Wrote review summary: {args.write_summary}")
        else:
            print(summary, end="")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"BusinessToday review: FAIL\nreason: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
