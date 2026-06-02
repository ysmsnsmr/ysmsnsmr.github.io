# Phase 2F.10: Paul Tan Opt-In Output Review

## Summary

Phase 2F.10 reviewed the local rehearsal outputs for the Paul Tan opt-in path.

The source gate and cap behaved as expected:

- baseline selected items: `9`;
- opt-in selected items: `10`;
- failed sources: none in both runs;
- Paul Tan selected items: `0` in baseline, `1` in opt-in;
- opt-in-only URL count: `1`;
- Paul Tan source cap held at `1`.

The selected Paul Tan item was relevant, but the display quality is not ready for workflow adoption yet.

## Reviewed Files

Baseline:

- `/tmp/malaysia_phase2f10_baseline_20260602.md`
- `/tmp/malaysia_phase2f10_baseline_20260602.json`

Paul Tan opt-in:

- `/tmp/malaysia_phase2f10_paul_tan_20260602.md`
- `/tmp/malaysia_phase2f10_paul_tan_20260602.json`

## Output Delta

The opt-in run added exactly one item:

- source: Paul Tan
- title: `Biodiesel B15 rollout begins June 1 – gov’t says no issue with compatibility; here’s what car brands say`
- category: `【知っておくと得】`
- tags: `prices`, `fuel`
- score: `7`
- reasons: `Paul Tan source-specific gate accepted`, `生活者向けの背景価値`
- penalties: none

This is a plausible life-impact candidate because B15 biodiesel rollout can affect fuel policy, vehicle owners, and public messaging around fuel compatibility.

## Positive Findings

- Paul Tan remained opt-in only.
- Baseline output did not include Paul Tan.
- Opt-in output included only one Paul Tan item.
- The selected item was not a car launch, review, showroom sale, motorsport item, or model-pricing item.
- The gate correctly mapped the item to `prices` and `fuel`.
- No fetch failures occurred.
- No workflow, Pages, or `news/malaysia/` write path was involved.

## Display Issues

The Paul Tan item exposed a display-quality gap:

- `結論` remained the English RSS title.
- `何が起きた` included a long English RSS description and WordPress-style trailing text: `The post ... appeared first on Paul Tan's Automotive News`.
- `生活への影響` used the generic fallback: `生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。`
- The output does not yet explain the practical reader impact in Japanese, such as fuel compatibility, rollout timing, or whether drivers need immediate action.

This is acceptable for local rehearsal, but not enough for workflow adoption.

## Adoption Decision

Do not connect Paul Tan opt-in to the daily production workflow yet.

Keep Phase 2F.9 as local opt-in only until a follow-up display guard is added for Paul Tan fuel/transport items.

The gate/cap behavior is promising, but the rendered user-facing text needs a source/topic-specific summary path before production use.

## Recommended Next Phase

Phase 2F.11 should focus on Paul Tan display normalization for accepted items, still local-only:

- add a fuel/B15/RON95/diesel display template or summary branch;
- strip WordPress feed boilerplate such as `The post ... appeared first on ...`;
- keep eligibility RSS-only and Groq-free;
- rerun baseline and opt-in output comparison;
- confirm Paul Tan remains capped at `1`;
- keep the daily workflow unchanged.

## Constraints Confirmed

This review does not change:

- production RSS default behavior;
- GitHub Actions workflows;
- Pages output;
- `news/malaysia/`;
- Groq behavior;
- body fetching;
- Phase 2F configs.

