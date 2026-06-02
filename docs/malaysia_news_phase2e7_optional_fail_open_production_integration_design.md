# Phase 2E.7: Optional Fail-Open Production Integration

## Summary

Phase 2E.7 adds an optional and fail-open production-adjacent path for body enrichment and Groq rendering in the daily Malaysia RSS workflow.

RSS Markdown remains the primary output. Body enrichment and Groq rendering are optional follow-up steps, and their outputs stay under the GitHub Actions temporary run directory.

This phase changes the workflow wiring only. It does not change scripts, config, Pages output rules, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/` content format.

本番採用は別Phaseで明示判断する。

## Required Design Points

- RSS Markdown remains the primary output
- body enrichment and Groq rendering are optional follow-up steps
- optional failures must fail open
- RSS-only daily output must not be blocked
- Groq output must not be committed to news/malaysia/ before a separate approval phase

## Implemented Fail-Open Order

The workflow keeps the RSS path first and independent:

1. Generate production RSS Markdown and selected JSON.
2. Build the Pages index from the RSS Markdown.
3. Optionally run body enrichment in a temporary run directory.
4. Optionally run Groq rendering against plain or enriched selected JSON.
5. Upload optional enriched outputs, Groq Markdown, improved-items JSON, logs, and status files as artifacts.
6. Commit only `news/malaysia/`.

The daily RSS Markdown must remain valid even if optional body enrichment fails, Groq API access fails, Groq validation rejects items, or enriched rendering is skipped.

## Enablement

Manual `workflow_dispatch` inputs default to false:

- `enable_body_enrichment`;
- `enable_groq_rendering`;
- `force_all_groq`;
- `debug_groq`.

The Groq model input defaults to `llama`, with `gpt-oss` available for manual checks.

Scheduled daily runs read repository variables and treat unset values as false:

- `MALAYSIA_NEWS_ENABLE_BODY_ENRICHMENT`;
- `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING`;
- `MALAYSIA_NEWS_FORCE_ALL_GROQ`;
- `MALAYSIA_NEWS_DEBUG_GROQ`;
- `MALAYSIA_NEWS_GROQ_MODEL`.

## Fail-Open Rules

Optional enrichment failures should be visible but non-blocking:

- log the failure clearly;
- preserve the RSS-only Markdown and selected JSON;
- continue the daily RSS output path;
- avoid silently treating fallback-only Groq output as production-ready enriched output.

The production writer should fail only for RSS-generation, Pages-index, or final validation problems in the primary RSS path. Optional body and Groq steps should not block the RSS-only daily output.

Body enrichment dependency installation runs only when body enrichment is enabled. If dependency installation or body fetching fails, the workflow writes status and log files under `${RUNNER_TEMP}` and continues.

Groq rendering runs only when enabled. If `GROQ_API_KEY` is missing, the workflow writes a warning/status file and continues. Optional Groq Markdown is always written under `${RUNNER_TEMP}` and the workflow must not pass `news/malaysia/${today}.md` to the Groq renderer.

## Production Guardrails

Future optional integration must preserve existing production boundaries:

- no source-selection changes;
- no Lowyat.NET production promotion;
- no broad Japanese normalization changes;
- no Groq prompt expansion unless separately approved;
- no body-enriched output committed to production paths unless separately approved;
- no Groq output committed to `news/malaysia/` before a separate approval phase.

The final git staging step remains scoped to:

```bash
git add news/malaysia/
```

Successful optional body enrichment or Groq rendering remains an observation signal. It does not imply production adoption. 本番採用は別Phaseで明示判断する。

## Verification

Static checks:

```bash
python3.12 -m py_compile scripts/malaysia_rss_summary.py scripts/enrich_malaysia_selected_items_with_body.py scripts/render_malaysia_news_with_groq.py scripts/build_malaysia_news_index.py
```

Local RSS rehearsal with JSON output:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --diagnostics \
  --output /tmp/malaysia_phase2e7/rss.md \
  --json-output /tmp/malaysia_phase2e7/selected_items.json
```

Workflow inspection:

```bash
rg -n "git add|git commit|git push|news/malaysia|selected_items_enriched|render_malaysia_news_with_groq|GROQ_API_KEY|upload-artifact|RUNNER_TEMP" .github/workflows/malaysia-rss-summary.yml
```

Expected:

- Groq `--output` points only to `${run_dir}`;
- `git add` targets only `news/malaysia/`;
- artifact upload uses `if: always()`;
- body dependency install is conditional on body enrichment being enabled.

Expected unchanged script/config/source-selection diff:

```bash
git diff -- scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected intended Phase 2E.7 diff:

- `.github/workflows/malaysia-rss-summary.yml`;
- this memo.
