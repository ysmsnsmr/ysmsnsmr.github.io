# Phase 2F.5: Cleaned RSS Set v2 Comparison

Date: 2026-05-31
Status: Local-only comparison. Do not connect to production.

## Summary

Phase 2F.5 compares the stable cleaned RSS set v1 with a v2 candidate that adds only Paul Tan and Lowyat.NET. The purpose is to see whether these two niche sources add practical local-life signal without overwhelming the feed with product or enthusiast noise.

This comparison uses only RSS metadata:

- title
- description
- link
- published

No Groq, article body fetching, production RSS changes, GitHub Actions changes, Pages changes, or `scripts/malaysia_rss_summary.py` changes are allowed.

## Source Sets

v1:

- Malay Mail Malaysia
- Malay Mail Money
- iMoney Articles

v2:

- Malay Mail Malaysia
- Malay Mail Money
- iMoney Articles
- Paul Tan
- Lowyat.NET

Hold:

- Free Malaysia Today
- Malay Mail World
- SAYS Malaysia
- BERNAMA English
- The Edge Malaysia
- Harian Metro Mutakhir

Hold candidates are listed in the output for auditability, but they are not fetched by the Phase 2F.5 helper.

## Manual Command

Run from the repository root:

```bash
python3.12 -B scripts/experiment_compare_cleaned_rss_set_v2.py --date 20260531
```

Default outputs:

- `/tmp/malaysia_rss_phase2f5/cleaned_rss_v2_comparison_20260531.json`
- `/tmp/malaysia_rss_phase2f5/cleaned_rss_v2_comparison_memo_20260531.md`
- `/tmp/malaysia_rss_phase2f5/observation_index.json`

Daily snapshots are not stored in the repository.

## What The Helper Compares

For v1 and v2:

- item counts;
- feed health and bozo/error states;
- duplicate URLs within each set;
- `life_impact_candidate`, `likely_noise`, `mixed`, and `unclear` counts;
- item counts and fit counts by feed.

For v1 vs v2:

- shared URL count;
- only-in-v1 URL count;
- only-in-v2 URL count;
- source deltas by feed.

## Source-Specific Filter Assumptions

Paul Tan should be treated as useful only for transport or driver-impact items, such as:

- LRT or public transport disruptions;
- JPJ or enforcement changes affecting drivers;
- roads, tolls, petrol, MyKad verification, public transport, or safety/recall notices.

Paul Tan likely noise includes:

- car launches;
- sales events;
- reviews;
- model pricing with no public-service angle;
- plant or industry-capacity stories with no direct user impact.

Lowyat.NET should be treated as useful only for public tech-life items, such as:

- telco/public internet;
- MyKad;
- payments;
- fuel subsidy;
- Touch 'n Go;
- public transport tech;
- government digital services.

Lowyat.NET likely noise includes:

- laptops;
- phones;
- gaming;
- product launches;
- gadget reviews;
- overseas tech.

## Interpretation Rules

Do not promote v2 to any production or cleaned-set config based on a single run.

Useful signal would look like:

- Paul Tan and Lowyat.NET fetch cleanly.
- Added feeds do not create duplicate noise against v1.
- Only-in-v2 items include repeated practical transport, payment, fuel, telco, or government-service items.
- Source-specific filters can separate useful items from product noise with simple RSS metadata.

Weak signal would look like:

- Most only-in-v2 items are launches, reviews, sales, gadgets, or enthusiast content.
- Added feeds require article-body fetching to understand relevance.
- Added feeds are unstable or create repeated bozo/error states.
- The extra source-specific filtering would outweigh the benefit.

## Not In Scope

- Editing `config/malaysia_news_feeds_phase2f.yml`.
- Editing `scripts/malaysia_rss_summary.py`.
- Editing GitHub Actions or Pages.
- Running Groq.
- Fetching article bodies.
- Storing daily snapshots in the repository.
