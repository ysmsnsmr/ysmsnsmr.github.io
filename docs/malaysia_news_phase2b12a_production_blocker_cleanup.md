# Phase 2B.12A: Production-Blocker Cleanup Before Adoption

Date: 2026-06-12
Status: Cleanup implemented. Production overwrite is not approved in this phase.

## Summary

Phase 2B.12A addresses blockers found during Phase 2B.11 artifact observation before any later Groq production adoption decision.

The cleanup targets:

- Groq numeric/unit mistakes in accepted summaries;
- English dateline leakage in RSS-rendered fallback blocks inside merged candidate artifacts;
- Paul Tan false positives where JPJ appears only as a vehicle-registration data source.

RSS-rendered Markdown remains the production output.

Groq merged Markdown remains artifact-only.

Groq output must not be committed to `news/malaysia/` in Phase 2B.12A.

## Implemented Cleanup

Groq validation now rejects high-risk numeric/unit conversions before accepting an improved summary.

Examples that must fallback:

- source `RM1.42b` rendered as `1.42億リンギット`;
- source `1.88 million` rendered as `1.88万人`.

The renderer does not try to repair unsafe numeric output. It fails open to the existing RSS summary.

Merge-candidate Markdown now strips common English dateline prefixes from non-accepted RSS-rendered blocks when `--merge-accepted-with-rss-markdown` is used.

This cleanup is scoped to Groq merged candidate output and does not change the normal RSS production Markdown.

Paul Tan gating now treats EV registration/ranking articles as `review` when `JPJ` appears only as a data source and no driver obligation, road-tax, licence, inspection, summons, recall, fuel, toll, or public-transport impact is present.

## Production Boundary

Phase 2B.12A does not approve production overwrite.

The daily workflow still commits only RSS-rendered Markdown to `news/malaysia/`.

Any later production adoption must explicitly decide whether Groq merged Markdown can replace `news/malaysia/${today}.md`.

## Post-Cleanup Artifact Re-Observation

Run `27414390078` confirmed the Phase 2B.12A cleanup behavior on GitHub Actions.

Observed configuration:

- event: `workflow_dispatch`;
- body enrichment: `false`;
- Groq rendering: `true`;
- model: `llama-3.3-70b-versatile`;
- `groq_rendering_status.txt`: `success`.

Observed RSS and Groq counts:

- processed items: `112`;
- selected items: `9`;
- failed sources: `0`;
- Groq requested: `3`;
- Groq accepted: `2`;
- Groq fallback: `1`.

Observed cleanup effects:

- MySalam triggered numeric/unit fallback with `unsafe numeric unit conversion: rm1.42b`;
- the previous Paul Tan EV registration/ranking item was no longer selected;
- the selected Paul Tan item was a JPJ enforcement/driver-obligation item about unapproved `albino lights`;
- `groq_merged_candidate.md` preserved all `9` selected URLs with no missing or extra URLs;
- target dateline leakage checks for `KUALA LUMPUR,`, `PUTRAJAYA,`, `GEORGE TOWN,`, and `MELAKA,` found no matches in `groq_merged_candidate.md`.

Remaining caveat:

- the MySalam item fell back to RSS-rendered text, so the English RSS title remained visible in the merged candidate;
- this is safer than accepting the incorrect numeric/unit conversion, but it remains a readability issue for any later production adoption design.

## Verification

Expected checks:

```bash
python3.12 -m py_compile scripts/render_malaysia_news_with_groq.py scripts/malaysia_rss_summary.py
python3.12 scripts/malaysia_rss_summary.py --self-test
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.12A: no workflow, config, Pages, or `news/malaysia/` production output changes.
