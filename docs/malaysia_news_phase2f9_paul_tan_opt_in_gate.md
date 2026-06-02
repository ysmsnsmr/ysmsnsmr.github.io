# Phase 2F.9: Paul Tan Opt-In Source Gate

## Summary

Phase 2F.9 adds a production-adjacent local opt-in path for Paul Tan in `scripts/malaysia_rss_summary.py`.

Paul Tan is not enabled by default. The existing daily workflow and default local command continue to use the current production RSS sources only:

- Malay Mail Malaysia;
- Malay Mail Money;
- Astro Awani National.

Paul Tan is fetched only when the local command passes:

```bash
python3.12 -B scripts/malaysia_rss_summary.py --include-paul-tan
```

## What Changed

The production RSS script now supports:

- `--include-paul-tan` local opt-in flag;
- Paul Tan RSS source appended only for opt-in runs;
- source-specific Paul Tan gate before normal selection;
- `review` and `reject` Paul Tan gate decisions excluded from selection;
- accepted Paul Tan items mapped to existing tags such as `public_transport`, `road_closure`, `jpj`, `prices`, `fuel`, and `vehicle_safety`;
- Paul Tan source cap of `1` item per output.

No workflow change was made. The daily workflow does not pass `--include-paul-tan`.

## Gate Policy

The Paul Tan gate uses only RSS metadata:

- title;
- description;
- link;
- published date.

Accepted signals include:

- public transport, LRT, MRT, Rapid KL, KTMB;
- road closures, tolls, RFID, SmartTAG, traffic enforcement;
- JPJ, licence, summons, road tax, insurance, vehicle inspection;
- petrol, diesel, RON95, fuel subsidy, `Budi Madani`;
- safety recalls or owner-affecting safety defects.

Rejected signals include:

- launches, previews, reviews, and spyshots;
- sales events, showroom promotions, model pricing, variants, and specs;
- motorsport, brand, plant, factory, or industry-capacity stories;
- ordinary vehicle wording without public-service impact.

Mixed items with unclear public-service value are treated as `review`, and `review` is excluded from production-style selection.

## Lowyat.NET

Lowyat.NET remains out of the mainline RSS path and is not connected to this implementation. It stays a separate `digital_life_watch` observation candidate only.

## Verification

Required checks:

```bash
python3.12 -m py_compile scripts/malaysia_rss_summary.py
python3.12 scripts/malaysia_rss_summary.py --self-test
```

Recommended local checks:

```bash
python3.12 -B scripts/malaysia_rss_summary.py --output /tmp/malaysia_phase2f9_baseline.md --json-output /tmp/malaysia_phase2f9_baseline.json
python3.12 -B scripts/malaysia_rss_summary.py --include-paul-tan --output /tmp/malaysia_phase2f9_paul_tan.md --json-output /tmp/malaysia_phase2f9_paul_tan.json
```

Expected:

- baseline run has no Paul Tan source;
- opt-in run may include Paul Tan only if a gated item ranks into final output;
- final output has at most `1` Paul Tan item;
- workflow, Pages output, and `news/malaysia/` remain unchanged.

