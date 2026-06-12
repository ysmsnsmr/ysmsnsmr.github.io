# Phase 2B.15A: Conditional Production Overwrite Implementation Design

Date: 2026-06-12
Status: Implementation design recorded. Production overwrite is not implemented in this phase.

## Summary

Phase 2B.15A defines how a later phase should implement conditional Groq merged production overwrite.

This phase is docs-only. It does not modify workflows, scripts, config, Pages output, or `news/malaysia/`.

RSS Markdown remains the current production output until a later implementation phase explicitly changes the workflow.

## Enable Flags

The later implementation should add a dedicated overwrite flag that defaults to `false`.

Manual workflow input:

```text
enable_groq_production_overwrite
```

Scheduled repository variable:

```text
MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE
```

Production overwrite is allowed only when all of these are true:

- `enable_groq_rendering=true`;
- `enable_groq_production_overwrite=true`;
- `GROQ_API_KEY` is present;
- Groq rendering status is `success`;
- Groq accepted count is greater than `0`;
- merged candidate validation passes.

## Workflow Shape

RSS generation remains first and blocking.

The workflow should write RSS Markdown to:

```text
news/malaysia/${today}.md
```

It should also preserve an exact fallback copy under `${run_dir}`:

```text
${run_dir}/rss_production_fallback.md
```

Groq merge remains in `${RUNNER_TEMP}` first:

```text
${run_dir}/groq_merged_candidate.md
```

Only after validation passes should the workflow copy the merged candidate over:

```text
news/malaysia/${today}.md
```

Final commit staging remains:

```bash
git add news/malaysia/
```

Groq logs, improved-items JSON, selected JSON, and artifact diagnostics must never be committed.

## Validation Requirements

Before overwrite, validation must confirm:

- selected URL count equals rendered URL count;
- there are no missing or extra selected URLs;
- category headers are present;
- processed count, selected count, and failed-source line are present;
- target dateline strings are absent after Phase 2B.12A cleanup;
- `::inbox-item`, `The post`, `appeared first`, and `Lowyat` are absent;
- improved-items JSON counts are readable;
- accepted count is greater than `0`.

On any validation failure:

- leave `news/malaysia/${today}.md` as RSS-rendered Markdown;
- write a status file explaining the failure under `${run_dir}`;
- upload artifacts with `if: always()`;
- do not fail the whole daily workflow unless RSS generation itself failed.

## Defaults And Rollback

Body enrichment remains off for the first production overwrite implementation.

The initial production model remains:

```text
llama-3.3-70b-versatile
```

The rollback path is:

- disable `enable_groq_production_overwrite`;
- or rerun with Groq rendering disabled;
- or manually correct the daily Markdown if a post-publication issue is found.

The first implementation should prefer false negatives over false positives. When unsure, keep RSS Markdown.

## Test Plan For Later Implementation

Static checks:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/malaysia-rss-summary.yml")'
python3.12 -m py_compile scripts/render_malaysia_news_with_groq.py scripts/malaysia_rss_summary.py
```

Workflow inspection:

- new overwrite flag defaults to `false`;
- `git add` remains scoped to `news/malaysia/`;
- Groq logs, JSON, and artifacts are never committed.

Behavior tests:

- overwrite flag false keeps RSS output;
- Groq disabled keeps RSS output;
- missing `GROQ_API_KEY` keeps RSS output;
- accepted count `0` keeps RSS output;
- URL validation failure keeps RSS output;
- validation success overwrites only `news/malaysia/${today}.md`;
- artifact upload still runs with `if: always()`.

## Production Boundary

Phase 2B.15A does not implement production overwrite.

Actual workflow implementation requires a later explicit phase.

Expected protected diff check for Phase 2B.15A:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/rehearse_malaysia_groq_merged_production.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result: no workflow, script, config, Pages, or `news/malaysia/` production output changes.
