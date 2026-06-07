# Phase 2B.10: Groq Accepted-Only Production Adoption Design

Date: 2026-06-07
Status: Design memo created. Production adoption is not implemented in this phase.

## Summary

Phase 2B.10 designs a future production path based on accepted-only Groq enhancement with RSS fallback.

This phase is docs-only. It does not implement production adoption, does not modify workflows, scripts, configs, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/`.

RSS-rendered Markdown remains the production output.

Groq output must not be written or committed to `news/malaysia/` in this phase.

Production adoption requires a later explicit implementation phase.

## Design Decision

Full-output Groq replacement is not the next adoption shape.

The preferred future path is accepted-only Groq enhancement with RSS fallback.

`llama-3.3-70b-versatile` remains the initial production candidate model.

Body enrichment remains off for the first adoption design.

`openai/gpt-oss-20b` remains comparison-only.

## Critical Constraints

`--accepted-only-markdown` is for artifact review only, not production output.

The current `--accepted-only-markdown` behavior must not be used as production output because it intentionally omits non-accepted RSS fallback items.

A future production path needs a separate merge mode that preserves all selected items.

If Groq has zero accepted items, production output must remain exactly the RSS-rendered Markdown.

Groq failure, missing `GROQ_API_KEY`, validation fallback, or zero accepted items must leave the RSS-rendered Markdown unchanged.

## Future Merge Design

Future production adoption should generate RSS Markdown and selected JSON first, exactly as the current production workflow does.

Optional Groq should run fail-open after RSS generation, using `selected_items.json`.

A future merge mode should combine Groq results with RSS-selected items:

- accepted Groq summaries replace only matching accepted items;
- non-requested items remain RSS-rendered;
- skipped items remain RSS-rendered;
- fallback items remain RSS-rendered;
- original selected item order is preserved;
- original category grouping is preserved;
- all selected items remain present in the final Markdown.

The future merge mode should be separate from `--accepted-only-markdown`, for example:

```text
--merge-accepted-with-rss-markdown
```

The exact flag name can be decided in the later implementation phase, but the behavior must preserve every selected item.

## Future Workflow Shape

RSS generation remains blocking and primary:

```bash
python3 -B scripts/malaysia_rss_summary.py \
  --include-paul-tan \
  --diagnostics \
  --output "${output_path}" \
  --json-output "${run_dir}/selected_items.json"
```

Groq enhancement remains optional and fail-open.

If a later phase approves production write behavior, the workflow should:

- preserve the original RSS Markdown as the fallback;
- write Groq-enhanced Markdown only after successful merge validation;
- commit only `news/malaysia/`;
- never commit Groq debug logs, improved-items JSON, or artifact files.

Pages index generation remains compatible with RSS-rendered output and must not depend on Groq artifacts.

## Readiness Inputs

Phase 2B.8 / 2B.9 pilot evidence:

| day | run | selected | requested | accepted | fallback | leakage |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Day1 | `27009168254` | 8 | 2 | 1 | 1 | none |
| Day2 | `27048530519` | 9 | 3 | 3 | 0 | none |
| Day3 | `27085547448` | 10 | 5 | 5 | 0 | none |

Aggregate:

- selected items reviewed: `27`;
- Groq requested: `10`;
- Groq accepted: `9`;
- Groq fallback: `1`;
- target dateline leakage: none found.

This evidence supports accepted-only enhancement with RSS fallback, not immediate full-output replacement.

## Future Acceptance Criteria

A later implementation phase should prove:

- default RSS-only production output remains unchanged when Groq is disabled;
- missing `GROQ_API_KEY` leaves output exactly RSS-rendered;
- zero accepted Groq items leaves output exactly RSS-rendered;
- accepted Groq items replace only their matching selected items;
- non-requested, skipped, and fallback items remain RSS-rendered;
- selected item order and category grouping are preserved;
- final Markdown still contains all selected items;
- Groq debug logs and improved-items JSON remain artifacts, not production files;
- final commit staging remains scoped to `news/malaysia/`.

## Verification

Expected added file:

```text
docs/malaysia_news_phase2b10_groq_accepted_only_production_adoption_design.md
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2B.10: no protected-path diff caused by this phase.
