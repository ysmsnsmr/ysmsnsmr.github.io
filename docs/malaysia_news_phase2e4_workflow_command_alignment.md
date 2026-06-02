# Phase 2E.4: Production Workflow Command Alignment

## Summary

Phase 2E.4 confirms that the current daily production workflow command is aligned with the Phase 2G Paul Tan production adoption path and the Phase 2E.3 local rehearsal scope.

This phase is documentation-only. It does not change scripts, workflows, config, Pages output, or `news/malaysia/`.

## Current Production Command

The daily workflow currently generates the Malaysia RSS summary with:

```bash
python3 -B scripts/malaysia_rss_summary.py --include-paul-tan --diagnostics --output "${output_path}"
```

This command is in `.github/workflows/malaysia-rss-summary.yml`.

## Alignment Notes

The command is aligned with Phase 2G because:

- it explicitly passes `--include-paul-tan`;
- Paul Tan remains behind the source-specific gate in `scripts/malaysia_rss_summary.py`;
- Paul Tan remains capped at `1` selected item;
- Paul Tan `review` and `reject` gate decisions remain excluded from selection;
- Lowyat.NET is not referenced in the production workflow.

The command is aligned with Phase 2E.3 because:

- it is the same production-style RSS summary command rehearsed locally;
- it generates RSS Markdown from RSS metadata only;
- it does not invoke article body enrichment;
- it does not invoke Groq rendering;
- it does not invoke the manual Groq verification workflow.

## Existing Pages Step

The workflow still runs:

```bash
python3 -B scripts/build_malaysia_news_index.py
```

This remains the existing Pages index build step after RSS Markdown generation. Phase 2E.4 does not change that behavior.

## Out Of Scope

Phase 2E.4 does not test or connect:

- article body excerpt enrichment;
- Groq enriched rendering;
- manual Groq verification;
- Lowyat.NET production adoption;
- any new RSS source configuration.

## Verification

Observed workflow command:

```bash
python3 -B scripts/malaysia_rss_summary.py --include-paul-tan --diagnostics --output "${output_path}"
```

Observed follow-up Pages index command:

```bash
python3 -B scripts/build_malaysia_news_index.py
```

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result for Phase 2E.4: no diff caused by this phase.

