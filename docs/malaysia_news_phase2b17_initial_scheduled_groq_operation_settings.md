# Phase 2B.17: Initial Scheduled Groq Production Operation Settings

Date: 2026-06-13
Status: Initial scheduled operation settings recorded.

## Summary

Phase 2B.17 records the recommended initial settings for daily scheduled Malaysia news operation after guarded Groq production overwrite was implemented.

The goal is conservative daily operation: use Groq merged output only through the Phase 2B.16 guarded opt-in path, keep RSS Markdown as the fail-open fallback, and move broad Groq targeting / body enrichment toward scheduled operation only after artifact evidence shows the failure modes are limited and correctable.

## Recommended Scheduled Repository Variables

Initial daily scheduled settings:

```text
MALAYSIA_NEWS_ENABLE_BODY_ENRICHMENT=false
MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=true
MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=true
MALAYSIA_NEWS_GROQ_MODEL=llama
MALAYSIA_NEWS_FORCE_ALL_GROQ=false
MALAYSIA_NEWS_DEBUG_GROQ=true
```

Equivalent manual dispatch settings:

```text
enable_body_enrichment=false
enable_groq_rendering=true
enable_groq_production_overwrite=true
groq_model=llama
force_all_groq=false
debug_groq=true
```

## Rationale

`enable_groq_rendering=true` and `enable_groq_production_overwrite=true` activate the guarded production path that was verified in Phase 2B.16.

`groq_model=llama` keeps the initial production model on `llama-3.3-70b-versatile`, which has the strongest current evidence.

`force_all_groq=false` remains the initial scheduled setting.

After the force-all strict accepted gate was added, `force_all_groq=true` is no longer treated as broad production acceptance. It is broad Groq exploration followed by a stricter accepted gate. Items that are only political background, market background, public-transport commentary without operational impact, or Paul Tan automotive noise should now fall back to RSS-rendered output.

Artifact run `27467402862` confirmed the intended shape after this gate refinement: `requested=4`, `accepted=1`, `fallback=3`; the accepted item was the concrete eCOSS subsidy item, while the KTM political/background item fell back with `transport_political_background_without_operational_impact`.

`enable_body_enrichment=false` is the conservative initial setting. Body enrichment has high fetch success and is becoming safer through body evidence cleanup and structured Groq input, but it still adds dependency, network, and evidence-policy complexity. It should remain optional until the cleaned evidence path has more artifact observations.

`debug_groq=true` should remain enabled during the initial scheduled observation period so fallback reasons, guard behavior, and validator evidence are visible in artifacts. It can be changed to `false` later if daily operation is stable.

## Operating Boundary

RSS Markdown is still generated first.

If Groq rendering fails, `GROQ_API_KEY` is missing, accepted count is `0`, validator fails, or copy fails, production output remains RSS-rendered Markdown.

Groq logs, selected JSON, improved-items JSON, validator reports, and optional diagnostics remain artifact-only.

Final commit staging remains limited to:

```bash
git add news/malaysia/
```

## Initial Observation Checklist

For the first scheduled runs with these settings, inspect artifacts for:

- `groq_rendering_status.txt: success`;
- `groq_production_overwrite_status.txt: applied` or a clear fail-open skip reason;
- validator `passed: true` when overwrite is applied;
- selected/rendered URL counts match;
- no forbidden/dateline matches in the merged candidate;
- Groq requested / accepted / fallback counts;
- accepted item Japanese quality;
- fallback reasons for rejected items;
- whether any post-publication correction was needed.

## Future Changes

Body enrichment and `force_all_groq=true` may be moved into scheduled operation after more artifact evidence using cleaned `body_evidence` input and the strict force-all accepted gate.

`force_all_groq=true` should remain manual-observation only until 2-3 additional dispatch runs confirm that broader targeting improves quality without adding generic or low-value accepted items.

`debug_groq=false` can be considered after the initial observation period if artifacts show stable guard and validator behavior.

## Production Reflection Roadmap

The current path to scheduled production reflection is staged rather than a single variable flip.

1. Freeze the current implementation and evidence:
   - force-all strict accepted gate;
   - transport political/background fallback;
   - eCOSS protected scheme-name display;
   - body evidence focus to `life_impact` validation.

2. Run 2-3 manual dispatch observations with:

   ```text
   enable_body_enrichment=true
   enable_groq_rendering=true
   enable_groq_production_overwrite=true
   groq_model=llama
   force_all_groq=true
   debug_groq=true
   ```

3. Promote to scheduled repository variables only if artifacts show:
   - workflow success;
   - validator pass;
   - selected/rendered URL counts match;
   - no forbidden/dateline matches;
   - accepted items are limited to concrete life-impact items such as subsidy, procedure, payment, public-service, or real transport-operation impacts;
   - KTM/political background, market background, and Paul Tan noise do not become accepted items;
   - failures remain fail-open to RSS Markdown.

4. If accepted, switch scheduled variables to:

   ```text
   MALAYSIA_NEWS_ENABLE_BODY_ENRICHMENT=true
   MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=true
   MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=true
   MALAYSIA_NEWS_GROQ_MODEL=llama
   MALAYSIA_NEWS_FORCE_ALL_GROQ=true
   MALAYSIA_NEWS_DEBUG_GROQ=true
   ```

5. Observe at least 3 scheduled runs after the switch. Roll back by repository variables if needed:
   - first rollback: `MALAYSIA_NEWS_FORCE_ALL_GROQ=false`;
   - body evidence rollback: `MALAYSIA_NEWS_ENABLE_BODY_ENRICHMENT=false`;
   - Groq rendering rollback: `MALAYSIA_NEWS_ENABLE_GROQ_RENDERING=false`;
   - overwrite rollback: `MALAYSIA_NEWS_ENABLE_GROQ_PRODUCTION_OVERWRITE=false`.

The decision standard is not perfect output. The standard is that known failure modes are observable, bounded, fail open to RSS, and correctable after publication if needed.
