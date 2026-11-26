# Three-language headline backend experiment

The existing collector generates Simplified Chinese (`zh-Hans`), Spanish
(`es`), and Korean (`ko`) headlines for up to three articles per run, with
one attempt per language. Set `META_ADS_HEADLINE_TRANSLATIONS_ENABLED=false`
to stop new generation. Missing or stale translations fall back to English.
The existing English/Japanese schema and generation history are unchanged.

`meta_ads_headline_translations.py` validates a v5 feed, takes an optional
previous independently versioned state, and produces per-item, per-language
headline records. Input is always the original article title, not the generated
English headline. It does not send article bodies or summaries. The v2 input
hash revision invalidates only prior three-language translations; English and
Japanese presentation histories are not changed.
`translate_headline` uses the existing OpenAI transport and safe failure
classification; the input is treated as untrusted. `build_state` accepts a
caller-supplied generator, so offline tests need no credentials. `save_state`
validates and atomically replaces an explicitly selected file. These functions
are called by the production collector after normal feed validation.

Each locale has `machine` or `missing` status. Only successful generated text,
an input hash, timestamp and an allowlisted safe failure code are saved; source
text, response bodies and credentials are not saved. A matching successful
record is reused; missing or changed-input records are retried only when the
function is explicitly invoked. Removed feed items are omitted. An unexpected
exception aborts generation rather than overwriting existing saved state.

The overlay is published separately from `personal-feed.json`. The top page
uses `?lang=zh-Hans`, `?lang=es`, or `?lang=ko` for headline-only views.
Details remain in English and the list link preserves the chosen view.

Offline verification: `python3 scripts/test_meta_ads_personal_feed_headline_translations.py`.
