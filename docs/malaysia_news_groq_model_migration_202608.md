# Malaysia News Groq Model Migration

## Deadline

- Previous production model: `llama-3.3-70b-versatile`
- Groq shutdown date: 2026-08-16
- Replacement decision deadline: 2026-08-15
- Production replacement: `openai/gpt-oss-120b`
- Remaining artifact-only candidates:
  - `openai/gpt-oss-20b`
  - `qwen/qwen3.6-27b`

Qwen 3.6 27B is a preview profile and must remain artifact-only during this migration observation.

Groq's deprecation notice recommends GPT-OSS 120B or Qwen 3.6 27B as replacements for Llama 3.3 70B:
https://console.groq.com/docs/deprecations

## Change Boundary

Before the cutover:

- production continues to use the Llama profile;
- candidates run from the same selected/enriched item JSON;
- candidates are artifact-only and cannot overwrite production;
- prompt, validator rules, request cap, and production gate remain unchanged;
- no candidate is promoted automatically.

## Production 120B Request Contract

The production profile uses the already observed GPT-OSS 120B request configuration:

- prompt layout: `user_only`;
- JSON contract: `summary_only`;
- completion budget: `800` tokens;
- rate-reset wait maximum: `60` seconds.

`summary_only` deliberately does not request an entry object or entry review. Accepted full summaries and the existing JSON-render fallback remain the production display path.

The single profile registry is `scripts/malaysia_groq_model_profiles.json`. Workflow YAML must not contain a model-ID selection branch.

## Fixed Metrics

The comparison report records these mechanical metrics for every profile:

- URL retention rate;
- validator pass/fail;
- accepted full summaries per requested item;
- request fallback rate;
- selected-item fallback rate;
- forbidden-expression count;
- entry-contract completion rate;
- reviewed-entry availability rate;
- Groq-replaced versus inherited summary-line rate.

Semantic quality remains a manual review. Each selected article is shown with the same five review criteria:

- subject preserved;
- attribution preserved;
- state and certainty preserved;
- claims supported by the available source text;
- natural Japanese that helps the reader decide whether to open the source.

Validator pass alone is not treated as proof of summary quality.

## Decision Rule

The 2026-08-15 cutover selects GPT-OSS 120B after scheduled artifacts show:

- URL retention remains 100%;
- validator failures and forbidden expressions do not increase;
- request fallback is operationally acceptable and not dominated by HTTP 429;
- accepted summaries preserve subject, attribution, state, and certainty in manual review;
- generic fallback does not materially increase compared with the Llama baseline.

The system prompt text, semantic gate, validator, request cap, and JSON-render policy are unchanged. The model profile supplies the already observed 120B request envelope.

## RSS-only Rollback

Immediate rollback requires no code change:

1. Set repository variable `MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false`.
2. Keep `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=true` only if artifact observation should continue.
3. Set `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=false` as well if all Groq calls must stop.
4. Confirm the next artifact reports `skipped_overwrite_disabled` and the committed daily page matches `rss_production_fallback.md`.

The merge and JSON-render artifacts remain diagnostic rollback evidence; neither is deleted during migration.

Do not use Llama as the primary rollback after its shutdown date. RSS-only is the supported rollback path.

## Golden Failures

Requested production articles that fall back are appended by URL to `scripts/fixtures/malaysia_groq_model_migration_failures.json`. Existing entries are preserved. New failure reasons may be added to an existing URL, but prior articles and reasons are not removed.
