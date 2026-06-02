# Phase 2G: Paul Tan Production Adoption

## Summary

Phase 2G adopts Paul Tan into the daily production Malaysia RSS summary by enabling the existing `--include-paul-tan` workflow path.

This is the explicit workflow adoption phase. Paul Tan remains behind the Phase 2F.9 source-specific gate, `review` and `reject` gate decisions stay excluded, and the Paul Tan source cap remains `1`.

## Why This Phase Exists

Phase 2F.10 confirmed the gate and cap worked:

- baseline selected items: `9`;
- opt-in selected items: `10`;
- Paul Tan selected items: `1`;
- failed sources: none;
- selected Paul Tan item: `Biodiesel B15 rollout begins June 1 – gov’t says no issue with compatibility; here’s what car brands say`.

Phase 2F.10 also found a display blocker: the Paul Tan item rendered with raw English RSS text, generic life-impact wording, and WordPress feed boilerplate.

Phase 2G fixes that blocker with Paul Tan-specific display cleanup only.

## What Changed

Production workflow:

- `.github/workflows/malaysia-rss-summary.yml` now passes `--include-paul-tan` to `scripts/malaysia_rss_summary.py`;
- existing commit/push behavior is unchanged.

RSS script:

- Paul Tan remains source-gated;
- Paul Tan remains capped at `1`;
- Paul Tan WordPress boilerplate such as `The post ... appeared first on Paul Tan's Automotive News` is stripped from Paul Tan display output;
- accepted Paul Tan fuel/transport items get Paul Tan-specific Japanese summary branches.

## Display Scope

Japanese display cleanup was intentionally not broadened globally.

The new cleanup is scoped to Paul Tan items only:

- B15, RON95, diesel, fuel subsidy;
- LRT, MRT, Rapid KL, KTMB, public transport;
- JPJ, licence, road tax, inspection, summons;
- road closure, toll, RFID, SmartTAG, traffic enforcement;
- clear safety recall or owner-action items.

Existing non-Paul Tan summary branches are not globally normalized by this phase.

## Lowyat.NET

Lowyat.NET remains out of production.

It is not part of Phase 2G and remains only a possible separate `digital_life_watch` observation candidate.

## Verification

Required checks:

```bash
python3.12 -m py_compile scripts/malaysia_rss_summary.py
python3.12 scripts/malaysia_rss_summary.py --self-test
```

Local baseline:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --output /tmp/malaysia_phase2g_baseline.md \
  --json-output /tmp/malaysia_phase2g_baseline.json
```

Local production rehearsal:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --output /tmp/malaysia_phase2g_paul_tan.md \
  --json-output /tmp/malaysia_phase2g_paul_tan.json
```

Expected:

- baseline has `0` Paul Tan selected items;
- opt-in has at most `1` Paul Tan selected item;
- selected Paul Tan item has Paul Tan-specific Japanese display text where matched;
- Paul Tan boilerplate does not appear in Markdown or selected JSON summaries;
- no Lowyat.NET production reference exists.

