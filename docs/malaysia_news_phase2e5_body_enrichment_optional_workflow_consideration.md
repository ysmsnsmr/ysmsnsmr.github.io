# Phase 2E.5: Body Enrichment Optional Workflow Consideration

## Summary

Phase 2E.5 considers whether article body enrichment should become an optional workflow step for the Malaysia news pipeline.

This phase is documentation-only. It does not change workflows, scripts, config, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/`.

本番採用は別Phaseで明示判断する。

## Current Position

Body enrichment should stay out of the current daily production output.

The daily workflow should remain RSS-first:

- generate the production RSS Markdown with the current `--include-paul-tan` command;
- build the Pages index from that RSS Markdown;
- commit only the RSS-based daily output and index.

Article body fetching is useful for observation, but it adds risks that should not be mixed into the daily writer yet:

- external article-page network failures;
- dependency availability, including `newspaper3k` and `lxml_html_clean`;
- longer workflow runtime;
- body text that may increase noise for crime, court, market, overseas, or non-life-impact stories;
- possible mismatch between body excerpt context and the existing RSS metadata selection rules.

## Optional Step Shape

A future optional body enrichment path should run only after selected JSON generation.

Recommended future order for local or artifact-only testing:

```bash
python3 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --output "${run_dir}/original.md" \
  --json-output "${run_dir}/selected_items.json"

python3 -B scripts/enrich_malaysia_selected_items_with_body.py \
  --json-input "${run_dir}/selected_items.json" \
  --output "${run_dir}/selected_items_enriched.json"
```

The enriched JSON should remain an observation artifact unless a later phase explicitly promotes it.

## Recommendation

Do not add body enrichment to the daily production workflow in Phase 2E.5.

If body enrichment is tested in GitHub Actions later, it should be added first as a manual or artifact-only optional step. It should preserve both the plain selected JSON and enriched selected JSON so reviewers can compare what changed.

Successful enrichment should not imply production adoption. 本番採用は別Phaseで明示判断する。

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2E.5: no protected-path diff caused by this phase.
