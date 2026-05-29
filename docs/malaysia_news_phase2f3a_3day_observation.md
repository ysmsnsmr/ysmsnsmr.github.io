# Phase 2F.3A: Cleaned RSS Candidate Set 3-Day Observation

Date: 2026-05-29
Status: Local manual observation only. Do not automate or connect to production.

## Summary

Phase 2F.3A observes the cleaned Phase 2F RSS candidate set for three daily snapshots. The observation window is:

- Day 1: 2026-05-29
- Day 2: 2026-05-30
- Day 3: 2026-05-31

The cleaned `english_expansion_set` should use only:

- Malay Mail Malaysia
- Malay Mail Money
- iMoney Articles

The disabled candidates should remain visible but skipped:

- BERNAMA English
- The Edge Malaysia
- Harian Metro Mutakhir

## Manual Commands

Run one command per day from the repository root:

```bash
python3.12 -B scripts/experiment_observe_cleaned_rss_sources_3day.py --date 20260529
python3.12 -B scripts/experiment_observe_cleaned_rss_sources_3day.py --date 20260530
python3.12 -B scripts/experiment_observe_cleaned_rss_sources_3day.py --date 20260531
```

Default outputs:

- `/tmp/malaysia_rss_phase2f3a/rss_source_set_comparison_YYYYMMDD.json`
- `/tmp/malaysia_rss_phase2f3a/rss_source_set_comparison_memo_YYYYMMDD.md`
- `/tmp/malaysia_rss_phase2f3a/observation_index.json`

The index is updated by date. Re-running a date replaces that date's index entry.

## Per-Day Pass Criteria

Each daily snapshot should pass when:

- `english_expansion_set.feeds_enabled == 3`
- `english_expansion_set.disabled_feeds == 3`
- BERNAMA, The Edge, and Harian Metro are skipped.
- Bozo and error feed counts are `0`, unless the failure is clearly transient and affects an enabled feed.
- Expansion items come only from:
  - `malay_mail_malaysia`
  - `malay_mail_money`
  - `imoney_articles`

## What To Observe

For each day, review:

- item counts per set;
- item counts per enabled feed;
- duplicate URL counts;
- `current_set`-only URLs, especially Astro Awani-only public service, weather, education, or official-announcement items;
- `english_expansion_set`-only URLs, especially whether iMoney adds practical personal-finance or living-cost material.

For iMoney, useful topics include:

- petrol prices;
- MyKad or payment-card changes;
- microfinancing and government-backed financing;
- personal finance that affects households;
- cost-of-living or daily money-management topics.

Less useful iMoney topics include:

- generic product comparisons with no clear public-interest angle;
- bank product content that reads like commercial catalogue material;
- broad finance advice not tied to Malaysia daily life.

## Final 3-Day Review Criteria

After three snapshots, the cleaned candidate set can be considered stable enough for the next local experiment if:

- all three runs keep `english_expansion_set` at 3 enabled and 3 disabled feeds;
- enabled feeds fetch without repeated bozo/error states;
- iMoney contributes practical local personal-finance or living-cost items on at least two of the three days;
- removing Astro Awani from the expansion set does not repeatedly hide important public-service, weather, education, or official-announcement items that Malay Mail misses;
- duplicate URL counts remain manageable and do not obscure source-set differences.

Keep the cleaned candidate set local-only if:

- iMoney mostly contributes commercial catalogue content;
- Astro Awani-only items repeatedly contain important public-service information;
- Malay Mail Money noise increases enough that the finance caps would need another redesign;
- any enabled feed becomes unreliable over the observation window.

## Not In Scope

- Changing `scripts/malaysia_rss_summary.py`.
- Changing GitHub Actions or GitHub Pages.
- Changing `news/malaysia/index.html` generation.
- Adding Groq, Hy-MT2, or article-body fetching.
- Creating a Codex automation or scheduled workflow.
- Storing daily snapshot artifacts in the repository.
