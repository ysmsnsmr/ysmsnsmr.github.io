# Phase 2F.3A: Cleaned RSS Candidate Set 3-Day Observation Review

Date: 2026-05-31  
Status: Completed. Local-only observation. Do not connect to production yet.

## Summary

Phase 2F.3A observed the cleaned Phase 2F RSS candidate set across three daily snapshots:

- Day 1: 2026-05-29
- Day 2: 2026-05-30
- Day 3: 2026-05-31

The purpose was to verify whether the cleaned English expansion set is technically stable and whether replacing Astro Awani National with iMoney Articles is directionally useful for the Malaysia news project.

The observation remained local-only. It did not change:

- `scripts/malaysia_rss_summary.py`
- GitHub Actions
- GitHub Pages
- `news/malaysia/index.html` generation
- Groq rendering
- article body fetching

Daily JSON and memo outputs were written under `/tmp/malaysia_rss_phase2f3a/`.

## Observed Source Sets

### Current Set

The current comparison baseline remained:

- `malay_mail_malaysia`
- `malay_mail_money`
- `astro_awani_national`

### Cleaned English Expansion Set

The cleaned candidate set remained:

- `malay_mail_malaysia`
- `malay_mail_money`
- `imoney_articles`

The following candidates remained visible but disabled/skipped:

- `bernama_english`
- `the_edge_malaysia`
- `harian_metro_mutakhir`

## Technical Result

The cleaned set passed the local observation checks.

Across the observed runs, the expected structure remained stable:

- `current_set`: 3 enabled feeds
- `english_expansion_set`: 3 enabled feeds
- `english_expansion_set`: 3 disabled feeds
- BERNAMA, The Edge, and Harian Metro remained skipped
- Bozo/error counts stayed at 0 for the enabled feeds
- No Groq API or article body fetching was used

The Day 3 run confirmed the same expected structure:

| set | enabled feeds | items | bozo feeds | error feeds | disabled |
| --- | ---: | ---: | ---: | ---: | ---: |
| current_set | 3 | 125 | 0 | 0 | 0 |
| english_expansion_set | 3 | 130 | 0 | 0 | 3 |

## Stable Difference Pattern

The source-set difference remained clear and stable:

| comparison | count |
| --- | ---: |
| Shared URLs | 100 |
| Current set only | 25 |
| English expansion set only | 30 |
| Duplicate URL count between sets | 100 |

The practical source difference is:

- Remove `astro_awani_national`: `-25` items
- Add `imoney_articles`: `+30` items
- Keep `malay_mail_malaysia`: unchanged
- Keep `malay_mail_money`: unchanged

This means Phase 2F.3A effectively tested:

> Astro Awani National as a Malay-language local/news auxiliary source  
> versus  
> iMoney Articles as an English personal-finance/living-cost candidate.

## Content Review

### Malay Mail Malaysia

Malay Mail Malaysia remains suitable as the primary English Malaysia general-news source.

It continues to provide:

- local public-interest news;
- weather and safety items;
- politics and national affairs;
- lifestyle/cultural context;
- incident and public-service-adjacent items.

In the Day 3 sample, Malay Mail Malaysia included a MetMalaysia thunderstorm warning and a missing-hiker update, showing that it can still capture some public-safety material without relying only on Astro Awani.

Decision: keep as primary.

### Malay Mail Money

Malay Mail Money remains technically stable but still needs finance/topic caps.

It provides useful economic context such as:

- ringgit;
- Bursa;
- banking;
- BNM/corporate finance;
- cost-of-living-adjacent finance.

However, it also includes:

- broad market news;
- corporate finance;
- overseas economic items;
- IPO and investment noise.

Decision: keep with existing finance and currency caps. Do not broaden finance exposure just because the feed is stable.

### iMoney Articles

iMoney Articles fetched consistently and added 30 expansion-only URLs.

Useful observed topics include:

- petrol prices;
- RON95, RON97, and diesel updates;
- MyKad/payment-card related material;
- microfinancing;
- personal financing;
- household money-management topics.

However, iMoney also includes product-comparison and loan-comparison content. Some items are useful for household/living-cost awareness, but others may read like bank product catalogue material.

Decision: conditionally keep as a living-cost/personal-finance candidate, not as a broad news source.

Recommended role:

- `english_living_money_candidate`
- suitable for `知っておくと得`
- suitable for living-cost alerts only when the title/description clearly supports public-interest or household relevance

Do not treat all iMoney items as automatically useful.

### Astro Awani National

Astro Awani fetched cleanly in the current set and contributed 25 current-set-only URLs.

It remains useful as a Malay-language source for:

- local public-service items;
- weather and disaster information;
- education and official-announcement items;
- Malay-language local context;
- items that may appear earlier or only in Malay-language media.

However, it also adds:

- Malay-to-Japanese translation burden;
- incident and politics noise;
- local items that are not always useful for the project’s target output.

The Day 3 sample included an item about the Strait of Hormuz and Malaysia-related risks to oil, gas, plastics, and other products. This suggests Astro Awani should not be deleted outright, because it may catch Malay-language economic/public-impact items.

Decision: demote from primary/default role, but keep as auxiliary/fallback or Malay local public-service watch.

## Final Decision

Phase 2F.3A is considered completed and technically successful.

The cleaned set is stable enough for the next local experiment, but it should not be connected to production yet.

Recommended source posture:

| Source | Decision | Role |
| --- | --- | --- |
| Malay Mail Malaysia | Keep | Primary English general-news source |
| Malay Mail Money | Keep with caps | Finance/economy source with noise controls |
| iMoney Articles | Conditional keep | Living-cost/personal-finance candidate |
| Astro Awani National | Demote, do not delete | Malay auxiliary/fallback/local public-service watch |
| BERNAMA English | Hold | Official source candidate pending valid RSS endpoint |
| The Edge Malaysia | Hold/reject current URL | Business RSS candidate not validated |
| Harian Metro Mutakhir | Keep disabled | Low-priority Malay experimental fallback |

## Recommendation

Do not immediately replace production RSS sources.

Instead:

1. Keep the current production behavior unchanged for now.
2. Treat the cleaned set as technically validated in local observation.
3. Continue Phase 2F.4 candidate backlog observation separately.
4. After Phase 2F.4, decide whether any additional source is better than or complementary to iMoney.
5. If source redesign proceeds, introduce changes behind a separate local/prototype path first, not directly into production workflow.

## Next Phase

Recommended next work:

### Phase 2F.4

Continue observing candidate backlog sources separately:

- Malay Mail World
- Free Malaysia Today
- Lowyat.NET
- Paul Tan
- SAYS Malaysia, currently held due to RSS parse error

### Future Phase 2F.5

If Phase 2F.4 identifies a strong candidate, compare:

- cleaned set plus iMoney only;
- cleaned set plus one additional candidate;
- Astro Awani auxiliary behavior;
- final selection quality after existing category caps/noise gates.

## Not In Scope

This review does not authorize:

- changing production RSS feeds;
- editing `scripts/malaysia_rss_summary.py`;
- changing GitHub Actions;
- changing GitHub Pages output;
- adding Groq, Hy-MT2, or article body fetching to this RSS observation;
- deleting disabled candidate sources from the audit trail.
