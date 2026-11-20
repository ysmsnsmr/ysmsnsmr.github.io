# Malaysia News Budgets

From the next scheduled update after the November 20, 2026 configuration change:

- Jev publication budget: at most 40 eligible articles.
- Candidate-pool `post_relevance_policy.target_card_count`: 40.
- Editorial summary generation cap: 40, including the scheduled workflow's
  explicit `MALAYSIA_NEWS_EDITORIAL_REQUEST_CAP` value.
- Existing per-article model, token limits, repairs and safety checks remain.
- Disaster and political-statement grouping still uses one shared classification
  request. Its existing 100-article input bound covers 40; its token/time limits
  remain unchanged.

The budget is a maximum, not a quota. Relevance, freshness and redundancy checks
can yield fewer articles. Existing RSS-only fallback behavior and the event
comparison cohort limit are unchanged. No already-published Markdown or HTML is
regenerated for this configuration change. The first real scheduled 40-item run
must still be observed for duration, token usage, fallbacks and grouping quality.

`scripts/test_malaysia_news_budget.py` checks agreement across configuration
sources. Boundary tests cover 40 selected/generated articles and a 41st excluded
or request-cap fallback item. Reverting the coordinated settings to 30 restores
the previous budget without changing saved news.
