# Meta Ads Tracker production runbook

## Bootstrap and daily collection

The daily workflow runs at 08:15 MYT (`00:15 UTC`). The first run succeeds only after every enabled public source has been fetched and validated. That successful instant becomes `baselineCutoffAt`: every observed RSS URL and SDK release tag is seeded into fingerprint state, while the initial candidate contains zero events. Articles that existed before monitoring began are therefore never mislabeled as `new_url`.

An optional historical catch-up is a separate, one-time human review. It must not alter the change detector or its baseline state.

After bootstrap, RSS URL additions become `new_url`, fingerprint changes on an existing RSS URL become `content_changed`, and a previously unseen SDK tag becomes `sdk_release`. Repeated SDK tags are not new releases. Each daily artifact has a canonical `candidateHash`; each detected revision has an `eventId` derived from its stable subject and full source fingerprint. Raw responses are never persisted, and the bounded normalized source excerpt is limited to 3,500 characters.

If any source fetch, parse, schema, or semantic validation fails, neither the candidate nor state is committed.

### Emergency stop and transport boundary

Set the repository Actions variable `META_ADS_TRACKER_COLLECT_ENABLED` to `false` to stop daily collection before dependency installation or any official-source request. A disabled run finishes successfully without creating an artifact or committing data. Set it to `true` (or leave it unset) to enable collection; any other value intentionally fails the run as a configuration error.

Every configured source has an explicit HTTPS host allowlist, three-redirect limit, 1 MiB response limit, item limit, and allowed media types. The collector disables environment proxy settings, rejects credentials, non-standard ports, literal or non-global IP addresses, disallowed redirects, unexpected media types, oversized payloads, and XML DTDs. These checks are transport safety controls, not evidence that an unavailable official source has no updates.

### Source governance and the 14-day re-review

`config/meta_ads_source_governance.json` is the authority for whether a configured source may be collected automatically. New automatic sources require a human `approved` record with reviewer, timestamp, evidence URL, and rationale in the same change that enables the source. A source cannot use the legacy grace status unless it is one of the two sources that existed when P0-B was established.

The existing Product News RSS and SDK release sources are temporarily permitted only before `2026-09-05` MYT. On that date, an unresolved record stops the daily workflow before any source request, candidate write, or state write. A `prohibited` decision must disable the source in the same configuration change. Login-required Help sources remain `manual_only` and are never scheduled for collection.

## Immutable weekly assembly

The weekly assembler is separate from daily collection and is scheduled for Friday 17:00 MYT (`09:00 UTC`). `cutoffAt` records that logical business cutoff; `generatedAt` records when GitHub Actions actually assembled the artifact. Scheduler delay therefore does not change the collection window.

Assembly requires at least one schema-valid successful candidate for every Monday-Friday date. Missing days fail closed. Exact duplicate `eventId` values are deduplicated. If the same URL changes more than once during the week, every distinct fingerprint revision remains as a separate event in chronological order. The resulting `weeklyHash` covers the complete artifact, and an existing weekly file cannot be replaced with different content.

## Review and approval

Run `Meta Ads tracker generate review artifact` with the Friday cutoff date. Groq receives only the immutable weekly artifact and may return a Japanese summary plus explicitly stated effective date, rollout, and target facts. Every extracted value needs an exact excerpt from the supplied source text. Groq does not produce business-impact or action decisions, and its artifact is never public.

After reviewing the official URL and optional Groq artifact, add a human decision to `data/meta_ads_tracker_decisions.json`:

```json
{
  "eventId": "meta-product-news-rss-0123456789abcdef0123",
  "revision": "<64-character source fingerprint>",
  "sourceFingerprint": "<same 64-character source fingerprint>",
  "originCandidateHash": "<64-character daily candidate hash>",
  "weeklyHash": "<64-character immutable weekly hash>",
  "reviewStatus": "approved",
  "reviewer": "name-or-account",
  "reviewedAt": "2026-08-21T18:00:00+08:00",
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

The five binding fields prevent an approval from being reused for a later body revision. Decisions for older `weeklyHash` values may stay in the file and do not block a current publication.

## Publication

Run `Meta Ads tracker publish approved report` with the validated Friday `YYYY-MM-DD` cutoff date. The workflow never runs Groq. It resolves the date inside the weekly directory, validates the immutable weekly artifact and all decision bindings, builds a temporary report, runs the public validator, and only then installs static output. A weekly artifact with changed events and no matching approval cannot replace the public report; partial human approval publishes only the exactly matched events.

Collection, weekly assembly, and publication share one repository-write concurrency group. Input values are passed through environment variables and parsed before path construction; shell interpolation and path traversal are rejected.

## Merge and UI gate

`Meta Ads tracker CI` runs the source/fixture contracts, six delta cases, weekly and approval lifecycle tests, fail-closed and workflow boundary checks, and the production UI. The UI gate renders the five approved fixture states at 375×667, 768×1024, and 1440×900, checks overflow, 44px targets, keyboard focus, axe WCAG A/AA, filters, query, reset, and the approved Workbench tokens, then uploads 15 viewport and 15 full-page PNGs.
