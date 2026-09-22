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
published feed remains intact. The collector still writes a safe routing
artifact with `runStatus: "failed"` and a bounded `failureCode` when a report
path is configured. It never contains article text, URLs, response bodies,
exception text, or credentials.

Set the variable to `false` to roll back to the prior deterministic publication
classifier without changing source transport or the public feed schema.

## Transport boundary

Jev requests use the fixed TypeSafe API endpoint with environment proxies
disabled. Redirects are rejected before a second request is made, including
same-host redirects, so a bearer token is never forwarded to a redirect target.
The safe error code is `redirect_blocked`; it follows the normal fail-closed
path and does not write a new feed or state.

## First production observation

The normal workflow runs at 08:15 MYT on Tuesday and Friday. It uploads a
runner-temp `meta-ads-jev-routing-<run id>` artifact for 30 days, including
when the collector fails after the kill switch. `runStatus: "succeeded"` means
the Python collector completed; it does not by itself prove that the later Git
commit/push completed. Review its safe per-item IDs, source IDs, choices,
confidence values, latency, and error codes; it deliberately contains no
article prose or URLs. If the report file was never created because setup or
the kill switch stopped the job, the upload step warns and preserves the
original failure.

Currently observed records are reclassified by Jev whenever they are present
in the current source input; only carried-forward records retain a prior
decision. Presentation generation is cached independently. A
`reseed_source_id` run rebuilds the selected source's current candidates but
still fetches and routes the other configured sources; it is not an API-call
scope limiter. Because a reseed can drop records that no longer appear in the
source, use it for targeted source-rule changes and review the artifact before
continuing.
