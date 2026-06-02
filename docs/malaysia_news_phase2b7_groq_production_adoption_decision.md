# Phase 2B.7: Groq Production Adoption Decision

Date: 2026-06-02
Status: Production adoption deferred. Groq-rendered Markdown is not approved for production output in this phase.

## Summary

Phase 2B.7 records the formal production adoption decision for Groq-rendered Malaysia news Markdown.

Decision: defer adoption.

RSS-rendered Markdown remains the production output. Groq rendering remains artifact-only, optional, and verification-only.

Groq output must not be written or committed to `news/malaysia/`.

## Evidence Considered

Phase 2B.4.8 static guard verification passed:

- renderer syntax checks passed;
- gpt-oss request guards were verified statically;
- enforcement/misuse skip guards were verified;
- unsupported `進学条件` life-impact fallback was verified;
- English lead leakage fallback was verified;
- Malaysia term normalization after accepted summaries was verified.

Phase 2B.5 live artifact verification succeeded:

| workflow | model | requested | accepted | fallback |
| --- | --- | ---: | ---: | ---: |
| manual Groq verification | `llama-3.3-70b-versatile` | 3 | 3 | 0 |
| manual Groq verification | `openai/gpt-oss-20b` | 3 | 3 | 0 |
| Phase 2E.7 optional Groq path | `llama-3.3-70b-versatile` | 1 | 1 | 0 |
| Phase 2E.7 body enrichment plus Groq path | `llama-3.3-70b-versatile` | 1 | 1 | 0 |

Phase 2E.7 production-adjacent workflow behavior was also confirmed:

- optional Groq output stayed under `${RUNNER_TEMP}` / downloaded artifacts;
- body enrichment plus Groq used `selected_items_enriched.json`;
- no target dateline leakage was found in the checked Groq Markdown;
- final production staging remained scoped to `news/malaysia/`.

## Decision

Groq production adoption is not approved in Phase 2B.7.

The successful live checks are enough to keep Groq in the optional verification path, but not enough to replace the RSS-rendered production output.

Reasons:

- evidence is still one-day and low requested-count;
- final RSS Markdown vs Groq Markdown readability review is incomplete;
- final factual-safety review is incomplete;
- production model choice is not final enough for output replacement;
- no multi-day Phase 2E.7 artifact review has been recorded yet.

## Current Production Boundary

Production output remains:

- RSS-rendered Markdown under `news/malaysia/`;
- existing Pages index generated from RSS-rendered output.

Groq rendering remains:

- artifact-only;
- optional;
- verification-only;
- fail-open;
- not committed to production paths.

Production adoption requires a later explicit phase.

## Next Actions

Continue Phase 2E.7 optional Groq runs as artifact-only checks.

Before reconsidering adoption, record multi-day artifact reviews that compare RSS Markdown and Groq Markdown for:

- factual safety;
- Japanese readability;
- dateline leakage;
- guard fallback behavior;
- usefulness over the current RSS-rendered output.

The next review should also decide whether `llama-3.3-70b-versatile` remains the preferred production candidate model or whether more gpt-oss evidence is needed.

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.7: no protected-path diff caused by this phase.

