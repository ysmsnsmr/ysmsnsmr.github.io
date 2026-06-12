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

## Workflow Test Result

### 2026-06-09

Run `27201344308` confirmed that the Phase 2B.11 artifact-only merge candidate path works on GitHub Actions.

Observed configuration:

- event: `workflow_dispatch`;
- body enrichment: `false`;
- Groq rendering: `true`;
- model: `llama-3.3-70b-versatile`;
- `groq_rendering_status.txt`: `success`.

Observed RSS and Groq counts:

- processed items: `117`;
- selected items: `11`;
- failed sources: `0`;
- Groq requested: `3`;
- Groq accepted: `2`;
- Groq fallback: `1`.

Observed artifact paths:

- `groq_json_input.txt` pointed to `${RUNNER_TEMP}/.../selected_items.json`;
- `rss_markdown_input.txt` pointed to `news/malaysia/2026-06-09.md`;
- `groq_merged_candidate.md` was present in the downloaded artifact.

The merged candidate preserved all selected items:

- selected URLs in `selected_items.json`: `11`;
- URLs rendered in `groq_merged_candidate.md`: `11`;
- missing selected URLs: `0`;
- extra rendered URLs: `0`.

Review caveat:

- `groq_merged_candidate.md` still contained RSS fallback dateline leakage in non-accepted RSS-rendered items, including `PUTRAJAYA,` and `KUALA LUMPUR,`;
- this confirms that merge mode preserves RSS fallback blocks as designed;
- the remaining RSS fallback dateline leakage is a production-readiness issue for a later explicit phase, not a Phase 2B.11 workflow artifact integration blocker.

### 2026-06-10

Run `27244759167` confirmed a second Phase 2B.11 artifact-only merge candidate run on GitHub Actions.

Observed configuration:

- event: `workflow_dispatch`;
- body enrichment: `false`;
- Groq rendering: `true`;
- model: `llama-3.3-70b-versatile`;
- `groq_rendering_status.txt`: `success`.

Observed RSS and Groq counts:

- processed items: `120`;
- selected items: `11`;
- failed sources: `0`;
- Groq requested: `4`;
- Groq accepted: `2`;
- Groq fallback: `2`.

Observed artifact paths:

- `groq_json_input.txt` pointed to `${RUNNER_TEMP}/.../selected_items.json`;
- `rss_markdown_input.txt` pointed to `news/malaysia/2026-06-10.md`;
- `groq_merged_candidate.md` was present in the downloaded artifact.

The merged candidate preserved all selected items:

- selected URLs in `selected_items.json`: `11`;
- URLs rendered in `groq_merged_candidate.md`: `11`;
- missing selected URLs: `0`;
- extra rendered URLs: `0`.

Review caveat:

- `groq_merged_candidate.md` again contained RSS fallback dateline leakage in non-accepted RSS-rendered items, including `PUTRAJAYA,` and `KUALA LUMPUR,`;
- this confirms the Phase 2B.11 workflow artifact path is stable across two runs, while the RSS fallback display cleanup remains a later production-readiness issue;
- no Groq Markdown is approved for `news/malaysia/` in Phase 2B.11.

### 2026-06-11

Run `27341458181` confirmed a third Phase 2B.11 artifact-only merge candidate run on GitHub Actions.

Observed configuration:

- event: `workflow_dispatch`;
- body enrichment: `false`;
- Groq rendering: `true`;
- model: `llama-3.3-70b-versatile`;
- `groq_rendering_status.txt`: `success`.

Observed RSS and Groq counts:

- processed items: `115`;
- selected items: `10`;
- failed sources: `0`;
- Groq requested: `2`;
- Groq accepted: `1`;
- Groq fallback: `1`.

Observed artifact paths:

- `groq_json_input.txt` pointed to `${RUNNER_TEMP}/.../selected_items.json`;
- `rss_markdown_input.txt` pointed to `news/malaysia/2026-06-11.md`;
- `groq_merged_candidate.md` was present in the downloaded artifact.

The merged candidate preserved all selected items:

- selected URLs in `selected_items.json`: `10`;
- URLs rendered in `groq_merged_candidate.md`: `10`;
- missing selected URLs: `0`;
- extra rendered URLs: `0`.

Review notes:

- the accepted item was an Astro Awani item about Malaysia and WOAH strengthening animal-health cooperation;
- the accepted Japanese summary was readable and stayed within the source topic;
- no obvious major factual error was found in the accepted item during artifact review;
- `groq_merged_candidate.md` still contained RSS fallback dateline leakage in non-accepted RSS-rendered items, especially `KUALA LUMPUR,`;
- the observed issue remains within a recoverable post-publication correction range if this path is later adopted;
- no Groq Markdown is approved for `news/malaysia/` in Phase 2B.11.

### 2026-06-12

Run `27410225459` confirmed a fourth Phase 2B.11 artifact-only merge candidate run on GitHub Actions.

Observed configuration:

- event: `workflow_dispatch`;
- body enrichment: `false`;
- Groq rendering: `true`;
- model: `llama-3.3-70b-versatile`;
- `groq_rendering_status.txt`: `success`.

Observed RSS and Groq counts:

- processed items: `113`;
- selected items: `10`;
- failed sources: `0`;
- Groq requested: `4`;
- Groq accepted: `4`;
- Groq fallback: `0`.

Observed artifact paths:

- `groq_json_input.txt` pointed to `${RUNNER_TEMP}/.../selected_items.json`;
- `rss_markdown_input.txt` pointed to `news/malaysia/2026-06-12.md`;
- `groq_merged_candidate.md` was present in the downloaded artifact.

The merged candidate preserved all selected items:

- selected URLs in `selected_items.json`: `10`;
- URLs rendered in `groq_merged_candidate.md`: `10`;
- missing selected URLs: `0`;
- extra rendered URLs: `0`.

Review notes:

- accepted Groq summaries were generated for MyDigital ID, MySalam, Selangor hiking permits, and LHDN e-Derma;
- MyDigital ID, Selangor hiking permits, and LHDN e-Derma were readable and broadly stayed within the RSS metadata topic;
- the MySalam accepted summary showed a likely numeric/unit factual error: `RM1.42b` was rendered as `1.42億リンギット`, and `1.88 million` was rendered as `1.88万人`;
- this is a significant production-readiness caveat for unattended Groq overwrite, even though it would be correctable after detection;
- `groq_merged_candidate.md` still contained RSS fallback dateline leakage in non-accepted RSS-rendered items, including `KUALA LUMPUR,` and `MELAKA,`;
- an RSS-rendered Paul Tan fallback item about EV brand registrations was displayed as a JPJ/driver-procedure item because the RSS metadata mentioned JPJ data; this is outside Groq acceptance but should be treated as a Paul Tan gate/display review item;
- no Groq Markdown is approved for `news/malaysia/` in Phase 2B.11.

## Continued Artifact Observation Window

Runs on `2026-06-11` and `2026-06-12` are treated as the continued Phase 2B.11 artifact observation window. Both results are recorded above.

The review standard is not whether Groq merged Markdown is perfect. The standard is whether any issue is small enough to detect, explain, and correct after publication if this path is later adopted.

For each run, record:

- whether the workflow run succeeded;
- whether `groq_merged_candidate.md` appeared in the uploaded artifact;
- processed item count, selected item count, and failed source count;
- Groq requested, accepted, and fallback counts;
- Japanese quality of accepted items;
- English text or dateline leakage remaining in fallback or skipped RSS-rendered items;
- whether any major factual error is apparent;
- whether observed issues remain within a recoverable post-publication correction range.

This continued observation does not approve production overwrite. Groq merged Markdown remains artifact-only until a later explicit adoption phase.

## Follow-Up Cleanup Decision

The `2026-06-12` artifact exposed production-blocker cleanup work that should happen before any adoption phase:

- add a numeric/unit guard so unsafe Groq conversions such as `RM1.42b` to `1.42億リンギット` fallback instead of being accepted;
- clean common RSS fallback dateline prefixes in Groq merged candidate artifacts;
- tighten Paul Tan gate/display behavior so EV registration rankings are not shown as JPJ driver-procedure items merely because JPJ appears as a data source.

These items are handled in Phase 2B.12A. This follow-up still does not approve Groq Markdown for `news/malaysia/`.

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
