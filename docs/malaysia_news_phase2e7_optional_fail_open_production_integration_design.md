# Phase 2E.7: Optional Fail-Open Production Integration Design

## Summary

Phase 2E.7 designs a future optional and fail-open production-adjacent path for body enrichment and Groq rendering.

This phase is documentation-only. It does not change workflows, scripts, config, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/`.

本番採用は別Phaseで明示判断する。

## Required Design Points

- RSS Markdown remains the primary output
- body enrichment and Groq rendering are optional follow-up steps
- optional failures must fail open
- RSS-only daily output must not be blocked
- Groq output must not be committed to news/malaysia/ before a separate approval phase

## Future Fail-Open Order

A future optional production-adjacent workflow should keep the RSS path first and independent:

1. Generate production RSS Markdown and selected JSON.
2. Build the Pages index from the RSS Markdown.
3. Optionally run body enrichment in a temporary run directory.
4. Optionally run Groq rendering against plain or enriched selected JSON.
5. Upload optional enriched outputs, Groq Markdown, improved-items JSON, logs, and summaries as artifacts or diagnostics.

The daily RSS Markdown must remain valid even if optional body enrichment fails, Groq API access fails, Groq validation rejects items, or enriched rendering is skipped.

## Fail-Open Rules

Optional enrichment failures should be visible but non-blocking:

- log the failure clearly;
- preserve the RSS-only Markdown and selected JSON;
- continue the daily RSS output path;
- avoid silently treating fallback-only Groq output as production-ready enriched output.

The production writer should fail only for RSS-generation, Pages-index, or final validation problems in the primary RSS path. Optional body and Groq steps should not block the RSS-only daily output.

## Production Guardrails

Future optional integration must preserve existing production boundaries:

- no source-selection changes;
- no Lowyat.NET production promotion;
- no broad Japanese normalization changes;
- no Groq prompt expansion unless separately approved;
- no body-enriched output committed to production paths unless separately approved;
- no Groq output committed to `news/malaysia/` before a separate approval phase.

Successful optional body enrichment or Groq rendering should remain an observation signal. It does not imply production adoption. 本番採用は別Phaseで明示判断する。

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2E.7: no protected-path diff caused by this phase.
