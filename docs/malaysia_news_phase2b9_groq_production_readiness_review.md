# Phase 2B.9: Groq Production Readiness Review

Date: 2026-06-07
Status: Readiness review completed. Production replacement is not approved in this phase.

## Summary

Phase 2B.9 reviews the Phase 2B.8 production-candidate artifact pilot for Groq-rendered Malaysia news Markdown.

The review covers 3 manual observation days using the Phase 2E.7 optional Groq path.

The reviewed candidate model is `llama-3.3-70b-versatile`.

Body enrichment was off for this pilot.

The artifact baseline was Phase 2E.9 accepted-only Markdown cleanup.

## Readiness Decision

Groq production replacement is not approved in Phase 2B.9.

RSS-rendered Markdown remains the production output.

Groq output remains artifact-only / optional / verification-only in Phase 2B.9.

Groq output must not be committed to `news/malaysia/`.

Production adoption requires a later explicit phase.

`llama-3.3-70b-versatile` is promising enough to move toward a later production-adoption design phase.

The current evidence best supports accepted-only Groq enhancement with RSS fallback, not immediate full-output replacement.

`openai/gpt-oss-20b` remains a comparison candidate, but it does not block llama-focused planning.

## Pilot Evidence

| day | run | selected | requested | accepted | fallback | leakage |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Day1 | `27009168254` | 8 | 2 | 1 | 1 | none |
| Day2 | `27048530519` | 9 | 3 | 3 | 0 | none |
| Day3 | `27085547448` | 10 | 5 | 5 | 0 | none |

Aggregate:

- selected items reviewed: `27`;
- Groq requested: `10`;
- Groq accepted: `9`;
- Groq fallback: `1`;
- target dateline leakage: none found;
- Groq output stayed under `${RUNNER_TEMP}` / downloaded artifacts;
- no Groq Markdown was committed to `news/malaysia/`.

## Review Notes

Across the 3-day pilot, optional Groq rendering succeeded in every run.

Accepted-only Markdown made the candidate review surface clearer because it displayed only Groq-accepted items.

The accepted summaries were generally readable and stayed close to RSS metadata.

Day1 had one fallback caused by expected guard behavior. This was not a workflow failure.

Day2 produced `3` accepted summaries and no fallback.

Day3 produced `5` accepted summaries and no fallback.

One Day3 human-interest item was readable but lower utility as a production candidate. This supports keeping RSS fallback and item-level selection discipline rather than approving broad full-output replacement.

No target dateline leakage was found in Day1, Day2, or Day3 candidate Markdown.

## Recommendation

Proceed to a later production-adoption design phase focused on accepted-only Groq enhancement with RSS fallback.

Do not pursue immediate full-output Groq replacement.

The next design should preserve every selected RSS item and replace only matching accepted Groq summaries.

Non-requested, skipped, and fallback items should remain RSS-rendered.

If Groq returns zero accepted items, production output should remain RSS-rendered Markdown.

## Boundaries

Phase 2B.9 is documentation/review only.

This phase does not modify:

- workflows;
- scripts;
- config;
- Pages/index generation;
- source selection;
- Groq prompts;
- body enrichment behavior;
- `news/malaysia/`.

RSS-rendered Markdown remains the production output.

Groq output remains artifact-only / optional / verification-only in Phase 2B.9.

Groq output must not be committed to `news/malaysia/`.

Production adoption requires a later explicit phase.

## Verification

Expected added file:

```text
docs/malaysia_news_phase2b9_groq_production_readiness_review.md
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.9: no protected-path diff caused by this phase.
