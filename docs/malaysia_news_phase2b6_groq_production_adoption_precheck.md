# Phase 2B.6: Groq Production Adoption Precheck

Date: 2026-06-02
Status: Decision-prep memo completed. Production adoption is not approved in this phase.

## Summary

Phase 2B.6 organizes the evidence needed before deciding whether Groq-rendered Markdown can be adopted for production.

This phase is documentation-only. It does not change workflows, scripts, config, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/`.

Groq production adoption is not approved in Phase 2B.6. Production adoption requires a later explicit phase.

## Current Evidence

Phase 2B.4.8 confirmed static guard behavior:

- renderer syntax checks passed;
- `scripts/malaysia_rss_summary.py --self-test` passed;
- gpt-oss request guards were verified statically;
- enforcement/misuse skip guards were verified;
- unsupported `進学条件` life-impact fallback was verified;
- English lead leakage fallback was verified;
- Malaysia term normalization after accepted summaries was verified.

Phase 2B.5 confirmed live artifact-only Groq verification on GitHub Actions:

| model | requested | accepted | fallback |
| --- | ---: | ---: | ---: |
| `llama-3.3-70b-versatile` | 3 | 3 | 0 |
| `openai/gpt-oss-20b` | 3 | 3 | 0 |

Phase 2E.7 added optional and fail-open Groq diagnostics to the daily workflow:

- RSS Markdown remains the primary output;
- optional Groq output stays under `${RUNNER_TEMP}`;
- optional failures do not block RSS-only daily output;
- final git staging remains scoped to `news/malaysia/`.

Phase 2E.7 optional Groq path was verified through manual dispatch:

| run | body enrichment | Groq model | selected/enriched items | requested | accepted | fallback |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `26808794435` | disabled | `llama-3.3-70b-versatile` | 5 / n/a | 1 | 1 | 0 |
| `26809210928` | enabled | `llama-3.3-70b-versatile` | 5 / 5 | 1 | 1 | 0 |

The body enrichment plus Groq run confirmed:

- body fetched: `4`;
- body excerpt used: `3`;
- body policy: `use_body=3`, `rss_only=1`, `rss_fallback=1`;
- Groq input switched to `selected_items_enriched.json`;
- target dateline leakage was not found.

## Current Adoption Boundary

Groq output remains artifact-only.

`news/malaysia/` remains RSS-rendered. Groq output must not be committed to `news/malaysia/` yet.

Production adoption must be a separate explicit phase.

## Pre-Adoption Checklist

Before approving production Groq-rendered Markdown, complete these checks:

- run the Phase 2E.7 daily workflow path with manual dispatch and `enable_groq_rendering=true`;
- confirm Groq Markdown is written only under `${RUNNER_TEMP}`;
- confirm final `git add` remains scoped to `news/malaysia/`;
- inspect artifacts for requested, accepted, and fallback counts;
- inspect guard logs for enforcement/misuse skips, English lead leakage, topic mismatch, and unsupported `進学条件`;
- inspect rendered Markdown for dateline leakage;
- compare RSS Markdown and Groq Markdown for readability, factual safety, and Japanese display quality;
- decide the preferred production candidate model.

Current model preference should lean toward `llama-3.3-70b-versatile` unless future gpt-oss evidence becomes stronger.

## Evidence Gaps

Remaining gaps before production adoption:

- Phase 2B.5 selected only `3` live items;
- the manual Groq verification workflow is artifact-only and does not imply production readiness;
- Phase 2E.7 optional path evidence is still limited to one-day artifact runs;
- final RSS Markdown vs Groq Markdown readability and factual-safety review is still needed;
- final production model choice is still needed;
- an explicit production adoption decision is still needed;
- no Groq-rendered Markdown has been approved for `news/malaysia/`.

## Recommendation

Do not adopt Groq-rendered Markdown into production yet.

Treat Phase 2B.6 as the decision-prep checkpoint.

Next recommended phase: run and review the Phase 2E.7 optional Groq path from the production daily workflow using manual dispatch, while keeping it artifact-only and fail-open.

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.6: no protected-path diff caused by this phase.
