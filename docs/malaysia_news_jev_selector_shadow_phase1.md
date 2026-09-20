# Malaysia News Jev Selector Shadow: Phase 1

Phase 1 compares Jev's semantic relevance signal with the Malaysia News
selector at the same point in a scheduled run. It is an observation experiment:
it does not alter selected items, Groq requests, rendered Markdown, or any
published page.

## Fixed Principles

1. **Safety conditions are fixed; the current validator implementation is not.**
   The system must not publish malformed or unsafe output, but the selector and
   validator are comparison targets that can be audited and changed in later,
   separately tested work.
2. **`REVIEW` preserves the baseline and never blocks a daily run.**
   During this phase, a possible disagreement only records a review candidate.
   The existing selector decision remains the routing and publication decision.
3. **Jev cannot bypass hard safety.**
   Any later promotion proposal remains subject to hard-safety checks. Phase 1
   records per-item hard-safety observations when Groq ran; it never changes
   that result or treats a Jev choice as an override.

## Scope

The runner reads the same run's `selection_observation.json`, whose selector
records are the **comparison-time baseline**, not ground truth. It sends only
the RSS title and a bounded public description to Jev. It does not send body
enrichment, tags, source URLs, Groq output, credentials, or instructions taken
from the RSS content.

The report stores stable item fingerprints and decision metadata, not article
text, URLs, raw provider responses, or credentials. Its trace fields are:

- `baselineDecision`: current selector result at the time of the run.
- `jevDecision`: semantic choice from Jev, when available.
- `routingDecision`: always `retain_baseline` in Phase 1.
- `finalPublicationDecision`: the unchanged selector result.
- `decisionSource`: `shadow_observation`.
- `experimentId`, `baselineReason`, and fingerprint-based `evidence`.

`hardSafetyObservation` is explicitly item-level and only reflects the Groq
renderer's hard-safety handling. `documentValidatorObservation` is separately
reported because Markdown validation is a document-level check.

## Cohort And Output

Only selector-evaluated RSS items are eligible. The deterministic cohort takes
selected items first, then exclusions ordered by selector stage, score, candidate
rank, and original input order. The default cap is 30 and the maximum is 50.

Jev choices are `direct_life_impact`, `public_information`, `unrelated_noise`,
and `unclear`. The report may surface only these observation hypotheses:

- excluded + `direct_life_impact`: `candidate_promote_for_review`, a possible
  selector false negative;
- selected + `unrelated_noise`: `selected_review`, a possible selector false
  positive;
- `unclear`: retain the baseline;
- all other combinations: retain the baseline.

These labels are not final diagnoses. Human review in Phase 2 must distinguish
deterministic-rule gaps, semantic judgments, Jev mistakes, and unresolved cases.

## Workflow Control And Failure Behavior

The workflow writes `jev_selector_shadow.json` inside its existing optional
diagnostics artifact. Calls are opt-in through the repository variable
`MALAYSIA_NEWS_JEV_SHADOW_ENABLED=true` and the existing `TYPESAFE_API_KEY`
secret. The default is disabled. A missing secret, transport failure, or invalid
provider answer is recorded in the artifact and cannot change the daily public
result or prevent the index from being built.

## Promotion Boundary

Phase 1 does not authorize production routing. Any Phase 3 change requires a
separate proposal, targeted tests, an explicit kill switch, and the ability to
return immediately to the selector-only baseline. It must preserve the hard
safety invariant above.
