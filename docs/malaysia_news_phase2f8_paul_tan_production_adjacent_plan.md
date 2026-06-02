# Phase 2F.8: Paul Tan Production-Adjacent Integration Plan

## Summary

Phase 2F.8 records a production-adjacent plan for Paul Tan. It translates the Phase 2F.6 source-specific gate design and Phase 2F.7 local test results into a future integration path.

This phase is planning only. It does not add Paul Tan to the live daily workflow, production RSS list, Pages output, Groq behavior, article body fetching, `scripts/malaysia_rss_summary.py`, `config/malaysia_news_feeds_phase2f.yml`, or `news/malaysia/`.

The safe path is:

- local opt-in first;
- source-specific Paul Tan gate before normal selection;
- source cap of `1`;
- no Lowyat.NET mainline promotion.

## Phase 2F.7 Evidence

Phase 2F.7 live local run used only Paul Tan RSS metadata on `2026-06-02`.

Observed result:

- feed: `https://paultan.org/feed/`;
- fetched items: `20`;
- bozo: `false`;
- error: none;
- accepted: `8`;
- rejected: `10`;
- review: `2`;
- source cap: `1`;
- would select count: `1`;
- would select title: `RON95 subsidy adjustment is last resort: PMO adviser`;
- Lowyat.NET: `digital_life_watch`, not fetched.

The result supports a cautious local opt-in path. It does not justify workflow or production enablement yet.

## Future Phase 2F.9 Integration Shape

Phase 2F.9 should make Paul Tan available only through an explicit local CLI flag, such as:

```bash
python3.12 -B scripts/malaysia_rss_summary.py --include-paul-tan
```

The default command and the existing daily workflow should continue to use the current production RSS sources only.

Future implementation in `scripts/malaysia_rss_summary.py` should:

- keep the existing `SOURCES` default unchanged unless `--include-paul-tan` is passed;
- append Paul Tan only for the opt-in local run;
- add source-specific gate helpers scoped to `item.source == "Paul Tan"` or `item.feed == "Paul Tan"`;
- reject Paul Tan items before normal candidate selection unless the gate decision is `accept`;
- treat `review` as excluded from production-style selection;
- add a per-source cap map with Paul Tan capped at `1`;
- preserve existing behavior for Malay Mail, Malay Mail Money, and Astro Awani.

The daily workflow must not pass `--include-paul-tan` until a later explicit approval phase.

## Gate Placement

The Paul Tan gate should run before normal selection, close to the existing exclusion path. A future implementation should prefer a small helper such as `paul_tan_gate_decision(item)` and then call it from `should_exclude_item(item)` or an equivalent pre-selection filter.

This keeps automotive-specific noise out of global keyword rules and avoids changing how existing feeds are scored.

Eligibility must be based only on RSS metadata:

- title;
- description;
- link;
- published date.

Do not use Groq or article body fetching to decide whether a Paul Tan item is eligible.

## Accepted Mapping

Accepted Paul Tan items should reuse existing tags and categories rather than adding a broad automotive category:

- public transport, LRT, MRT, Rapid KL, KTMB: `public_transport`;
- JPJ, licence, road tax, inspection, summons: `jpj`;
- tolls, road closures, RFID, SmartTAG, traffic enforcement: `road_closure`;
- petrol, diesel, RON95, fuel subsidy, `Budi Madani`: existing prices or cost/fuel-related logic;
- safety recalls or owner-affecting safety defects: only include when owner action or driver safety impact is clear.

Examples of accepted Paul Tan content:

- LRT service disruption;
- JPJ process or enforcement change;
- RON95 or diesel subsidy item;
- toll or road-closure item;
- recall requiring owner awareness or action.

Examples of rejected Paul Tan content:

- vehicle launches;
- reviews and previews;
- spyshots;
- showroom or sales events;
- model pricing, variants, and specs with no public-service angle;
- motorsport;
- brand, plant, or industry-capacity stories with no direct user impact.

## Source Cap

Paul Tan should have a lower cap than general feeds.

Recommended cap:

- `Paul Tan`: max `1` item per output.

The cap should apply after the source-specific gate and before final output. This prevents a transport-heavy day from crowding out broader Malaysia sources while still allowing one high-value mobility item.

## Lowyat.NET Position

Lowyat.NET is not part of the Paul Tan integration path.

Keep Lowyat.NET:

- out of production RSS;
- out of the cleaned mainline set;
- separate as `digital_life_watch` observation only, if continued.

Any future Lowyat.NET work should be designed separately around public tech-life topics such as telco, public internet, MyKad, payments, Touch 'n Go, fuel subsidy technology, public transport technology, or government digital services.

## Future Phase 2F.9 Acceptance Tests

Before any workflow adoption, Phase 2F.9 should pass:

```bash
python3.12 scripts/malaysia_rss_summary.py --self-test
```

It should also verify:

- baseline local run without `--include-paul-tan` remains unchanged in source set behavior;
- opt-in local run with `--include-paul-tan` fetches Paul Tan;
- Paul Tan launch, review, sales, and model-pricing noise is excluded;
- Paul Tan LRT, JPJ, RON95, diesel, toll, road, and clear recall items can pass;
- `review` items are not selected;
- final output includes no more than `1` Paul Tan item;
- selected JSON exposes enough reasons/tags to audit why a Paul Tan item passed.

Protected diff check for Phase 2F.8:

```bash
git diff -- scripts/malaysia_rss_summary.py .github/workflows scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result: no diff from Phase 2F.8.

## Decision

Paul Tan is eligible for a future production-adjacent local opt-in experiment, not for immediate workflow adoption.

The next safe phase is Phase 2F.9: implement an opt-in local flag and source-specific gate in the production script, with default behavior unchanged and workflow untouched.

