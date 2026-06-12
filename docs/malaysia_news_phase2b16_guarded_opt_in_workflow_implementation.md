# Phase 2B.16: Guarded Opt-In Workflow Implementation

Date: 2026-06-12
Status: Guarded opt-in workflow implemented. Default production output remains RSS-rendered Markdown.

## Summary

Phase 2B.16 implements conditional Groq merged production overwrite in the daily Malaysia RSS workflow.

The default remains RSS-only. Groq merged Markdown can overwrite:

```text
news/malaysia/${today}.md
```

only when explicitly enabled and the Phase 2B.15B validator passes.

RSS Markdown is always generated first and preserved as the exact fail-open fallback.

## Enable Flags

Manual workflow input:

```text
enable_groq_production_overwrite
```

Scheduled repository variable:

```text
MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE
```

Both default to `false`. An unset repository variable is treated as `false`.

Production overwrite is attempted only when:

- `enable_groq_rendering=true`;
- `enable_groq_production_overwrite=true`;
- optional Groq rendering status is `success`;
- `groq_merged_candidate.md` exists under `${RUNNER_TEMP}`;
- improved-items JSON exists under `${RUNNER_TEMP}`;
- `scripts/validate_malaysia_groq_merged_candidate.py` exits `0`.

## Workflow Shape

The workflow now runs in this order:

1. Generate RSS Markdown to `news/malaysia/${today}.md`.
2. Write selected JSON under `${RUNNER_TEMP}`.
3. Copy exact RSS Markdown to `${run_dir}/rss_production_fallback.md`.
4. Run optional body enrichment if enabled.
5. Run optional Groq merged candidate generation if enabled.
6. Run guarded production overwrite validation.
7. Copy `groq_merged_candidate.md` over `news/malaysia/${today}.md` only if validation passes.
8. Build `news/malaysia/index.html` from the final daily Markdown.
9. Commit only `news/malaysia/`.

Final staging remains:

```bash
git add news/malaysia/
```

## Fail-Open Behavior

Any guarded overwrite skip or failure leaves RSS Markdown as production output.

RSS output is kept when:

- overwrite flag is false;
- Groq rendering is disabled;
- `GROQ_API_KEY` is missing;
- Groq rendering fails;
- accepted count is `0`;
- merged candidate or improved-items JSON is missing;
- validator fails;
- candidate copy fails.

The workflow writes status files under `${run_dir}` and continues unless RSS generation or Pages index build itself fails.

## Artifact Boundary

These files remain artifact-only and must not be committed:

- selected JSON;
- enriched selected JSON;
- Groq logs;
- improved-items JSON;
- `groq_merged_candidate.md`;
- validator status/report files;
- optional diagnostics status files.

The optional diagnostics artifact upload remains `if: always()`.

## Rollback

Rollback is disabling:

```text
enable_groq_production_overwrite
```

or rerunning with Groq rendering disabled.

Because RSS Markdown is generated first and preserved as `${run_dir}/rss_production_fallback.md`, a failed or skipped overwrite keeps the RSS-rendered daily output.

## Defaults

The first production overwrite model remains:

```text
llama-3.3-70b-versatile
```

Body enrichment remains off by default and is independent of overwrite.

`openai/gpt-oss-20b` remains selectable for comparison, but `llama-3.3-70b-versatile` is the primary candidate.

## Verification

Static checks:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/malaysia-rss-summary.yml")'
python3.12 -m py_compile scripts/validate_malaysia_groq_merged_candidate.py scripts/render_malaysia_news_with_groq.py scripts/malaysia_rss_summary.py scripts/build_malaysia_news_index.py
```

Workflow inspection:

```bash
rg -n "enable_groq_production_overwrite|MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE|rss_production_fallback|validate_malaysia_groq_merged_candidate|groq_production_overwrite|build_malaysia_news_index|git add news/malaysia|upload-artifact" .github/workflows/malaysia-rss-summary.yml
```

Expected behavior:

- overwrite flag false keeps RSS output;
- Groq disabled keeps RSS output;
- missing `GROQ_API_KEY` keeps RSS output;
- Groq success but accepted `0` keeps RSS output;
- validator failure keeps RSS output;
- validator success overwrites only `news/malaysia/${today}.md`;
- index build reflects the final daily Markdown;
- artifacts remain diagnostics only.
