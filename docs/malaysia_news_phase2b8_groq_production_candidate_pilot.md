# Phase 2B.8: Groq Production Candidate Pilot

Date: 2026-06-04
Status: Pilot memo created. Production adoption is not approved in this phase.

## Summary

Phase 2B.8 starts a production-candidate evidence pilot for Groq-rendered Malaysia news Markdown.

This phase does not approve or perform production replacement.

RSS-rendered Markdown remains production output.

Groq output remains artifact-only / optional / verification-only.

Groq output must not be committed to `news/malaysia/`.

Production adoption requires a later explicit phase.

The pilot uses the existing Phase 2E.7 optional Groq path and reviews Groq Markdown only as downloaded artifact output.

## Background

Phase 2B.7 deferred Groq production adoption because the evidence was still limited and final RSS-vs-Groq quality review was incomplete.

Phase 2B.8 keeps that deferral in force while shifting the next work toward structured production-candidate evidence gathering.

The goal is to collect several days of artifact evidence before making any later production adoption decision.

## Initial Pilot Configuration

Initial production candidate:

```text
model: llama-3.3-70b-versatile
body enrichment: off
review window: 3 manual observation days
workflow path: Phase 2E.7 optional Groq path
```

Manual dispatch inputs:

```text
enable_body_enrichment=false
enable_groq_rendering=true
groq_model=llama
force_all_groq=false
debug_groq=true
```

`openai/gpt-oss-20b` remains a later comparison candidate, but it is not the initial production candidate for this pilot.

Phase 2E.9 accepted-only Markdown cleanup is the expected artifact baseline. Candidate Groq Markdown should render only Groq-accepted items, while non-accepted items remain available in JSON and logs.

## Daily Review Fields

For each manual observation day, record:

- run id;
- downloaded artifact path;
- selected item count;
- Groq requested / accepted / fallback counts;
- `groq_json_input.txt` target;
- `groq_llama.md` presence;
- accepted-only Markdown confirmation;
- dateline leakage result;
- RSS vs Groq readability notes;
- RSS vs Groq factual-safety notes;
- confirmation that Groq output stayed under `${RUNNER_TEMP}` / downloaded artifacts;
- confirmation that no Groq output was committed to `news/malaysia/`.

## Pilot Interpretation

This pilot gathers evidence for a later decision. It does not define production adoption success by itself.

A promising pilot should show:

- optional Groq rendering succeeds or fails open;
- accepted-only Groq Markdown is easy to review;
- no target dateline leakage appears in candidate Markdown;
- Groq summaries do not introduce factual drift against RSS-rendered Markdown;
- Japanese readability is meaningfully better than, or at least not worse than, RSS-rendered Markdown;
- production RSS Markdown remains unaffected.

If the 3-day pilot is promising, a later phase may compare candidate artifacts against production RSS output and decide whether to continue with `llama-3.3-70b-versatile`, add `openai/gpt-oss-20b` comparison runs, or defer adoption again.

## Boundaries

Phase 2B.8 is docs-first and documentation-only.

No workflow dispatch is performed in this phase.

This phase does not modify:

- workflows;
- scripts;
- config;
- Pages/index generation;
- source selection;
- Groq prompts;
- body enrichment behavior;
- `news/malaysia/`.

RSS-rendered Markdown remains production output.

Groq output remains artifact-only / optional / verification-only.

Groq output must not be committed to `news/malaysia/`.

Production adoption requires a later explicit phase.

## Verification

Expected added file:

```text
docs/malaysia_news_phase2b8_groq_production_candidate_pilot.md
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.8: no protected-path diff caused by this phase.
