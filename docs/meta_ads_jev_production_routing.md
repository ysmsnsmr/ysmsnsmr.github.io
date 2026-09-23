# Jev production routing

The Personal Feed keeps its existing source allowlists, safe fetch limits,
parsers, item limits, and freshness limits. When Jev is enabled, it receives
fresh, successfully parsed candidates from those configured feeds and decides
whether each candidate appears in the public feed. The legacy source-specific
keyword prefilter is retained for the Jev-disabled rollback path only.

## Legacy relevance boundary

Jev-enabled collection does not apply the old source-specific semantic keyword
groups before the model call. This prevents a plausible item from being
discarded before Jev can evaluate it, while preserving the non-semantic
boundaries: configured source IDs and hosts, safe transport, parser and item
limits, freshness, and fail-closed fetch/parse behavior. It does not add new
sources or permit arbitrary URLs.

When `META_ADS_JEV_ROUTING_ENABLED` is `false` (or the Jev classifier is not
available), the previous source-specific keyword and category rules run
unchanged. The next Jev-enabled artifact should therefore be read with the
expectation that `relevanceExcludedItems` can fall for the RSS sources and that
more candidates may reach Jev. Review Jev choices, runtime, request volume, and
cost rather than treating the larger candidate set as automatically useful.
If noise, false positives, API load, or cost is clearly unacceptable, disable
the Jev variable to restore the prior prefilter behavior.

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

## Official-link discovery

When a configured RSS source is parsed successfully and the item is fresh,
official Meta Business News links are extracted independently of the parent
article's source-specific keyword decision. The linked official page is then
fetched and validated as its own item. A parent article is never relabeled as
official, and an invalid promoted link does not invalidate the direct source.

The discovery normalizer removes only known tracking decorations, including
Meta's `_sp` parameter, before applying the existing HTTPS, host, path, and
metadata checks. Unknown query parameters and unsupported page families remain
rejected.

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
