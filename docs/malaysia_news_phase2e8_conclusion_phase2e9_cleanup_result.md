# Phase 2E.8 Conclusion and Phase 2E.9 Cleanup Result

Date: 2026-06-04
Status: Documentation-only result memo.

## Summary

This memo records the Phase 2E.8 optional Groq artifact review conclusion and the Phase 2E.9 artifact Markdown cleanup result.

No workflows, scripts, config, Pages output, Groq prompts, body enrichment behavior, source selection, or `news/malaysia/` files are changed by this memo.

## Phase 2E.8 Conclusion

Phase 2E.8 remains an artifact-only review path.

Available evidence confirms that the optional Groq path can run successfully without blocking RSS production output across the 3 manual observation days:

- Groq-only run `26808794435` succeeded with `requested=1`, `accepted=1`, `fallback=0`;
- body enrichment plus Groq run `26809210928` succeeded with `requested=1`, `accepted=1`, `fallback=0`;
- Day 2 body enrichment plus Groq run `26879809470` succeeded with `selected=10`, `enriched=10`, `body_fetched=7`, `body_excerpt_used=6`, `requested=5`, `accepted=4`, `fallback=1`;
- Day 3 body enrichment plus Groq run `26947998995` succeeded with `selected=8`, `enriched=8`, `body_fetched=7`, `body_excerpt_used=6`, `requested=1`, `accepted=1`, `fallback=0`;
- body enrichment plus Groq used `selected_items_enriched.json`;
- Groq output stayed in artifacts / `${RUNNER_TEMP}`;
- no Groq Markdown was committed to `news/malaysia/`.

Day 2 had no target dateline leakage in Groq Markdown.

Day 3 exposed dateline leakage in non-accepted RSS fallback items inside Groq artifact Markdown. This was a review-surface problem rather than a Groq-accepted-summary problem, and it led to the Phase 2E.9 accepted-only cleanup.

Conclusion: the optional Groq artifact path is useful and operationally stable enough for continued artifact review, but still not sufficient for production adoption.

Reasons:

- multi-day evidence now exists, but accepted Groq item counts are still small;
- Day 3 showed that mixed accepted/non-accepted artifact Markdown was too easy to misread before cleanup;
- RSS Markdown vs Groq Markdown factual-safety and usefulness review remains the deciding step;
- production adoption remains deferred.

## Phase 2E.9 Cleanup Result

Phase 2E.9 cleaned up optional Groq artifact Markdown so it renders only Groq-accepted items.

Result:

- non-accepted RSS fallback items are no longer mixed into Groq artifact Markdown;
- accepted item order follows the original selected item order;
- when accepted count is `0`, Markdown shows a short notice only;
- selected/enriched JSON still preserves the full selected item set;
- improved-items JSON still preserves requested / accepted / fallback counts and accepted records;
- Groq request targeting, validation, fallback decisions, and prompts remain unchanged.

This makes the Groq Markdown artifact a focused review surface for accepted Groq improvements only.

Phase 2E.9 post-push run `26948966282` confirmed the cleanup:

- accepted-only Groq Markdown was generated;
- requested `1`, accepted `1`, fallback `0`;
- no target dateline leakage was found;
- Groq output remained artifact-only and was not committed to `news/malaysia/`.

## Current Boundary

RSS-rendered Markdown remains the production output.

Groq production adoption remains deferred.

Groq rendering remains artifact-only, optional, and verification-only.

Groq output must not be committed to `news/malaysia/`.

Production adoption requires a later explicit phase.

## Next Review Step

Continue collecting Phase 2E.8 optional Groq artifacts manually as needed, now using accepted-only Groq Markdown as the review surface.

Future review should compare accepted-only Groq Markdown against RSS-rendered Markdown for:

- factual safety;
- Japanese readability;
- dateline leakage;
- guard fallback behavior;
- usefulness over the current RSS-rendered output.

## Verification

Expected protected diff check:

```bash
git diff -- .github/workflows scripts/malaysia_rss_summary.py scripts/render_malaysia_news_with_groq.py scripts/enrich_malaysia_selected_items_with_body.py scripts/build_malaysia_news_index.py config/malaysia_news_feeds_phase2f.yml news/malaysia
```

Expected result: no protected-path diff caused by this memo.
