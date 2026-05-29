# Phase 2F.1: RSS Source Candidate Review

Date: 2026-05-29
Status: RSS source redesign remains local-only. Do not connect to production yet.

## Summary

Phase 2F.0 compared the current Malaysia RSS source set with an English-expanded candidate set before any Phase 2E.3 workflow integration. The run showed that the English expansion can add useful local personal-finance material through iMoney, but the current BERNAMA and The Edge RSS candidates are not ready.

Current recommendation:

- Keep Malay Mail Malaysia as the primary English general-news source.
- Keep Malay Mail Money, with the existing finance and currency caps still required.
- Treat iMoney Articles as a conditional candidate for local personal-finance and living-cost observation.
- Demote Astro Awani National from primary candidate to Malay-language auxiliary/fallback candidate, but do not remove it yet.
- Keep BERNAMA English on hold until its RSS URL or parser handling is fixed.
- Reject or hold the current The Edge Malaysia RSS URL candidate because it produced no RSS items.
- Keep Harian Metro disabled as a low-priority Malay experimental fallback.

## Observed Phase 2F.0 Run

Input artifacts:

- `/tmp/rss_source_set_comparison.json`
- `/tmp/rss_source_set_comparison_memo.md`

Run metadata:

- Generated at: `2026-05-29T19:00:57.076849+08:00`
- Per-feed limit: `50`
- Groq API: not used
- Article body fetching: not used

Set-level results:

| set | enabled feeds | items | duplicate URLs | bozo feeds | error feeds | disabled |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current_set | 3 | 125 | 0 | 0 | 0 | 0 |
| english_expansion_set | 5 | 130 | 0 | 2 | 2 | 1 |

Set difference:

- Shared URLs: `100`
- Only in `current_set`: `25`
- Only in `english_expansion_set`: `30`
- Duplicate URL count between sets: `100`

## Feed Health

| set | id | name | enabled | items | bozo | observed error |
| --- | --- | --- | --- | ---: | --- | --- |
| current_set | `malay_mail_malaysia` | Malay Mail Malaysia | true | 50 | false | - |
| current_set | `malay_mail_money` | Malay Mail Money | true | 50 | false | - |
| current_set | `astro_awani_national` | Astro Awani National | true | 25 | false | - |
| english_expansion_set | `malay_mail_malaysia` | Malay Mail Malaysia | true | 50 | false | - |
| english_expansion_set | `bernama_english` | BERNAMA English | true | 0 | true | XML parse failed: invalid token; lenient parse also failed |
| english_expansion_set | `malay_mail_money` | Malay Mail Money | true | 50 | false | - |
| english_expansion_set | `imoney_articles` | iMoney Articles | true | 30 | false | - |
| english_expansion_set | `the_edge_malaysia` | The Edge Malaysia | true | 0 | true | no RSS item elements found |
| english_expansion_set | `harian_metro_mutakhir` | Harian Metro Mutakhir | false | 0 | false | disabled |

External candidate context checked during planning:

- BERNAMA English RSS candidate: `https://www.bernama.com/en/index.php/rssfeed.php`
- BERNAMA category RSS-like candidate: `https://bernama.com/en/index.php/world/general/rssfeed.php`
- The Edge Malaysia: `https://theedgemalaysia.com/`
- iMoney feed listing: `https://rss.feedspot.com/malaysia_personal_finance_rss_feeds/`

These references are only source-candidate context. They are not production dependencies.

## Candidate Decisions

### Malay Mail Malaysia

Decision: keep as primary English general source.

Reasoning:

- The feed fetched cleanly in both source sets.
- It contributes the main English Malaysia news coverage already used by the production line.
- It contains some crime and politics noise, but that is already handled by selection and noise gates rather than by dropping the feed.

Production implication: no source change needed.

### Malay Mail Money

Decision: keep, with existing finance and currency caps.

Reasoning:

- The feed fetched cleanly in both source sets.
- It remains useful for ringgit, Bursa, BNM, banking, and cost-of-living-adjacent finance.
- The sample still contains overseas market, corporate, IPO, and broad finance noise, so caps and filters remain essential.

Production implication: no source change needed. Do not broaden finance exposure just because this feed is reliable.

### iMoney Articles

Decision: conditionally adopt for local personal-finance and living-cost observation; not as broad news.

Reasoning:

- The feed fetched cleanly and added `30` URLs unique to the English expansion set.
- Sample items include petrol prices, personal financing, MyKad/Touch 'n Go, microfinancing, and money-management topics.
- This is closer to household-facing practical information than a general business-news feed.
- It also includes product and loan comparison content, so selection must treat it as practical/living-cost material only when the RSS title or description clearly supports that.

Production implication: suitable for a later local experiment or candidate branch, but not yet connected to the production RSS line.

### Astro Awani National

Decision: demote from primary candidate to Malay-language auxiliary/fallback candidate; do not remove yet.

Reasoning:

- The feed fetched cleanly and contributed `25` current-set-only URLs.
- It provides Malay-language coverage that can catch local public-service, weather, education, and official-announcement items.
- It also increases BM translation burden and includes incident/politics noise.
- The Phase 2F goal is to evaluate moving Malay-language RSS from main source to support/experimental role, and this run supports that direction without proving removal is safe.

Production implication: keep current production behavior unchanged for now. In future source redesign, test Astro as auxiliary rather than default primary.

### BERNAMA English

Decision: hold.

Reasoning:

- The current candidate URL returned `0` parsed items.
- The feed was marked bozo with an XML parse error: invalid token; lenient parsing also failed.
- BERNAMA may still be valuable as an official/national English source, but Phase 2F.0 did not validate a usable RSS input path.

Production implication: do not adopt until Phase 2F.2 finds a valid URL or implements a deliberately scoped parser fix.

### The Edge Malaysia

Decision: hold or reject the current RSS URL candidate.

Reasoning:

- The current candidate URL returned `0` RSS items.
- The script observed `no RSS item elements found`.
- Even if a valid feed is later found, The Edge is likely to skew toward markets, companies, and investing, which may duplicate or worsen Malay Mail Money noise.

Production implication: do not adopt the current URL. Reconsider only if Phase 2F.2 finds a stable RSS endpoint and a narrow reason to include it.

### Harian Metro Mutakhir

Decision: keep disabled as low-priority Malay experimental fallback.

Reasoning:

- It was intentionally disabled and was not fetched.
- It remains useful only as a possible Malay-language stress test or emergency fallback, not as an English-expansion source.

Production implication: no production use.

## Phase 2E.3 Implication

Do not advance workflow integration based on RSS source redesign yet.

Phase 2E.3 can still rehearse the current production-adjacent line, but RSS source redesign should remain separate until one of these is true:

- BERNAMA and The Edge candidates are fixed and re-tested, or
- BERNAMA and The Edge are explicitly dropped from the English expansion set, leaving a smaller validated candidate set of Malay Mail Malaysia, Malay Mail Money, and iMoney Articles, with Astro Awani as auxiliary/fallback.

## Phase 2F.2 Recommendation

The next RSS-source step should be a focused candidate cleanup, not production integration.

Recommended Phase 2F.2 tasks:

1. Investigate BERNAMA English RSS alternatives or parser handling using only title, description, link, and published fields.
2. Investigate whether The Edge has a real RSS endpoint; if not, formally drop it from the candidate set.
3. Re-run the comparison with a smaller validated English expansion set.
4. Add a memo comparing source quality, not just fetch health, for iMoney and Astro Awani auxiliary value.

## Not In Scope

- Changing `scripts/malaysia_rss_summary.py`.
- Changing GitHub Actions, Pages, or `news/malaysia/index.html` generation.
- Adding Groq, Hy-MT2, or article-body fetching to RSS source review.
- Treating Phase 2F.1 decisions as live production source changes.
