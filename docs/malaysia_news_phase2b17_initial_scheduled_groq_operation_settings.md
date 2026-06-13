# Phase 2B.17: Initial Scheduled Groq Production Operation Settings

Date: 2026-06-13
Status: Initial scheduled operation settings recorded.

## Summary

Phase 2B.17 records the recommended initial settings for daily scheduled Malaysia news operation after guarded Groq production overwrite was implemented.

The goal is conservative daily operation: use Groq merged output only through the Phase 2B.16 guarded opt-in path, keep RSS Markdown as the fail-open fallback, and avoid broad Groq targeting or body enrichment until more evidence is collected.

## Recommended Scheduled Repository Variables

Initial daily scheduled settings:

```text
MALAYSIA_NEWS_ENABLE_BODY_ENRICHMENT=false
MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=true
MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=true
MALAYSIA_NEWS_GROQ_MODEL=llama
MALAYSIA_NEWS_FORCE_ALL_GROQ=false
MALAYSIA_NEWS_DEBUG_GROQ=true
```

Equivalent manual dispatch settings:

```text
enable_body_enrichment=false
enable_groq_rendering=true
enable_groq_production_overwrite=true
groq_model=llama
force_all_groq=false
debug_groq=true
```

## Rationale

`enable_groq_rendering=true` and `enable_groq_production_overwrite=true` activate the guarded production path that was verified in Phase 2B.16.

`groq_model=llama` keeps the initial production model on `llama-3.3-70b-versatile`, which has the strongest current evidence.

`force_all_groq=false` is the key quality setting. Observation runs with `force_all_groq=true` passed technically, but they accepted broader and more generic items such as political/public-transport background articles. Daily operation should keep Groq targeting narrower.

`enable_body_enrichment=false` is the conservative initial setting. Body enrichment has high fetch success and is becoming safer through body evidence cleanup and structured Groq input, but it still adds dependency, network, and evidence-policy complexity. It should remain optional until the cleaned evidence path has more artifact observations.

`debug_groq=true` should remain enabled during the initial scheduled observation period so fallback reasons, guard behavior, and validator evidence are visible in artifacts. It can be changed to `false` later if daily operation is stable.

## Operating Boundary

RSS Markdown is still generated first.

If Groq rendering fails, `GROQ_API_KEY` is missing, accepted count is `0`, validator fails, or copy fails, production output remains RSS-rendered Markdown.

Groq logs, selected JSON, improved-items JSON, validator reports, and optional diagnostics remain artifact-only.

Final commit staging remains limited to:

```bash
git add news/malaysia/
```

## Initial Observation Checklist

For the first scheduled runs with these settings, inspect artifacts for:

- `groq_rendering_status.txt: success`;
- `groq_production_overwrite_status.txt: applied` or a clear fail-open skip reason;
- validator `passed: true` when overwrite is applied;
- selected/rendered URL counts match;
- no forbidden/dateline matches in the merged candidate;
- Groq requested / accepted / fallback counts;
- accepted item Japanese quality;
- fallback reasons for rejected items;
- whether any post-publication correction was needed.

## Future Changes

Body enrichment may be reconsidered after more artifact evidence using cleaned `body_evidence` input.

`force_all_groq=true` should remain diagnostic-only unless a later phase proves that broader targeting improves quality without adding generic or low-value accepted items.

`debug_groq=false` can be considered after the initial observation period if artifacts show stable guard and validator behavior.
