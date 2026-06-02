# Phase 2B.5: Live Groq Verification

Date: 2026-06-02
Status: Live GitHub Actions verification completed successfully.

## Summary

Phase 2B.5 verified that live Groq rendering works on GitHub Actions when `GROQ_API_KEY` is configured.

This phase confirms the live workflow path that Phase 2B.4.8 could not execute locally because the API key was unavailable.

This memo also folds in the Phase 2E.7 production-adjacent optional Groq path runs as formal live verification evidence.

This documentation merge does not approve Groq production adoption. Production adoption requires a later explicit phase, and Groq output must not be committed to `news/malaysia/` yet.

## Manual Groq Verification Workflow

Workflow:

- `.github/workflows/malaysia-groq-manual-verify.yml`
- `workflow_dispatch`
- `permissions: contents: read`
- artifact-only verification output

The workflow was manually dispatched on `main` with:

- `model=both`
- `force_all=true`
- `debug_groq=true`

Artifacts were downloaded locally after the run completed.

Result:

Both configured Groq model checks completed successfully:

| model | requested | accepted | fallback |
| --- | ---: | ---: | ---: |
| `llama-3.3-70b-versatile` | 3 | 3 | 0 |
| `openai/gpt-oss-20b` | 3 | 3 | 0 |

This confirms that live artifact-only Groq verification works on GitHub Actions with the repository secret configured.

## Phase 2E.7 Optional Groq Path Evidence

The production daily workflow optional Groq path was also verified with manual dispatch. These runs used the Phase 2E.7 fail-open workflow wiring and kept Groq output under the downloaded artifact / `${RUNNER_TEMP}` path.

### Optional Groq Only

Run:

- run id: `26808794435`
- workflow: `.github/workflows/malaysia-rss-summary.yml`
- `enable_body_enrichment=false`
- `enable_groq_rendering=true`
- `groq_model=llama`
- `force_all_groq=false`
- `debug_groq=true`

Result:

- selected items: `5`
- Groq model: `llama-3.3-70b-versatile`
- requested: `1`
- accepted: `1`
- fallback: `0`
- Groq input: `selected_items.json`
- Groq output: artifact / `${RUNNER_TEMP}` only
- target dateline leakage: none found

### Body Enrichment Plus Groq

Run:

- run id: `26809210928`
- workflow: `.github/workflows/malaysia-rss-summary.yml`
- `enable_body_enrichment=true`
- `enable_groq_rendering=true`
- `groq_model=llama`
- `force_all_groq=false`
- `debug_groq=true`

Result:

- selected items: `5`
- enriched items: `5`
- body fetched: `4`
- body excerpt used: `3`
- body policy: `use_body=3`, `rss_only=1`, `rss_fallback=1`
- Groq model: `llama-3.3-70b-versatile`
- Groq input: `selected_items_enriched.json`
- requested: `1`
- accepted: `1`
- fallback: `0`
- Groq output: artifact / `${RUNNER_TEMP}` only
- target dateline leakage: none found

## Scope

This phase was verification-only.

It did not change or adopt:

- RSS source selection;
- production Pages output;
- `news/malaysia/`;
- Groq prompts;
- article body enrichment;
- daily RSS workflow output format.

The manual verification workflow and Phase 2E.7 optional workflow path remain artifact-only for Groq output. They do not commit Groq Markdown.

## Notes

The previous observed manual workflow failure was caused by missing `GROQ_API_KEY`. After configuring the repository secret, the live run succeeded.

The manual Groq verification workflow generates selected JSON through its own artifact-only path. The Phase 2E.7 optional path verifies the production daily workflow wiring, including body enrichment plus Groq routing.

Production adoption of Groq-rendered Markdown remains a separate decision and is not implied by these verification results.
