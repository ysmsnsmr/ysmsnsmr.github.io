# Three-language headline backend experiment

This backend-only stage prepares Simplified Chinese (`zh-Hans`), Spanish (`es`),
and Korean (`ko`) headlines. It does **not** add a public feed field, page,
workflow, scheduled generation, or backfill. It does not call the API unless a
caller explicitly invokes it. The existing English/Japanese schema, generation
revision, hashes, state and publication path are unchanged.

`meta_ads_headline_translations.py` validates a v5 feed, takes an optional
previous independently versioned state, and produces per-item, per-language
headline records. Input is the existing English display headline when present,
otherwise the original title. It does not send article bodies or summaries.
`translate_headline` uses the existing OpenAI transport and safe failure
classification; the input is treated as untrusted. `build_state` accepts a
caller-supplied generator, so offline tests need no credentials. `save_state`
validates and atomically replaces an explicitly selected file. These functions
are not called by the production workflow.

Each locale has `machine` or `missing` status. Only successful generated text,
an input hash, timestamp and an allowlisted safe failure code are saved; source
text, response bodies and credentials are not saved. A matching successful
record is reused; missing or changed-input records are retried only when the
function is explicitly invoked. Removed feed items are omitted. An unexpected
exception aborts generation rather than overwriting existing saved state.

The user has not approved public multilingual rendering or recurring API
calls. Before wiring this backend into collection, separately establish a
bounded call budget, storage location, retention and retry policy, and validate
translation quality, fallbacks, costs, and publication/privacy implications.
The current schema is an independent experimental contract, not an extension
of public `personal-feed.json`.

Offline verification: `python3 scripts/test_meta_ads_personal_feed_headline_translations.py`.
