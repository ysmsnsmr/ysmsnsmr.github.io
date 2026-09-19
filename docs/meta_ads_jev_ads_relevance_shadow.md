# Jev Ads Relevance shadow comparison

This is a one-time **artifact-only** comparison. It does not affect the
collector, Personal Feed state, publication, GitHub Pages, source configuration,
or ACTION/WATCH/DROP decisions.

## Fixed input and output boundary

- Input is only the committed 15-item fixture at
  `scripts/fixtures/meta_ads_jev_ads_relevance_shadow/human_labels.json`.
- The provider receives only each item's public `title` and a `sourceContext`
  capped at 4,000 characters. It never receives the human lane, URL, source
  fingerprint, production state, source configuration, API key, or source code.
- The runner requests `jev-1.13.0` with the versioned
  `meta-ads-relevance-v1` choice question.
- The local output records item IDs, human lanes, the returned choice,
  probabilities, confidence, safe failure codes, and comparison totals. It never
  stores a raw provider response, request payload, title, source context, URL,
  credential, or exception body.
- Artifacts are written atomically, cannot overwrite a previous artifact, and
  are ignored by Git under `artifacts/meta_ads_jev_ads_relevance_shadow/`.

[TypeSafe's privacy policy](https://typesafe.ai/legal/privacy-policy) says
submitted input is not used to train or fine-tune its models, but it describes
retention only as reasonably necessary and says data may be processed in the
United States. The input is therefore deliberately limited to this public
fixture; do not expand it to private documents or live Personal Feed state
without a separate review.

## Run manually

The normal command is deliberately non-networked and only validates the frozen
fixture:

```bash
python3 scripts/experiment_meta_ads_jev_ads_relevance_shadow.py
```

For the explicit live comparison, set `TYPESAFE_API_KEY` only in your shell or
secret manager. Do not place it in a committed file. Choose a new simple
lowercase filename each run:

```bash
TYPESAFE_API_KEY='...' \
python3 scripts/experiment_meta_ads_jev_ads_relevance_shadow.py \
  --live \
  --output-name jev-shadow-2026-09-19.json
```

An `ACTION -> DROP` comparison is a review finding, never an automatic route
change. `unclear`, transport failures, and malformed responses are also
observations. A future production integration requires a new Idea Gate and
explicit human review.
