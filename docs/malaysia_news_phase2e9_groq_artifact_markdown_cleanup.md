# Phase 2E.9: Groq Artifact Markdown Cleanup

Date: 2026-06-04
Status: Artifact Markdown cleanup implemented.

## Summary

Phase 2E.9 cleans up optional Groq artifact Markdown so it renders only Groq-accepted items.

This cleanup applies only to artifact Markdown. It does not change Groq request targeting, validation, fallback decisions, Groq prompts, source selection, body enrichment behavior, Pages output, or production RSS Markdown.

RSS-rendered Markdown remains the production output.

Groq production adoption remains deferred.

Groq output must not be committed to `news/malaysia/`.

## What Changed

`scripts/render_malaysia_news_with_groq.py` now supports:

```text
--accepted-only-markdown
```

When enabled, the renderer:

- runs the same Groq request, validation, and fallback logic as before;
- keeps `improved-items` JSON unchanged;
- renders only items that received accepted Groq improvements;
- preserves accepted item order from the original `selected_items` order;
- renders a short notice if accepted count is `0`;
- does not render RSS fallback or non-accepted items in Groq artifact Markdown.

The daily workflow optional Groq step passes `--accepted-only-markdown`, while still writing Groq Markdown to:

```text
${run_dir}/groq_${model_short}.md
```

The final production staging remains scoped to:

```bash
git add news/malaysia/
```

## Why

Before this cleanup, optional Groq artifact Markdown could contain a mixture of:

- Groq-accepted improved items;
- skipped items rendered from RSS summaries;
- fallback items rendered from RSS summaries.

That made the artifact harder to review because not every item in the Groq Markdown had actually been improved by Groq.

After this cleanup, the Groq Markdown artifact is a focused review surface for accepted Groq improvements only. Non-accepted items remain available in selected/enriched JSON and log artifacts.

## Review Notes

For Phase 2E.8 multi-day review, inspect:

- `groq_${model_short}.md` for accepted Groq-rendered items only;
- `groq_${model_short}_improved_items.json` for requested / accepted / fallback counts;
- `selected_items.json` and `selected_items_enriched.json` for the full selected item set;
- stderr logs for skip, fallback, and guard diagnostics.

## Post-Push Result

Phase 2E.9 post-push run `26948966282` confirmed the cleanup in GitHub Actions artifacts:

- accepted-only Groq Markdown was generated;
- requested `1`, accepted `1`, fallback `0`;
- no target dateline leakage was found;
- Groq output remained artifact-only;
- no Groq or body artifact files were committed to `news/malaysia/`.

## Verification

Expected checks:

```bash
python3.12 -m py_compile scripts/render_malaysia_news_with_groq.py
```

Artifact-style local run:

```bash
python3.12 -B scripts/render_malaysia_news_with_groq.py \
  --json-input /tmp/malaysia_phase2e7_body_groq_llama/malaysia-rss-summary-optional-26809210928-1/malaysia-rss-summary-optional-2026-06-02-26809210928-1/selected_items_enriched.json \
  --output /tmp/malaysia_phase2e9_groq_accepted_only.md \
  --model llama-3.3-70b-versatile \
  --debug-groq \
  --improved-items-output /tmp/malaysia_phase2e9_groq_improved_items.json \
  --accepted-only-markdown
```

Expected protected diff check:

```bash
git diff -- scripts/malaysia_rss_summary.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```
