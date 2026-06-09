# Phase 2B.11: Artifact-Only Merge Candidate Workflow Integration

Date: 2026-06-09
Status: Workflow artifact integration implemented. Production overwrite is not approved in this phase.

## Summary

Phase 2B.11 integrates Groq merge mode into the existing Malaysia daily workflow as an artifact-only production-adjacent output.

RSS-rendered Markdown remains the production output.

Optional Groq now produces `groq_merged_candidate.md` under `${RUNNER_TEMP}` / uploaded artifacts only.

Groq merged Markdown must not be written or committed to `news/malaysia/`.

Production overwrite requires a later explicit phase.

## What Changed

The optional Groq step in `.github/workflows/malaysia-rss-summary.yml` now uses:

```text
--merge-accepted-with-rss-markdown
--rss-markdown-input "${{ steps.generate.outputs.output_path }}"
```

The primary optional Groq artifact is now:

```text
${run_dir}/groq_merged_candidate.md
```

The workflow also writes:

```text
${run_dir}/rss_markdown_input.txt
${run_dir}/groq_${model_short}_improved_items.json
${run_dir}/groq_${model_short}_stdout.log
${run_dir}/groq_${model_short}_stderr.log
${run_dir}/groq_rendering_status.txt
```

The Phase 2B.11 workflow integration does not produce the old `--accepted-only-markdown` artifact.

Groq API is still called once per optional Groq run.

## Workflow Behavior

RSS generation remains blocking and primary:

```bash
python3 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --diagnostics \
  --output "${output_path}" \
  --json-output "${run_dir}/selected_items.json"
```

Optional Groq runs only when `enable_groq_rendering=true`.

Body enrichment behavior is unchanged:

- default is off;
- if enabled and successful, Groq uses `selected_items_enriched.json`;
- otherwise Groq uses `selected_items.json`.

If `GROQ_API_KEY` is missing, the workflow:

- writes `skipped_missing_groq_api_key` status;
- copies the RSS Markdown to `${run_dir}/groq_merged_candidate.md`;
- continues without blocking RSS output.

If Groq succeeds with accepted items, the merged candidate:

- preserves all RSS-selected items;
- replaces only matched accepted item blocks;
- keeps non-requested, skipped, and fallback items RSS-rendered.

Final production staging remains scoped to:

```bash
git add news/malaysia/
```

## Boundaries

Phase 2B.11 changes workflow artifact behavior only.

It does not approve production overwrite.

It does not change Groq prompts, targeting, validation, fallback logic, body enrichment behavior, RSS source selection, Pages index behavior, or `news/malaysia/` output policy.

RSS-rendered Markdown remains production output.

Groq merged Markdown remains artifact-only.

A later explicit phase is required before Groq merged Markdown can replace `news/malaysia/${today}.md`.

## Verification

Expected checks:

```bash
python3.12 -m py_compile scripts/render_malaysia_news_with_groq.py
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/malaysia-rss-summary.yml")'
rg -n "merge-accepted-with-rss-markdown|accepted-only-markdown|rss-markdown-input|groq_merged_candidate|git add news/malaysia|RUNNER_TEMP" .github/workflows/malaysia-rss-summary.yml
```

Expected protected non-workflow diff check:

```bash
git diff -- scripts/malaysia_rss_summary.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.11: no protected non-workflow diff caused by this phase.
