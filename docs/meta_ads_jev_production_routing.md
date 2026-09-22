# Jev production routing

The Personal Feed keeps its existing source allowlists, safe fetch limits,
parsers, freshness limits, and source-specific eligibility checks.  Jev runs
only after those boundaries have retained a candidate, and decides whether that
candidate appears in the public feed.

## Routing contract

| Jev choice | Stored publication status | Public result |
| --- | --- | --- |
| `direct_impact` | `included` | Published |
| `strategic_signal` | `included` | Published |
| `unclear` | `included` | Published for later artifact review |
| `unrelated` | `drop` | Kept only in internal state |

The only model-derived state evidence is `jev:<choice>`.  Titles, source
context, raw provider responses, URLs, and credentials are not written to the
routing artifact or state by this path.

## Enable and rollback

Set the repository variable `META_ADS_JEV_ROUTING_ENABLED` to `true` after the
workflow change reaches `main`.  The workflow then requires the existing
`TYPESAFE_API_KEY` secret.  A missing key, provider error, timeout, or invalid
choice fails before feed and state files are written, so the previously
published feed remains intact.

Set the variable to `false` to roll back to the prior deterministic publication
classifier without changing source transport or the public feed schema.

## Transport boundary

Jev requests use the fixed TypeSafe API endpoint with environment proxies
disabled. Redirects are rejected before a second request is made, including
same-host redirects, so a bearer token is never forwarded to a redirect target.
The safe error code is `redirect_blocked`; it follows the normal fail-closed
path and does not write a new feed or state.

## First production observation

The normal workflow runs at 08:15 MYT on Tuesday and Friday.  It uploads a
runner-temp `meta-ads-jev-routing-<run id>` artifact for 30 days.  Review its
safe per-item IDs, source IDs, choices, confidence values, latency, and error
codes; it deliberately contains no article prose or URLs.

Existing unchanged state records retain their earlier publication decision to
avoid unnecessary model calls.  To apply the new routing to a source's current
fresh candidates, manually run the collector once with that source ID in
`reseed_source_id`.  Reseed one configured source at a time; observe the
artifact before continuing to another source.
