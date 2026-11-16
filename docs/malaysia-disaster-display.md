# Natural Disaster Display Group

This is a presentation layer, not a selector, deduplicator, safety validator or
live warning feed. All selected articles, summaries, sources and article anchors
remain available. Publication budgets and Jev routing do not change.

- Group actual natural-disaster damage, specific warnings and concrete effects
  such as road closures, transport disruption, school closures and evacuation.
- Leave policy, budgets, long-term mitigation, preparedness, equipment checks,
  historical statistics and drills in their existing categories.
- Show up to three headlines. Prefer explicitly affected Klang Valley places,
  then concrete disruption, warnings and damage. Other reports are collapsed.
  Selangor alone, datelines and officials' offices do not establish local impact.
- Each headline opens its unchanged article. Map and direct article links open
  all enclosing disclosures automatically, including on initial page load.

One optional Luna request classifies the already-published text per run using the
existing model profile and transport. No additional summary regeneration occurs.
The `YYYY-MM-DD.display.json` sidecar is bound to the Markdown SHA-256 and each
article's headline, summary and URL. Missing, invalid, failed or stale metadata
retains regular rendering; historical pages without metadata remain unchanged.
Deleting a sidecar and rebuilding restores the regular layout for that date.
The initial November 16 sidecar is explicitly marked `human_review`; subsequent
workflow labels are marked `model`. Human labels are not reported as API results.

Scheduled runs classify the guarded publication output. Manual runs classify the
Luna candidate and produce `disaster_display.json` and
`disaster_display_preview.html` in the artifact; they never commit or publish.
Diagnostics retain labels, token usage and bounded transport status, not prompts,
response bodies, provider error messages or keys. The existing article date and
warning-expiry protections remain authoritative.

`Malaysia disaster display review` is a manual-only, read-permission workflow for
replaying just the classification. Its optional `source_run_id` reuses a previous
RSS artifact; otherwise it reads the latest saved Markdown. It generates only a
review artifact and never regenerates summaries or publishes. Local validation
failures have a separate `validation_reason`, even when the API request succeeded.
The main RSS workflow can invoke this same review via `disaster_display_review_run`;
when provided, the normal collection, summary and publication job is skipped.

Inspect model grouping and geographic prioritization in real artifacts. These
semantic choices are not guaranteed by the structural validator. If ambiguous,
the prompt asks for regular display or no Klang Valley preference. Classification
does not assert that a published warning remains currently valid.
