# Phase 2B.4.8: Groq Guard Verification

Date: 2026-05-31
Status: Static/no-API verification completed. Live Groq verification not executed because `GROQ_API_KEY` was not set.

## Summary

Phase 2B.4.8 guard implementation is already present in `scripts/render_malaysia_news_with_groq.py` and was committed as `78d3b46 Add Groq output guards for topic safety`.

This verification checkpoint confirmed the local guard behavior without changing RSS selection, GitHub Actions, Pages, Phase 2F source configuration, Groq prompts, or article body fetching.

Verification artifacts were written under:

- `/tmp/malaysia_groq_phase2b48_verify/`

These artifacts are local only and should not be committed.

## Static Checks

Passed:

```bash
python3.12 -m py_compile scripts/render_malaysia_news_with_groq.py
python3.12 -m py_compile scripts/render_malaysia_news_from_json.py
python3.12 scripts/malaysia_rss_summary.py --self-test
```

`scripts/malaysia_rss_summary.py --self-test` result:

```text
self-test passed
```

## Fresh Selected JSON

Generated with network access:

```bash
python3.12 -B scripts/malaysia_rss_summary.py \
  --output /tmp/malaysia_groq_phase2b48_verify/original_20260531.md \
  --json-output /tmp/malaysia_groq_phase2b48_verify/selected_items_20260531.json
```

Result:

- processed: `87`
- selected: `11`
- failed sources: `0`

Selected items included the expected guard-relevant cases:

- paddy farmers / spot checks
- Ops Kesan 6.0 / oil prices
- fleet card misuse
- hire purchase rules
- ringgit / Bursa market items

## No-API Renderer Runs

Because `GROQ_API_KEY` was not set, both model runs used fallback rendering only:

```bash
python3.12 -B scripts/render_malaysia_news_with_groq.py \
  --json-input /tmp/malaysia_groq_phase2b48_verify/selected_items_20260531.json \
  --output /tmp/malaysia_groq_phase2b48_verify/llama_no_api_20260531.md \
  --model llama-3.3-70b-versatile \
  --force-all \
  --debug-groq \
  --improved-items-output /tmp/malaysia_groq_phase2b48_verify/llama_no_api_improved_items_20260531.json

python3.12 -B scripts/render_malaysia_news_with_groq.py \
  --json-input /tmp/malaysia_groq_phase2b48_verify/selected_items_20260531.json \
  --output /tmp/malaysia_groq_phase2b48_verify/gptoss_no_api_20260531.md \
  --model openai/gpt-oss-20b \
  --force-all \
  --debug-groq \
  --improved-items-output /tmp/malaysia_groq_phase2b48_verify/gptoss_no_api_improved_items_20260531.json
```

Both runs reported:

```text
groq: GROQ_API_KEY is not set; using fallback renderer for all items.
```

Counts:

| model | requested | accepted | fallback |
| --- | ---: | ---: | ---: |
| llama no-API | 0 | 0 | 0 |
| gpt-oss no-API | 0 | 0 | 0 |

Dateline note:

- The no-API fallback Markdown still contains source RSS datelines such as `KUALA LUMPUR, May`, `PUTRAJAYA, May`, and `ALOR SETAR, May`.
- This does not test the live Groq English-lead guard, because no Groq output was generated.
- The static guard probe below verifies that such output would be rejected if returned by Groq.

## Static Guard Probe

A local probe was run without sending any network request to Groq:

- `/tmp/malaysia_groq_phase2b48_verify/static_guard_probe_20260531.json`

Result:

- passed: `9`
- failed: `0`

Verified behavior:

| guard | result |
| --- | --- |
| `openai/gpt-oss-20b` request uses `include_reasoning: false` | pass |
| `openai/gpt-oss-20b` request uses `reasoning_effort: low` | pass |
| `openai/gpt-oss-20b` omits `response_format` | pass |
| `llama-3.3-70b-versatile` uses `response_format: {"type": "json_object"}` | pass |
| `spot checks` enforcement/misuse item is skipped | pass |
| `fleet card misuse` item is skipped | pass |
| unsupported `進学条件` life impact is rejected | pass |
| English lead leakage is rejected | pass |
| KPDN / fleet card / oil price term normalization is applied | pass |

## Remaining Live Verification

Live Groq verification still needs to be run in an environment where `GROQ_API_KEY` is available.

When the key is available, rerun both model commands with real API access and record:

- requested / accepted / fallback counts;
- `groq-debug: item=N skipped enforcement_misuse`;
- `english lead leakage` fallback occurrences;
- `life_impact topic mismatch` or unsupported `進学条件` fallback occurrences;
- whether accepted Markdown still contains English dateline leakage.

## Not Changed

This phase did not change:

- `scripts/malaysia_rss_summary.py`
- `.github/workflows`
- `scripts/build_malaysia_news_index.py`
- Phase 2F configs/helpers
- Groq prompt text
- RSS source configuration
- article body fetching

Untracked backup files related to the Groq renderer were left untouched. Backup cleanup should remain a separate task.
