# Phase 2B.13: Groq Merged Production Adoption Rehearsal

Date: 2026-06-12
Status: Local-only rehearsal added. Production overwrite is not approved in this phase.

## Summary

Phase 2B.13 adds a local-only rehearsal for the future Groq merged production path.

The rehearsal simulates a production overwrite sequence under `/tmp` only:

- generate RSS Markdown;
- generate selected JSON;
- run Groq merge mode;
- validate the merged candidate;
- write a rehearsal report.

RSS-rendered Markdown remains the current production output.

Groq merged Markdown must not be committed to `news/malaysia/` in Phase 2B.13.

Actual production overwrite requires a later explicit phase.

## Rehearsal Helper

The helper is:

```bash
python3.12 -B scripts/rehearse_malaysia_groq_merged_production.py
```

Default output directory:

```text
/tmp/malaysia_phase2b13_groq_merged_rehearsal/
```

Expected outputs:

- `rss.md`;
- `selected_items.json`;
- `groq_merged_candidate.md`;
- `production_candidate_rehearsal.md`;
- `groq_llama_improved_items.json`;
- `groq_stdout.log`;
- `groq_stderr.log`;
- `rehearsal_report.md`;
- `rehearsal_report.json`.

If `GROQ_API_KEY` is not available locally, the helper records that live Groq rehearsal was not executed and uses the RSS Markdown as the candidate fallback.

## Review Criteria

The rehearsal report should confirm:

- selected URL count equals rendered URL count;
- there are no missing or extra selected URLs;
- category headers, processed count, selected count, and failed-source line are present;
- Groq requested, accepted, and fallback counts are captured;
- target dateline strings are absent from the merged candidate;
- high-risk numeric/unit fallback messages are captured when present;
- no files are written to `news/malaysia/`.

## Production Boundary

Phase 2B.13 does not change:

- daily workflow behavior;
- Pages/index generation;
- source selection;
- Groq prompts;
- body enrichment behavior;
- production commit behavior.

The current daily workflow still commits RSS-rendered Markdown only.

Any later phase that writes Groq merged Markdown to `news/malaysia/${today}.md` must be explicitly approved.

## Verification

Expected checks:

```bash
python3.12 -m py_compile scripts/rehearse_malaysia_groq_merged_production.py scripts/render_malaysia_news_with_groq.py scripts/malaysia_rss_summary.py
python3.12 -B scripts/rehearse_malaysia_groq_merged_production.py
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.13: no workflow, config, Pages, or `news/malaysia/` production output changes.
