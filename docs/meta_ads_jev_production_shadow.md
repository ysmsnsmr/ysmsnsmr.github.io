# Meta Ads Jev production shadow

This bounded production shadow classifies current public Personal Feed items and
writes a private GitHub Actions artifact. It has no routing or publication
effect.

## Safety boundary

- Input is the committed `meta-ads-updates/personal-feed.json` only.
- The provider receives the public English title and, when available, the
  public English machine/reviewed summary capped at 4,000 characters.
- The artifact stores item/source IDs, typed Jev output, latency, safe error
  codes and aggregate counts. It does not store title, summary, URL, raw
  provider response, exception body or credential.
- The workflow has `contents: read`, never commits, and never writes Personal
  Feed state or Pages output.
- A Jev failure uploads the diagnostic artifact and fails only this independent
  workflow. It cannot stop collection or publication.
- `jev-1.13.0` and `meta-ads-relevance-v1` remain fixed during observation.

## Enable and run

Store the TypeSafe credential as the repository Actions secret
`TYPESAFE_API_KEY`. Set the repository Actions variable
`META_ADS_JEV_SHADOW_ENABLED=true`. Unset or `false` disables the workflow
without calling the provider.

Run **Meta Ads Jev production shadow** manually. The default limit is 15 and the
accepted range is 1-50. The first implementation deliberately has no schedule;
schedule eligibility follows one successful manual production artifact review.

## Observation

Review `summary.classified`, `summary.failed`, `summary.choices`,
`summary.sources`, `summary.errorCodes`, per-item confidence and latency. These
are observations only. Do not use them to publish, drop, approve or stop an
item. Automatic routing requires a separate decision.
