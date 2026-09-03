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
- hard-safety checks, validator rules, request-cap mechanism, and RSS-only rollback remain unchanged; the default cap is `12` requests per run;
- no candidate is promoted automatically.

## Production 120B Editorial Entry Contract

The production profile uses the already observed GPT-OSS 120B request configuration:

- prompt layout: `user_only`;
- JSON contract: `editorial_entry_v3`;
- completion budget: `800` tokens;
- rate-reset wait maximum: `60` seconds.

The production response has one required Japanese `entry_ja` and zero to two `supporting_points_ja`. Subject, attribution, state, and certainty remain in this prose; life impact and next action are not independent required fields. Groq failures, request-cap skips, malformed JSON, and hard-safety rejections render the RSS Editorial Entry instead.

The single profile registry is `scripts/malaysia_groq_model_profiles.json`. Workflow YAML must not contain a model-ID selection branch.

## Fixed Metrics

The comparison report records these mechanical metrics for every profile:

- URL retention rate;
- validator pass/fail;
- accepted full summaries per requested item;
- request fallback rate;
- selected-item fallback rate;
- forbidden-expression count;
- Groq-replaced versus RSS-inherited entry-field rate;
- hard-safety and transport/JSON-contract diagnostics.

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
- accepted editorial entries preserve subject, attribution, state, and certainty in manual review;
- RSS fallback remains complete and readable for all non-accepted articles.

The hard-safety checks, validator, request-cap mechanism, and JSON-render policy are unchanged. The usefulness vocabulary gate, topic-specific Groq fallback templates, and the old four-item summary contract are not part of this production path. The request cap is `12` items per run in selected JSON order.

## RSS-only Rollback

Immediate rollback requires no code change:

1. Set repository variable `MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false`.
2. Keep `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=true` only if artifact observation should continue.
3. Set `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=false` as well if all Groq calls must stop.
4. Confirm the next artifact reports `skipped_overwrite_disabled` and the committed daily page matches `rss_production_fallback.md`.

`groq_json_render_candidate.md` is the only Groq production candidate. Legacy RSS Markdown and `selected_summary` remain available for one migration stage solely as rollback compatibility data.

Do not use Llama as the primary rollback after its shutdown date. RSS-only is the supported rollback path.

## Golden Failures

Requested production articles that fall back are appended by URL to `scripts/fixtures/malaysia_groq_model_migration_failures.json`. Existing entries are preserved. New failure reasons may be added to an existing URL, but prior articles and reasons are not removed.
