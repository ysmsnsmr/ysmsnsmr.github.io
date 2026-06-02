# Phase 2F.10: Paul Tan Opt-In Local Rehearsal

## Summary

Phase 2F.10 rehearsed the Phase 2F.9 Paul Tan opt-in path locally. The goal was to confirm that the default production-style run remains unchanged, while `--include-paul-tan` adds Paul Tan only through the source-specific gate and source cap.

This phase does not change GitHub Actions, Pages output, `news/malaysia/`, Groq behavior, article body fetching, or Phase 2F config files.

## Commands

Baseline:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --output /tmp/malaysia_phase2f10_baseline_20260602.md \
  --json-output /tmp/malaysia_phase2f10_baseline_20260602.json
```

Paul Tan opt-in:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --output /tmp/malaysia_phase2f10_paul_tan_20260602.md \
  --json-output /tmp/malaysia_phase2f10_paul_tan_20260602.json
```

Prerequisite checks:

```bash
python3.12 -m py_compile scripts/malaysia_rss_summary.py
python3.12 scripts/malaysia_rss_summary.py --self-test
```

## Observed Results

| run | processed | selected | failed sources | sources |
| --- | ---: | ---: | --- | --- |
| baseline | 85 | 9 | none | Malay Mail 8, Astro Awani 1 |
| Paul Tan opt-in | 88 | 10 | none | Malay Mail 8, Paul Tan 1, Astro Awani 1 |

Opt-in-only item:

- source: Paul Tan
- title: `Biodiesel B15 rollout begins June 1 – gov’t says no issue with compatibility; here’s what car brands say`
- category: `【知っておくと得】`
- tags: `prices`, `fuel`
- score: `7`
- reasons: `Paul Tan source-specific gate accepted`, `生活者向けの背景価値`
- penalties: none

The opt-in run had exactly one URL not present in baseline, and it was the Paul Tan item above.

## Interpretation

The rehearsal supports keeping Paul Tan behind local opt-in for now:

- default run did not include Paul Tan;
- opt-in run included at most one Paul Tan item;
- Paul Tan item passed through the source-specific gate;
- no fetch failures occurred;
- no workflow or Pages connection was made.

The selected Paul Tan item is a fuel-policy/driver-cost item, not a broad automotive launch or review. That matches the Phase 2F.9 intended gate shape.

## Next Decision Point

Phase 2F.10 does not approve workflow adoption. The next safe decision would be either:

- continue local rehearsals for additional days; or
- create a manual artifact-only workflow rehearsal that passes `--include-paul-tan`, still without writing to Pages or `news/malaysia/`.

Daily production workflow adoption should remain blocked until explicitly approved.

