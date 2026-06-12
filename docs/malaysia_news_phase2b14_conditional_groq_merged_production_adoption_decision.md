# Phase 2B.14: Conditional Groq Merged Production Adoption Decision

Date: 2026-06-12
Status: Conditional adoption decision recorded. Production overwrite is not implemented in this phase.

## Summary

Phase 2B.14 records the conditional decision to move toward Groq merged production adoption in a later implementation phase.

The decision is not that Groq output is perfect.

The decision is that known failure modes are now limited, observable, and correctable enough to proceed to a fail-open production implementation design.

This phase is docs-only. It does not modify workflows, scripts, config, Pages output, or `news/malaysia/`.

## Decision

Conditional Groq merged production adoption is approved for a later implementation phase.

Required adoption shape:

- RSS Markdown must be generated first and remain the exact fallback;
- Groq merged Markdown may replace `news/malaysia/${today}.md` only after successful merge validation;
- if Groq fails, `GROQ_API_KEY` is missing, accepted count is zero, merge validation fails, URL preservation fails, or required Markdown lines are missing, production output stays RSS-rendered;
- final commit staging must remain scoped to `news/malaysia/`.

Required visible boundary:

- Groq logs, improved-items JSON, selected JSON, and artifact diagnostics must not be committed;
- optional artifact upload should remain available for post-publication review;
- the production surface should include or be paired with a caution that summaries are assisted and may be corrected after publication.

## Evidence Considered

Phase 2B.8 and Phase 2B.9 showed that the evidence supports accepted-only Groq enhancement with RSS fallback, not full-output replacement.

Phase 2B.11 showed that the artifact workflow generated `groq_merged_candidate.md` across multiple runs and preserved selected URLs.

Phase 2B.12A reduced the main blockers:

- unsafe numeric/unit conversion now falls back;
- common RSS fallback datelines are stripped in merged candidate artifacts;
- the Paul Tan EV registration/ranking false positive was removed.

Phase 2B.12A post-cleanup run `27414390078` confirmed:

- processed `112`, selected `9`, failed sources `0`;
- Groq requested `3`, accepted `2`, fallback `1`;
- selected/rendered URLs `9/9`, with no missing or extra URLs;
- target dateline matches: none;
- the MySalam numeric issue safely fell back.

Phase 2B.13 local rehearsal confirmed the RSS side of the production-like path:

- RSS rehearsal succeeded with processed `112`, selected `9`, failed sources `0`;
- local live Groq was not executed because `GROQ_API_KEY` was absent;
- adoption implementation should therefore rely on the GitHub Actions secret path and retain artifact diagnostics.

## Later Implementation Requirements

The later production implementation phase should add an explicit enable flag or repository variable, defaulting to `false`.

When enabled, the workflow should:

- generate RSS Markdown to `news/malaysia/${today}.md` first;
- preserve an internal temp copy of the exact RSS Markdown;
- run Groq merge to `${RUNNER_TEMP}`;
- validate the merged candidate before overwrite;
- overwrite `news/malaysia/${today}.md` only if validation passes.

Validation must require:

- selected URL count equals rendered URL count;
- there are no missing or extra selected URLs;
- category headers and count lines are present;
- target dateline strings are absent after Phase 2B.12A cleanup;
- improved-items counts and stderr logs are captured as artifacts.

Fail-open behavior:

- any failed validation leaves RSS Markdown unchanged;
- missing `GROQ_API_KEY` leaves RSS Markdown unchanged;
- zero accepted Groq items leave RSS Markdown unchanged;
- post-publication correction can be done by rerunning with Groq disabled or manually correcting the daily Markdown.

## Production Boundary

Phase 2B.14 does not implement production overwrite.

RSS-rendered Markdown remains the production output until a later explicit implementation phase changes the workflow.

The initial production model remains `llama-3.3-70b-versatile`.

Body enrichment remains off for the first production overwrite implementation.

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/rehearse_malaysia_groq_merged_production.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.14: no workflow, script, config, Pages, or `news/malaysia/` production output changes.
