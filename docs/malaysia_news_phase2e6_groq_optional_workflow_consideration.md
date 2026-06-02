# Phase 2E.6: Groq Optional Workflow Consideration

## Summary

Phase 2E.6 considers whether Groq enriched rendering should become an optional workflow step for the Malaysia news pipeline.

This phase is documentation-only. It does not change workflows, scripts, config, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/`.

本番採用は別Phaseで明示判断する。

## Current Position

Groq enriched rendering should stay out of the current daily Pages output.

The daily production workflow currently remains RSS-first:

- generate RSS Markdown with the production command that includes `--include-paul-tan`;
- build the Pages index from RSS Markdown;
- commit the RSS-based output under `news/malaysia/`.

Groq rendering should remain a manual or artifact-only comparison path until a later explicit production-adoption phase.

## Existing Renderer Shape

`scripts/render_malaysia_news_with_groq.py` already supports local and artifact verification through:

```bash
python3 -B scripts/render_malaysia_news_with_groq.py \
  --json-input "${run_dir}/selected_items.json" \
  --output "${run_dir}/groq.md" \
  --model llama-3.3-70b-versatile \
  --force-all \
  --debug-groq \
  --improved-items-output "${run_dir}/groq_improved_items.json"
```

That shape is appropriate for observation because it can preserve:

- RSS baseline Markdown;
- selected JSON;
- Groq-rendered Markdown;
- improved-items JSON;
- stdout, stderr, and guard diagnostics.

## Production-Style Rehearsal Note

Any future production-style Groq rehearsal should align selected JSON generation with the current production RSS command by including `--include-paul-tan`.

The Groq step should run after selected JSON generation and should not replace RSS Markdown in the daily output without a separate explicit phase.

## Recommendation

Do not add Groq rendering to the daily production workflow in Phase 2E.6.

Keep Groq enriched rendering as a manual or artifact-only optional workflow step. If a later workflow adds it, the workflow should upload Groq output as artifacts first, not commit it to `news/malaysia/`.

Successful Groq rendering should not imply production adoption. 本番採用は別Phaseで明示判断する。

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2E.6: no protected-path diff caused by this phase.
