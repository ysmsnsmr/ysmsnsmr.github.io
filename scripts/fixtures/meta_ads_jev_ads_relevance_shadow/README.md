# Meta Ads Jev Ads Relevance shadow fixture

This directory contains the frozen human-labelled input set for the first Jev
Ads Relevance shadow experiment. It is deliberately separate from production
collection, publication, and approval data.

`human_labels.json` joins the 15 previously reviewed titles to the URL and
fingerprint stored in the production state at commit
`908595bbd3461311f6f9ba250711530f968baf83`. The human labels come from the
reviewed golden test at commit `8618730`.

The field is named `url`, not `officialUrl`, because the labelled set contains
both official and unofficial sources. Calling every URL official would create a
false provenance claim.

This checkpoint does not call Jev, define a Jev API client, modify a hard
validator, or affect a published feed. A later checkpoint may add the fixed
model/question contract and an artifact-only runner after provider retention,
learning use, and credential boundaries have been verified.
