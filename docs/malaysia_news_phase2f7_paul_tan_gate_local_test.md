# Phase 2F.7: Paul Tan Source-Specific Gate Local Test

## Summary

Phase 2F.7 adds a local-only implementation test for the Paul Tan source-specific gate designed in Phase 2F.6. The purpose is to verify whether RSS metadata alone can separate practical Malaysia transport or driver-impact items from ordinary automotive noise before any production adoption.

This phase does not add Paul Tan to production RSS. It does not promote Lowyat.NET. It does not change GitHub Actions, Pages, Groq, article body fetching, `scripts/malaysia_rss_summary.py`, `config/malaysia_news_feeds_phase2f.yml`, or `news/malaysia/`.

## Manual Commands

Run syntax check:

```bash
python3.12 -m py_compile scripts/experiment_test_paul_tan_source_gate.py
```

Run fixture self-test:

```bash
python3.12 -B scripts/experiment_test_paul_tan_source_gate.py --self-test
```

Run live local observation:

```bash
python3.12 -B scripts/experiment_test_paul_tan_source_gate.py --date 20260602
```

Default outputs:

- `/tmp/malaysia_rss_phase2f7/paul_tan_source_gate_20260602.json`
- `/tmp/malaysia_rss_phase2f7/paul_tan_source_gate_memo_20260602.md`
- `/tmp/malaysia_rss_phase2f7/observation_index.json`

Daily snapshots stay in `/tmp` and are not tracked in the repository.

## Gate Rules

The helper fetches only Paul Tan:

```yaml
id: paul_tan
name: Paul Tan
url: https://paultan.org/feed/
language: en
source_type: automotive_transport
role: transport_driver_impact_candidate
priority: medium
enabled: true
```

It uses only RSS metadata:

- title;
- description;
- link;
- published.

Each item receives:

- `gate_decision`: `accept`, `reject`, or `review`;
- `positive_signals`;
- `noise_signals`;
- `matched_signal_groups`;
- `gate_reason`.

Accepted signals are limited to practical Malaysia mobility impact:

- LRT, MRT, Rapid KL, KTMB, public transport, rail, bus, service disruption;
- road closures, highway, toll, RFID, SmartTAG, traffic enforcement;
- JPJ, licence, summons, road tax, insurance, vehicle inspection;
- petrol, diesel, RON95, fuel subsidy, `Budi Madani`;
- safety recalls or owner-affecting safety defects.

Rejected signals are ordinary automotive noise:

- launches, previews, reviews, spyshots, and test drives;
- sales events, showroom promotions, model pricing, variants, and specs;
- motorsport, brand, plant, factory, or industry-capacity stories;
- vehicle-type wording with no public-service angle.

Mixed cases should be accepted only when the public-service signal is clear from RSS metadata. Otherwise they should be marked `review` or rejected.

## Source Cap Simulation

The helper does not select production articles. It only simulates a future cap:

- accepted items are ranked by signal strength and recency;
- `would_select_items` is capped at `1`.

This cap is intentionally lower than general feeds because Paul Tan is a niche source with high automotive-noise risk.

## Lowyat.NET Decision

Lowyat.NET is not fetched in Phase 2F.7. It remains separate `digital_life_watch` observation only.

Useful Lowyat.NET topics, if investigated later, would be public tech-life items such as telco, public internet, MyKad, payments, Touch 'n Go, fuel subsidy technology, and government digital services. That path should be designed separately and should not block Paul Tan's transport-specific gate.

## Acceptance Criteria

The Phase 2F.7 helper is considered usable for local observation if:

- fixture self-test passes;
- live run writes JSON, memo, and index under `/tmp/malaysia_rss_phase2f7/`;
- Paul Tan is the only fetched feed;
- Lowyat.NET is listed only as `digital_life_watch` and is not fetched;
- output records accept/reject/review counts and source-cap simulation;
- protected production files have no diff.

Protected diff check:

```bash
git diff -- scripts/malaysia_rss_summary.py .github/workflows scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result: no diff from Phase 2F.7.

