#!/usr/bin/env python3
"""Build non-public weekly-recovery and Friday-preflight evidence.

Recovery records deliberately do not replace immutable weekly artifacts.  They
preserve the actual observation times when GitHub Actions scheduling prevents
the normal Friday 17:00 MYT coverage contract from being met.
"""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from meta_ads_tracker_contract import ContractError, load_and_validate_source_config
from meta_ads_tracker_publication import (
    KUALA_LUMPUR,
    _enabled_sources,
    _validate_event_semantics,
    _validate_schema,
    canonical_hash,
    load_json,
    parse_timestamp,
    validate_candidate,
    write_json,
)


RECOVERY_SCHEMA_VERSION = "meta-ads-tracker-weekly-recovery/v1"
PREFLIGHT_SCHEMA_VERSION = "meta-ads-tracker-weekly-preflight/v1"
RECOVERY_SCHEMA = Path(__file__).resolve().parent / "schemas/meta_ads_tracker_weekly_recovery.schema.json"
DEFAULT_CANDIDATES_DIRECTORY = Path("data/meta_ads_tracker_candidates")
DEFAULT_RECOVERY_DIRECTORY = Path("data/meta_ads_tracker_weekly_recovery")


def _week(cutoff_at: datetime) -> dict[str, str]:
    local_date = cutoff_at.astimezone(KUALA_LUMPUR).date()
    start = local_date - timedelta(days=local_date.weekday())
    end = start + timedelta(days=6)
    return {"startDate": start.isoformat(), "endDate": end.isoformat(), "label": f"{start.isoformat()}〜{end.isoformat()}"}


def cutoff_for_date(value: str) -> datetime:
    try:
        local_date = date.fromisoformat(value)
    except ValueError as error:
        raise ContractError("--cutoff-date must be YYYY-MM-DD") from error
    if local_date.weekday() != 4:
        raise ContractError("--cutoff-date must be a Friday in Asia/Kuala_Lumpur")
    return datetime.combine(local_date, time(17, 0), KUALA_LUMPUR).astimezone(timezone.utc)


def latest_friday_cutoff(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ContractError("preflight now must include a timezone")
    local_now = now.astimezone(KUALA_LUMPUR)
    days_since_friday = (local_now.weekday() - 4) % 7
    local_friday = local_now.date() - timedelta(days=days_since_friday)
    return datetime.combine(local_friday, time(17, 0), KUALA_LUMPUR).astimezone(timezone.utc)


def _week_dates(cutoff_at: datetime) -> list[date]:
    start = cutoff_at.astimezone(KUALA_LUMPUR).date()
    start -= timedelta(days=start.weekday())
    return [start + timedelta(days=offset) for offset in range(5)]


def _candidate_time(file_name: str, candidate: Any) -> datetime:
    if not isinstance(candidate, dict):
        raise ContractError(f"{file_name} must contain a JSON object")
    return parse_timestamp(candidate.get("generatedAt"), f"{file_name}.generatedAt").astimezone(timezone.utc)


def _select_week_candidates(
    candidates: list[tuple[str, Any]],
    cutoff_at: datetime,
) -> list[tuple[str, dict[str, Any], datetime]]:
    required_dates = set(_week_dates(cutoff_at))
    selected: list[tuple[str, dict[str, Any], datetime]] = []
    seen_hashes: set[str] = set()
    for file_name, candidate in candidates:
        candidate_time = _candidate_time(file_name, candidate)
        if candidate_time.astimezone(KUALA_LUMPUR).date() not in required_dates:
            continue
        try:
            validated = validate_candidate(candidate)
        except ContractError as error:
            raise ContractError(f"invalid recovery candidate {file_name}: {error}") from error
        candidate_hash = validated["candidateHash"]
        if candidate_hash in seen_hashes:
            continue
        seen_hashes.add(candidate_hash)
        selected.append((file_name, validated, candidate_time))
    return sorted(selected, key=lambda entry: (entry[2], entry[0]))


def _coverage_by_date(
    selected: list[tuple[str, dict[str, Any], datetime]],
    cutoff_at: datetime,
) -> dict[date, list[tuple[str, dict[str, Any], datetime]]]:
    coverage = {day: [] for day in _week_dates(cutoff_at)}
    for entry in selected:
        local_date = entry[2].astimezone(KUALA_LUMPUR).date()
        coverage[local_date].append(entry)
    return coverage


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ContractError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_preflight(candidates: list[tuple[str, Any]], now: datetime) -> dict[str, Any]:
    generated_at = now.astimezone(timezone.utc).replace(microsecond=0)
    cutoff_at = latest_friday_cutoff(generated_at)
    selected = _select_week_candidates(candidates, cutoff_at)
    boundary = min(generated_at, cutoff_at)
    coverage = _coverage_by_date(selected, cutoff_at)
    entries: list[dict[str, Any]] = []
    missing_dates: list[str] = []
    for day in _week_dates(cutoff_at):
        eligible = [entry for entry in coverage[day] if entry[2] <= boundary]
        if not eligible:
            missing_dates.append(day.isoformat())
        entries.append(
            {
                "date": day.isoformat(),
                "eligibleCandidateCount": len(eligible),
                "latestEligibleCandidateAt": _timestamp(eligible[-1][2]) if eligible else None,
            }
        )
    backup_start = cutoff_at - timedelta(hours=1)
    friday = _week_dates(cutoff_at)[-1].isoformat()
    backup_eligible = (
        backup_start <= generated_at < cutoff_at
        and missing_dates == [friday]
    )
    if not missing_dates:
        status = "ready"
    elif backup_eligible:
        status = "backup_recommended"
    elif generated_at >= cutoff_at:
        status = "window_closed"
    else:
        status = "recovery_required"
    report = {
        "schemaVersion": PREFLIGHT_SCHEMA_VERSION,
        "preflightHash": "",
        "generatedAt": _timestamp(generated_at),
        "cutoffAt": _timestamp(cutoff_at),
        "week": _week(cutoff_at),
        "status": status,
        "coverage": entries,
        "missingDates": missing_dates,
        "backup": {
            "windowStartsAt": _timestamp(backup_start),
            "windowEndsAt": _timestamp(cutoff_at),
            "eligible": backup_eligible,
        },
    }
    report["preflightHash"] = canonical_hash(report, "preflightHash")
    validate_preflight(report)
    return report


def validate_preflight(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "schemaVersion", "preflightHash", "generatedAt", "cutoffAt", "week", "status", "coverage", "missingDates", "backup"
    }:
        raise ContractError("weekly preflight has an invalid shape")
    if payload["schemaVersion"] != PREFLIGHT_SCHEMA_VERSION:
        raise ContractError("weekly preflight schemaVersion is unsupported")
    if canonical_hash(payload, "preflightHash") != payload["preflightHash"]:
        raise ContractError("weekly preflight hash does not match canonical content")
    generated_at = parse_timestamp(payload["generatedAt"], "weekly preflight.generatedAt")
    cutoff_at = parse_timestamp(payload["cutoffAt"], "weekly preflight.cutoffAt")
    if cutoff_at.astimezone(KUALA_LUMPUR).weekday() != 4 or cutoff_at.astimezone(KUALA_LUMPUR).time() != time(17, 0):
        raise ContractError("weekly preflight.cutoffAt must be Friday 17:00 Asia/Kuala_Lumpur")
    if payload["week"] != _week(cutoff_at):
        raise ContractError("weekly preflight.week must match cutoffAt")
    if payload["status"] not in {"ready", "backup_recommended", "recovery_required", "window_closed"}:
        raise ContractError("weekly preflight.status is unsupported")
    if not isinstance(payload["coverage"], list) or len(payload["coverage"]) != 5:
        raise ContractError("weekly preflight.coverage must contain Monday-Friday exactly once")
    expected_dates = [day.isoformat() for day in _week_dates(cutoff_at)]
    missing: list[str] = []
    for index, (entry, expected_date) in enumerate(zip(payload["coverage"], expected_dates)):
        if not isinstance(entry, dict) or set(entry) != {"date", "eligibleCandidateCount", "latestEligibleCandidateAt"}:
            raise ContractError(f"weekly preflight.coverage[{index}] has an invalid shape")
        if entry["date"] != expected_date:
            raise ContractError("weekly preflight.coverage dates must be ordered Monday-Friday")
        count = entry["eligibleCandidateCount"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ContractError("weekly preflight eligibleCandidateCount must be a non-negative integer")
        latest = entry["latestEligibleCandidateAt"]
        if count == 0:
            if latest is not None:
                raise ContractError("weekly preflight empty coverage must not have a latest timestamp")
            missing.append(expected_date)
        else:
            if parse_timestamp(latest, "weekly preflight latestEligibleCandidateAt") > min(generated_at, cutoff_at):
                raise ContractError("weekly preflight latest candidate exceeds its coverage boundary")
    if payload["missingDates"] != missing:
        raise ContractError("weekly preflight.missingDates must match coverage")
    backup = payload["backup"]
    if not isinstance(backup, dict) or set(backup) != {"windowStartsAt", "windowEndsAt", "eligible"}:
        raise ContractError("weekly preflight.backup has an invalid shape")
    if parse_timestamp(backup["windowStartsAt"], "weekly preflight backup.windowStartsAt") != cutoff_at - timedelta(hours=1):
        raise ContractError("weekly preflight backup window must start one hour before cutoff")
    if parse_timestamp(backup["windowEndsAt"], "weekly preflight backup.windowEndsAt") != cutoff_at:
        raise ContractError("weekly preflight backup window must end at cutoff")
    expected_eligible = (
        cutoff_at - timedelta(hours=1) <= generated_at < cutoff_at
        and missing == [expected_dates[-1]]
    )
    if not isinstance(backup["eligible"], bool) or backup["eligible"] != expected_eligible:
        raise ContractError("weekly preflight backup eligibility does not match coverage and time window")
    return payload


def build_recovery(
    candidates: list[tuple[str, Any]],
    cutoff_at: datetime,
    generated_at: datetime,
) -> dict[str, Any]:
    cutoff_at = cutoff_at.astimezone(timezone.utc).replace(microsecond=0)
    generated_at = generated_at.astimezone(timezone.utc).replace(microsecond=0)
    if cutoff_at.astimezone(KUALA_LUMPUR).weekday() != 4 or cutoff_at.astimezone(KUALA_LUMPUR).time() != time(17, 0):
        raise ContractError("recovery cutoffAt must be Friday 17:00 Asia/Kuala_Lumpur")
    selected = _select_week_candidates(candidates, cutoff_at)
    coverage = _coverage_by_date(selected, cutoff_at)
    missing_all = [day.isoformat() for day, entries in coverage.items() if not entries]
    if missing_all:
        raise ContractError(f"weekly recovery requires at least one candidate for every Monday-Friday date; missing {missing_all}")
    missing_pre_cutoff = [
        day.isoformat()
        for day, entries in coverage.items()
        if not any(candidate_time <= cutoff_at for _name, _candidate, candidate_time in entries)
    ]
    if not missing_pre_cutoff:
        raise ContractError("weekly recovery is not allowed when normal pre-cutoff coverage is complete")

    references: list[dict[str, str]] = []
    events: dict[str, dict[str, Any]] = {}
    for file_name, candidate, candidate_time in selected:
        references.append(
            {
                "fileName": file_name,
                "candidateHash": candidate["candidateHash"],
                "generatedAt": candidate["generatedAt"],
                "timing": "on_time" if candidate_time <= cutoff_at else "late",
            }
        )
        for event in candidate["items"]:
            recovered_event = deepcopy(event)
            recovered_event["originCandidateHash"] = candidate["candidateHash"]
            existing = events.get(event["eventId"])
            if existing is not None:
                excluded = {"detectedAt", "originCandidateHash"}
                if {key: value for key, value in existing.items() if key not in excluded} != {
                    key: value for key, value in recovered_event.items() if key not in excluded
                }:
                    raise ContractError(f"recovery eventId collision with different content: {event['eventId']}")
                continue
            events[event["eventId"]] = recovered_event
    recovery = {
        "schemaVersion": RECOVERY_SCHEMA_VERSION,
        "recoveryHash": "",
        "generatedAt": _timestamp(generated_at),
        "cutoffAt": _timestamp(cutoff_at),
        "week": _week(cutoff_at),
        "recoveryReason": "missing_pre_cutoff_coverage",
        "missingPreCutoffDates": missing_pre_cutoff,
        "candidateRefs": references,
        "items": sorted(events.values(), key=lambda event: (event["detectedAt"], event["eventId"])),
        "publicationEligible": False,
        "requiresHumanDisposition": True,
    }
    recovery["recoveryHash"] = canonical_hash(recovery, "recoveryHash")
    validate_recovery(recovery)
    return recovery


def validate_recovery(payload: Any) -> dict[str, Any]:
    _validate_schema(payload, RECOVERY_SCHEMA, "weekly recovery")
    assert isinstance(payload, dict)
    if canonical_hash(payload, "recoveryHash") != payload["recoveryHash"]:
        raise ContractError("weekly recovery hash does not match canonical content")
    cutoff_at = parse_timestamp(payload["cutoffAt"], "weekly recovery.cutoffAt")
    if cutoff_at.astimezone(KUALA_LUMPUR).weekday() != 4 or cutoff_at.astimezone(KUALA_LUMPUR).time() != time(17, 0):
        raise ContractError("weekly recovery.cutoffAt must be Friday 17:00 Asia/Kuala_Lumpur")
    generated_at = parse_timestamp(payload["generatedAt"], "weekly recovery.generatedAt")
    if generated_at < cutoff_at:
        raise ContractError("weekly recovery.generatedAt cannot precede cutoffAt")
    if payload["week"] != _week(cutoff_at):
        raise ContractError("weekly recovery.week must match cutoffAt")
    if payload["publicationEligible"] is not False or payload["requiresHumanDisposition"] is not True:
        raise ContractError("weekly recovery must remain non-public and require human disposition")
    week_dates = _week_dates(cutoff_at)
    refs_by_hash: dict[str, dict[str, Any]] = {}
    covered: dict[date, list[dict[str, Any]]] = {day: [] for day in week_dates}
    for index, reference in enumerate(payload["candidateRefs"]):
        candidate_hash = reference["candidateHash"]
        if candidate_hash in refs_by_hash:
            raise ContractError("weekly recovery candidateRefs must not repeat a candidateHash")
        candidate_time = parse_timestamp(reference["generatedAt"], f"weekly recovery.candidateRefs[{index}].generatedAt")
        local_date = candidate_time.astimezone(KUALA_LUMPUR).date()
        if local_date not in covered:
            raise ContractError("weekly recovery candidateRefs must be Monday-Friday of its week")
        expected_timing = "on_time" if candidate_time <= cutoff_at else "late"
        if reference["timing"] != expected_timing:
            raise ContractError("weekly recovery candidate timing does not match cutoffAt")
        refs_by_hash[candidate_hash] = reference
        covered[local_date].append(reference)
    missing_all = [day.isoformat() for day, refs in covered.items() if not refs]
    if missing_all:
        raise ContractError("weekly recovery must include a candidate for every Monday-Friday date")
    expected_missing = [
        day.isoformat()
        for day, refs in covered.items()
        if not any(reference["timing"] == "on_time" for reference in refs)
    ]
    if payload["missingPreCutoffDates"] != expected_missing:
        raise ContractError("weekly recovery missingPreCutoffDates must match candidate timing")
    configured_sources = _enabled_sources(load_and_validate_source_config())
    event_ids: set[str] = set()
    for index, event in enumerate(payload["items"]):
        _validate_event_semantics(event, index, configured_sources, weekly=True)
        if event["eventId"] in event_ids:
            raise ContractError(f"duplicate recovery eventId: {event['eventId']}")
        event_ids.add(event["eventId"])
        reference = refs_by_hash.get(event["originCandidateHash"])
        if reference is None:
            raise ContractError("weekly recovery item references an unknown candidateHash")
        if event["detectedAt"] != reference["generatedAt"]:
            raise ContractError("weekly recovery item detectedAt must match its origin candidate")
    return payload


def write_immutable_recovery(path: Path, recovery: dict[str, Any]) -> None:
    validate_recovery(recovery)
    if path.exists():
        existing = validate_recovery(load_json(path))
        if existing["recoveryHash"] != recovery["recoveryHash"]:
            raise ContractError(f"immutable weekly recovery already exists with different content: {path}")
        return
    write_json(path, recovery)


def validate_recovery_directory(directory: Path) -> int:
    """Validate every recovery record already committed to a directory."""
    if not directory.exists():
        return 0
    if not directory.is_dir():
        raise ContractError(f"recovery directory is not a directory: {directory}")
    count = 0
    for path in sorted(directory.glob("*.json")):
        validate_recovery(load_json(path))
        count += 1
    return count


def _load_candidates(directory: Path) -> list[tuple[str, Any]]:
    return [(path.name, load_json(path)) for path in sorted(directory.glob("*.json"))]


def _write_output(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--candidates-dir", type=Path, default=DEFAULT_CANDIDATES_DIRECTORY)
    preflight.add_argument("--output", type=Path, required=True)
    recovery = subparsers.add_parser("recover")
    recovery.add_argument("--candidates-dir", type=Path, default=DEFAULT_CANDIDATES_DIRECTORY)
    recovery.add_argument("--output-dir", type=Path, default=DEFAULT_RECOVERY_DIRECTORY)
    recovery.add_argument("--cutoff-date", required=True)
    args = parser.parse_args()
    try:
        candidates = _load_candidates(args.candidates_dir)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if args.command == "preflight":
            report = build_preflight(candidates, now)
            _write_output(args.output, report)
            print(f"PASS: weekly preflight {report['status']} ({len(report['missingDates'])} missing dates)")
            return 0
        cutoff_at = cutoff_for_date(args.cutoff_date)
        recovery_payload = build_recovery(candidates, cutoff_at, now)
        output = args.output_dir / f"{cutoff_at.astimezone(KUALA_LUMPUR).date().isoformat()}.json"
        write_immutable_recovery(output, recovery_payload)
        print(f"PASS: created non-public weekly recovery with {len(recovery_payload['items'])} events: {output}")
        return 0
    except (ContractError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
