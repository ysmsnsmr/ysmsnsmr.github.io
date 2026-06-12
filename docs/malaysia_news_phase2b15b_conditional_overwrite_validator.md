# Phase 2B.15B: Conditional Overwrite Validator

Date: 2026-06-12
Status: Validator implemented. Production overwrite is not implemented in this phase.

## Summary

Phase 2B.15B adds a reusable validator for Groq merged production candidates.

The validator decides whether a merged candidate Markdown file is safe for a future phase to copy over:

```text
news/malaysia/${today}.md
```

This phase does not enable production overwrite. It does not modify the daily workflow, source selection, Groq prompts, Pages generation, or `news/malaysia/`.

RSS-rendered Markdown remains the current production output.

## Validator

The validator is:

```bash
python3.12 -B scripts/validate_malaysia_groq_merged_candidate.py \
  --selected-json <path>/selected_items.json \
  --candidate-markdown <path>/groq_merged_candidate.md \
  --improved-items-json <path>/groq_llama_improved_items.json \
  --rss-fallback-markdown <path>/rss.md \
  --status-output <path>/validator_status.json \
  --report-output <path>/validator_report.md
```

It exits `0` only when the candidate is safe for a later conditional overwrite step.

It exits nonzero when validation fails. A later production overwrite phase must treat that as fail-open to exact RSS Markdown.

## Validation Rules

The validator requires:

- selected JSON, candidate Markdown, RSS fallback Markdown, and improved-items JSON are readable;
- improved-items counts are parseable;
- Groq accepted count is greater than `0`;
- selected URL count equals rendered URL count;
- no selected URLs are missing;
- no extra rendered URLs are present;
- selected and rendered URL lists contain no duplicates;
- category headers are present;
- processed count, selected count, and failed-source line are present;
- target dateline and forbidden strings are absent:
  - `KUALA LUMPUR,`
  - `PUTRAJAYA,`
  - `GEORGE TOWN,`
  - `MELAKA,`
  - `— The`
  - `::inbox-item`
  - `The post`
  - `appeared first`
  - `Lowyat`
  - `lowyat`

If Groq accepted items exist but the candidate Markdown is byte-for-byte identical to RSS fallback Markdown, validation fails conservatively.

## Rehearsal Integration

`scripts/rehearse_malaysia_groq_merged_production.py` now includes the same validator result in:

- `rehearsal_report.json`;
- `rehearsal_report.md`.

This keeps local rehearsal and future workflow overwrite checks aligned.

If local `GROQ_API_KEY` is missing, the rehearsal remains non-production and uses RSS Markdown as the fallback candidate. The validator should fail overwrite eligibility because accepted count is `0`.

## Production Boundary

Phase 2B.15B is a validator implementation phase only.

It does not:

- add a workflow overwrite flag;
- copy Groq Markdown to `news/malaysia/`;
- commit Groq output;
- change Groq request targeting;
- change Groq prompt text;
- change Groq validation behavior;
- change RSS source selection.

Production overwrite wiring remains a later explicit phase.

## Test Plan

Static checks:

```bash
python3.12 -m py_compile scripts/validate_malaysia_groq_merged_candidate.py scripts/rehearse_malaysia_groq_merged_production.py
```

Fixture checks under `/tmp`:

- valid candidate with matching URLs and `accepted > 0` passes;
- `accepted = 0` fails;
- missing selected URL fails;
- extra rendered URL fails;
- target dateline leakage fails;
- missing count/header line fails;
- malformed improved-items JSON fails.

Rehearsal check:

```bash
python3.12 -B scripts/rehearse_malaysia_groq_merged_production.py
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result: no workflow, config, Pages, source-selection, or production output changes.
