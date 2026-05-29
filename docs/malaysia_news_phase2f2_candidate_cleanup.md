# Phase 2F.2: RSS Candidate Cleanup

Date: 2026-05-29
Status: Local candidate cleanup only. Do not connect to production.

## Summary

Phase 2F.2 narrows the English expansion RSS experiment after the Phase 2F.0 run and Phase 2F.1 review. The goal is to keep validated RSS inputs enabled, while leaving failed or unvalidated candidates visible but disabled.

This cleanup does not change:

- `scripts/malaysia_rss_summary.py`
- GitHub Actions
- GitHub Pages
- `news/malaysia/index.html` generation
- Groq rendering
- article body fetching

## Cleanup Decision

Enabled in `english_expansion_set`:

- `malay_mail_malaysia`
- `malay_mail_money`
- `imoney_articles`

Disabled in `english_expansion_set`:

- `bernama_english`
- `the_edge_malaysia`
- `harian_metro_mutakhir`

The YAML schema remains unchanged. Each feed still has exactly:

- `id`
- `name`
- `url`
- `language`
- `source_type`
- `role`
- `priority`
- `enabled`

## Candidate Notes

### BERNAMA English

Decision: disabled, held for later investigation.

Updated metadata:

- `role: official_source_hold`
- `priority: low`
- `enabled: false`

Reasoning:

- In Phase 2F.0, the configured BERNAMA URL returned `0` parsed items.
- The feed was marked bozo with an XML parse error, and lenient parsing also failed.
- Planning context showed a separate `https://rss.bernama.com/` landing page and that the current `https://www.bernama.com/en/index.php/rssfeed.php` candidate behaves like an HTML news page rather than a clean RSS item feed.
- BERNAMA may still be useful as an official English source, but Phase 2F.2 should not add HTML parsing or guess new endpoint behavior.

Return condition:

- Re-enable only after a valid BERNAMA RSS endpoint is found and verified with title, description, link, and published fields.

### The Edge Malaysia

Decision: disabled, current RSS URL candidate rejected.

Updated metadata:

- `role: rejected_business_feed_candidate`
- `priority: low`
- `enabled: false`

Reasoning:

- In Phase 2F.0, `https://theedgemalaysia.com/feed` returned `0` RSS items.
- The script observed `no RSS item elements found`.
- Planning context showed The Edge homepage content but did not validate a real RSS item endpoint.
- Even with a valid feed, The Edge is likely to increase business, markets, and investing noise unless there is a narrow local-life reason to include it.

Return condition:

- Reconsider only if a stable RSS endpoint is found and the source has a clear role not already covered by Malay Mail Money.

### iMoney Articles

Decision: keep enabled as the validated personal-finance/living-cost candidate.

Reasoning:

- In Phase 2F.0, iMoney fetched cleanly and contributed `30` items.
- Sample topics included petrol prices, MyKad/Touch 'n Go, microfinancing, personal financing, and money management.
- It should remain a local experiment candidate, not a broad news source.

## Expected Post-Cleanup Run Shape

After rerunning `scripts/experiment_compare_rss_source_sets.py`:

- `english_expansion_set` should have `3` enabled feeds and `3` disabled feeds.
- BERNAMA, The Edge, and Harian Metro should be skipped, not fetched.
- Expansion items should come from Malay Mail Malaysia, Malay Mail Money, and iMoney only.
- Bozo and error feed counts should be `0` unless a still-enabled feed fails during the run.

## Next Recommendation

Phase 2F.3, if needed, should be a BERNAMA-specific RSS endpoint investigation. It should stay separate from the source-set comparison and should not add HTML scraping to the RSS comparison script.

The cleaned candidate set is now suitable for another local-only source comparison, but not for production workflow integration.
