#!/usr/bin/env python3
"""Assemble an immutable Friday-cutoff weekly artifact from successful daily candidates."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from meta_ads_tracker_contract import ContractError
from meta_ads_tracker_publication import (
    KUALA_LUMPUR,
    WEEKLY_SCHEMA_VERSION,
    canonical_hash,
    load_json,
    parse_timestamp,
    validate_candidate,
    validate_weekly_candidate,
    write_json,
)


def logical_cutoff(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ContractError("assembler now must include a timezone")
    local_now = now.astimezone(KUALA_LUMPUR)
    days_since_friday = (local_now.weekday() - 4) % 7
    cutoff_date = local_now.date() - timedelta(days=days_since_friday)
    cutoff = datetime.combine(cutoff_date, time(17, 0), KUALA_LUMPUR)
    if cutoff > local_now:
        cutoff -= timedelta(days=7)
    return cutoff.astimezone(timezone.utc)


def _week(cutoff_at: datetime) -> dict[str, str]:
    local_date = cutoff_at.astimezone(KUALA_LUMPUR).date()
    start = local_date - timedelta(days=local_date.weekday())
    end = start + timedelta(days=6)
    return {"startDate": start.isoformat(), "endDate": end.isoformat(), "label": f"{start.isoformat()}〜{end.isoformat()}"}


def assemble_weekly(
    candidates: list[tuple[str, dict[str, Any]]],
    cutoff_at: datetime,
    generated_at: datetime,
) -> dict[str, Any]:
    if cutoff_at.tzinfo is None or generated_at.tzinfo is None:
        raise ContractError("weekly timestamps must include a timezone")
    cutoff_utc = cutoff_at.astimezone(timezone.utc).replace(microsecond=0)
    local_cutoff = cutoff_utc.astimezone(KUALA_LUMPUR)
    if local_cutoff.weekday() != 4 or local_cutoff.time() != time(17, 0):
        raise ContractError("cutoffAt must be Friday 17:00 Asia/Kuala_Lumpur")
    week = _week(cutoff_utc)
    start_date = datetime.fromisoformat(week["startDate"]).date()
    required_dates = {start_date + timedelta(days=offset) for offset in range(5)}

    selected: list[tuple[str, dict[str, Any], datetime]] = []
    covered_dates: set[Any] = set()
    seen_hashes: set[str] = set()
    for file_name, candidate in candidates:
        validate_candidate(candidate)
        candidate_time = parse_timestamp(candidate["generatedAt"], f"{file_name}.generatedAt")
        local_date = candidate_time.astimezone(KUALA_LUMPUR).date()
        if local_date not in required_dates or candidate_time > cutoff_utc:
            continue
        if candidate["candidateHash"] in seen_hashes:
            continue
        seen_hashes.add(candidate["candidateHash"])
        covered_dates.add(local_date)
        selected.append((file_name, candidate, candidate_time))
    missing = sorted(required_dates - covered_dates)
    if missing:
        raise ContractError(f"weekly assembly requires a successful candidate for every Monday-Friday date; missing {missing}")

    selected.sort(key=lambda entry: (entry[2], entry[0]))
    candidate_refs: list[dict[str, str]] = []
    events: dict[str, dict[str, Any]] = {}
    for file_name, candidate, _candidate_time in selected:
        candidate_refs.append(
            {
                "fileName": file_name,
                "candidateHash": candidate["candidateHash"],
                "generatedAt": candidate["generatedAt"],
            }
        )
        for event in candidate["items"]:
            weekly_event = deepcopy(event)
            weekly_event["originCandidateHash"] = candidate["candidateHash"]
            existing = events.get(event["eventId"])
            if existing is not None:
                excluded = {"detectedAt", "originCandidateHash"}
                existing_content = {key: value for key, value in existing.items() if key not in excluded}
                incoming_content = {key: value for key, value in weekly_event.items() if key not in excluded}
                if existing_content != incoming_content:
                    raise ContractError(f"eventId collision with different content: {event['eventId']}")
                continue
            events[event["eventId"]] = weekly_event

    weekly = {
        "schemaVersion": WEEKLY_SCHEMA_VERSION,
        "weeklyHash": "",
        "generatedAt": generated_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cutoffAt": cutoff_utc.isoformat().replace("+00:00", "Z"),
        "week": week,
        "candidateRefs": candidate_refs,
        "items": sorted(events.values(), key=lambda event: (event["detectedAt"], event["eventId"])),
    }
    weekly["weeklyHash"] = canonical_hash(weekly, "weeklyHash")
    validate_weekly_candidate(weekly)
    return weekly


def write_immutable_weekly(path: Path, weekly: dict[str, Any]) -> None:
    validate_weekly_candidate(weekly)
    if path.exists():
        existing = load_json(path)
        validate_weekly_candidate(existing)
        if existing["weeklyHash"] != weekly["weeklyHash"]:
            raise ContractError(f"immutable weekly artifact already exists with different content: {path}")
        return
    write_json(path, weekly)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-dir", type=Path, default=Path("data/meta_ads_tracker_candidates"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/meta_ads_tracker_weekly"))
    parser.add_argument("--cutoff-at", help="Logical Friday cutoff ISO timestamp; defaults to the latest Friday 17:00 MYT")
    args = parser.parse_args()
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        cutoff = parse_timestamp(args.cutoff_at, "--cutoff-at") if args.cutoff_at else logical_cutoff(now)
        output = args.output_dir / f"{cutoff.astimezone(KUALA_LUMPUR).date().isoformat()}.json"
        if output.exists():
            existing = validate_weekly_candidate(load_json(output))
            if parse_timestamp(existing["cutoffAt"], "existing weekly.cutoffAt") != cutoff.astimezone(timezone.utc):
                raise ContractError(f"existing weekly artifact has a different logical cutoff: {output}")
            print(f"PASS: immutable weekly artifact already exists: {output}")
            return 0
        candidates = [(path.name, load_json(path)) for path in sorted(args.candidates_dir.glob("*.json"))]
        weekly = assemble_weekly(candidates, cutoff, now)
        write_immutable_weekly(output, weekly)
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: assembled {len(weekly['items'])} events into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
