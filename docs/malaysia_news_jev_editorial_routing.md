# Malaysia News Jev Editorial Routing

This is the production successor to the artifact-only Phase 1 comparison. It
does not treat the existing selector as ground truth: it reuses its hard,
deterministic boundaries, then lets Jev apply the final editorial ordering.

## Candidate Boundary

Before Jev is called, the RSS selector enforces freshness, a valid URL, URL
deduplication, and canonical-event deduplication. Score thresholds, static
exclusions, final-noise policy, and source or finance diversity are not used at
this stage. It writes both outputs to the optional artifact:

- `selected_items_baseline.json`: the unchanged legacy selector result,
  including fixed category limits and its total cap;
- `editorial_candidate_pool.json`: the same deterministic candidates before
  those category and total limits.

This distinction is intentional. Category and total limits are no longer used
to decide which semantic candidates Jev sees. The limits are replaced after
classification by one editorial budget of 15 cards.

## Public Display Categories

The legacy `category` remains selection metadata. Public Markdown and HTML use
two display categories instead:

| Jev choice | Display category |
| --- | --- |
| `direct_life_impact` | `暮らしに関わる更新` |
| `public_information` | `社会・経済の動き` |
| `unclear` | The legacy category's mapped display category |

For RSS-only fallback, historical `速報` and `生活インパクト` map to `暮らしに
関わる更新`; `知っておくと得` maps to `社会・経済の動き`. This preserves a
consistent public layout without using display labels to change article
selection.

## Routing Contract

| Jev choice | Publication handling |
| --- | --- |
| `direct_life_impact` | First priority within the 15-card editorial budget |
| `public_information` | Fills remaining budget in deterministic candidate order |
| `unclear` | Fills any remaining budget in deterministic candidate order |
| `unrelated_noise` | Not included in the routed card set |

`direct_life_impact` is protected from lower-priority candidates, but it is
not an unlimited exception: the page remains bounded to 15 selected cards.
Each routing artifact records a stable fingerprint, candidate rank, baseline
selection status, Jev choice, confidence, latency, and final publication
decision. It never stores article text, URLs, raw provider responses, or
credentials.

## Enable And Rollback

The repository Actions variable `MALAYSIA_NEWS_JEV_ROUTING_ENABLED` is the
production switch. Its default is `false`.

- `false`: retain the legacy selector item list (with disabled-routing metadata
  in the diagnostic JSON) and render it in the two public display categories;
  the existing Phase 1 shadow may run when its own switch is enabled.
- `true`: attempt Jev routing and write `jev_editorial_routing.json`.

The router is fail-open. A missing API key, candidate pool above 150 items,
transport failure, timeout, or invalid Jev answer restores the complete legacy
selector result for that run. It is then rendered using the same two public
display categories. When routing is active, the earlier Phase 1 shadow call is
skipped so the same RSS items are not classified twice.

Set `MALAYSIA_NEWS_JEV_ROUTING_ENABLED=false` to return immediately to the
legacy selector. This does not change RSS fetching, the Groq summary path,
hard-safety checks, or the document-level RSS rollback.

## First Live Review

After enabling the variable, review one optional artifact before treating the
routing as stable:

- `jev_editorial_routing_status.txt` is `applied`;
- `editorial_candidate_pool.json` and `selected_items_baseline.json` explain
  any change in selection;
- direct-impact articles are retained ahead of lower-priority candidates;
- selected/rendered URLs still match and the existing Groq/Markdown validators
  pass.
