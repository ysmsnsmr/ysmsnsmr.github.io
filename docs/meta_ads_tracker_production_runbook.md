# Meta Ads Tracker production runbook

The daily workflow runs at 08:15 MYT (`00:15 UTC`) and stores only normalized candidate metadata, fingerprints, and a bounded source excerpt under `data/meta_ads_tracker_candidates/`. It never stores the raw RSS, HTML, or API response body. Friday's run also copies the candidate into `data/meta_ads_tracker_weekly/`.

The candidate is not public. A human reviewer may inspect the Groq review-only artifact from the manual `Meta Ads tracker publish approved report` workflow, then add only explicitly reviewed records to `data/meta_ads_tracker_decisions.json`:

```json
{
  "itemId": "meta-product-news-rss-...",
  "reviewStatus": "approved",
  "reviewer": "name-or-account",
  "reviewedAt": "2026-08-15T09:00:00+08:00",
  "priority": "standard",
  "businessImpact": {
    "status": "human_assessed",
    "summary": "人間が確認した業務影響",
    "assessmentSource": "human_review"
  },
  "action": {
    "status": "review_required",
    "summary": "人間が確認した対応要否",
    "assessmentSource": "human_review"
  }
}
```

Dispatch the publish workflow with the candidate date only after the decision file is committed. Groq output is a draft, not an approval. A missing key, transport error, invalid Groq JSON, invalid decision, or publication validator failure stops the run before `meta-ads-updates/latest.json` is changed. The static UI reads only that validated approved report.
