# Phase 2C.0: Hy-MT2 Local Translation Research

Date: 2026-05-25
Scope: local research only. Do not integrate Hy-MT2 into the production RSS selection, Groq rendering, GitHub Actions, or Pages workflow yet.

## Summary

Hy-MT2 is being evaluated as a translation-only layer for the Malaysia RSS news project. The intended role is narrow:

- Translate RSS `title` and `description` faithfully into Japanese.
- Preserve item order, category, source, date, URL, score, tags, and flags as metadata.
- Do not use Hy-MT2 for article selection, classification, life-impact judgment, summarization, or ranking.
- Compare later whether `selected_items.json -> Hy-MT2 translation -> Groq summary` improves Japanese display quality.

Initial result: `tencent/Hy-MT2-1.8B-GGUF` Q4_K_M can be downloaded and loaded locally on this MacBook Air, and a minimal English-to-Japanese translation completed. The current `llama-cli` invocation drops into interactive chat mode, so Phase 2C.1 should use `llama-completion`, a non-interactive wrapper, or a subprocess timeout before batch testing.

## Local Environment

Observed environment:

- macOS: 14.5, BuildVersion 23F79
- Machine: MacBook Air, Model Identifier MacBookAir10,1
- Chip: Apple M1
- CPU: 8 cores, 4 performance and 4 efficiency
- Memory: 8 GB
- Homebrew: `/usr/local/bin/brew`

Notes:

- Homebrew is installed under `/usr/local`, and `llama-cli --version` reports a Darwin `x86_64` build. On this Apple Silicon machine, this likely means the Homebrew `llama.cpp` binary is running through the Intel/Rosetta path rather than a native arm64 Homebrew installation.
- This is acceptable for Phase 2C.0 feasibility checking, but Phase 2C.1 should consider a native arm64 build if speed becomes a blocker.

## llama.cpp Setup

Initial state:

- `llama-cli`: not installed
- `llama-server`: not installed
- `cmake`: not installed
- `brew list --versions llama.cpp cmake`: no installed formula output

Installed via Homebrew:

```bash
brew install llama.cpp
```

Post-install state:

```text
llama-cli: /usr/local/bin/llama-cli
llama-server: /usr/local/bin/llama-server
llama-completion: /usr/local/bin/llama-completion
llama.cpp: 9290
cmake: not installed
```

Version output:

```text
version: 9290 (bcfd1989e)
built with AppleClang 16.0.0.16000026 for Darwin x86_64
```

## Model Download

Target model:

- Repository: `tencent/Hy-MT2-1.8B-GGUF`
- Quantization: `Q4_K_M`
- Local file: `/tmp/hymt2/Hy-MT2-1.8B-Q4_K_M.gguf`
- File size: about 1.1 GB

The direct Hugging Face file URL was reachable. Header metadata reported:

```text
content-length: 1133080448
x-linked-size: 1133080448
```

The `llama-cli -hf tencent/Hy-MT2-1.8B-GGUF:Q4_K_M` path failed during model download with an HTTP library read error:

```text
get_repo_files: error: HTTPLIB failed: Failed to read connection
failed to download model from Hugging Face
```

Direct download with `curl` succeeded:

```bash
mkdir -p /tmp/hymt2
curl -L --fail --continue-at - \
  -o /tmp/hymt2/Hy-MT2-1.8B-Q4_K_M.gguf \
  'https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf?download=true'
```

Observed download time was roughly 52 seconds in this environment.

## Minimal Translation Test

Prompt:

```text
Translate the following text into Japanese. Only output the translated result without any additional explanation: Thunderstorms, strong winds and heavy rain forecast across nine states until 8pm
```

Command tested:

```bash
/usr/bin/time -p llama-cli \
  -m /tmp/hymt2/Hy-MT2-1.8B-Q4_K_M.gguf \
  -p 'Translate the following text into Japanese. Only output the translated result without any additional explanation: Thunderstorms, strong winds and heavy rain forecast across nine states until 8pm' \
  -n 128 \
  --temp 0.7 \
  --top-p 0.6 \
  --top-k 20 \
  --repeat-penalty 1.05 \
  --no-display-prompt
```

Observed translation:

```text
午後8時まで、9州で雷雨、強風、豪雨が予報されている
```

This is faithful enough for a first translation-only experiment. It preserves the key details: 8pm, nine states, thunderstorms, strong winds, and heavy rain.

Operational caveat:

- `llama-cli` entered interactive chat mode after producing the translation and repeatedly printed prompts.
- `--no-conversation` is not supported by this `llama-cli` build and prints:

```text
--no-conversation is not supported by llama-cli
please use llama-completion instead
```

Recommendation:

- Phase 2C.1 should use `llama-completion` for non-interactive execution, or implement a subprocess wrapper with timeout and output cleanup.
- Avoid using plain `llama-cli` in batch mode until the interactive prompt issue is solved.

## selected_items.json Three-Item Trial Set

Source file:

```text
/tmp/malaysia_selected_items.json
```

Observed item count:

```text
9 selected items
```

Initial three-item trial set:

### Item 1

- category: `【速報】`
- source: Malay Mail
- published_date: 2026年5月25日
- title: `Thunderstorms, strong winds and heavy rain forecast across nine states until 8pm`
- description: `KUALA LUMPUR, May 25 — Thunderstorms, heavy rain and strong winds are expected to prevail until 8 pm today i...`
- link: `https://www.malaymail.com/news/malaysia/2026/05/25/thunderstorms-strong-winds-and-heavy-rain-forecast-across-nine-states-until-8pm/221381`

Why include it:

- Clear weather-alert style English.
- Good baseline for checking numbers, time, and weather terms.

### Item 2

- category: `【生活インパクト】`
- source: Malay Mail
- published_date: 2026年5月25日
- title: `JPJ seizes Vellfire linked to ex-national football player, G-Wagon owned by ‘Datuk’ motivational speaker in Bukit Bintang Ops Luxury raid`
- description: `KUALA LUMPUR, May 25 — The Road Transport Department (JPJ) has seized several luxury vehicles, including a Toyota...`
- link: `https://www.malaymail.com/news/malaysia/2026/05/25/jpj-seizes-vellfire-linked-to-ex-national-football-player-g-wagon-owned-by-datuk-motivational-speaker-in-bukit-bintang-ops-luxury-raid/221275`

Why include it:

- Tests whether Hy-MT2 translates JPJ and vehicle/operation wording without adding extra judgment.
- Also useful as a caution case: translation should not turn this into a broader public-service summary by itself.

### Item 3

- category: `【生活インパクト】`
- source: Malay Mail
- published_date: 2026年5月25日
- title: `JPJ to restore online vehicle ownership transfer service immediately, Anthony Loke announces`
- description: `PUTRAJAYA, May 25 — The Road Transport Department (JPJ) has agreed to immediately restore its online transfer of v...`
- link: `https://www.malaymail.com/news/malaysia/2026/05/25/jpj-to-restore-online-vehicle-ownership-transfer-service-immediately-anthony-loke-announces/221309`

Why include it:

- Tests administrative/service terminology.
- Directly relevant to the later pipeline because translated title/description may help Groq produce better Japanese summaries.

## Translation Trial Design

Phase 2C.1 should translate only these fields:

- `title`
- `description`

Fields that must not be translated or modified:

- `category`
- `source`
- `published_date`
- `published_at`
- `link`
- `canonical_key`
- `tags`
- `flags`
- `score`
- `reasons`
- `penalties`
- `background_value`
- `selected_summary`

Suggested prompt shape for each field:

```text
Translate the following RSS news text into Japanese.
Only output the translated Japanese.
Do not add facts.
Do not summarize.
Keep names, agencies, place names, dates, times, and numbers faithful.
Text:
...
```

For `description`, the translator should preserve source facts but remove no content by itself. Dateline removal should remain a display/summarization decision, not a translation-layer decision, unless a later phase explicitly changes that policy.

## translated_items.json Design

Proposed top-level structure:

```json
{
  "schema_version": "phase2c.translated_items.v1",
  "generated_at": "2026-05-25T00:00:00+08:00",
  "translation_engine": "hymt2-local-gguf",
  "model": "tencent/Hy-MT2-1.8B-GGUF:Q4_K_M",
  "source_json": "/tmp/malaysia_selected_items.json",
  "counts": {
    "input_items": 9,
    "translated_items": 3,
    "failed_items": 0
  },
  "items": []
}
```

Proposed item structure:

```json
{
  "index": 1,
  "category": "【速報】",
  "source": "Malay Mail",
  "published_date": "2026年5月25日",
  "title": "Thunderstorms, strong winds and heavy rain forecast across nine states until 8pm",
  "description": "KUALA LUMPUR, May 25 — ...",
  "translated_title": "午後8時まで9州で雷雨、強風、豪雨の予報",
  "translated_description": "クアラルンプール、5月25日 — ...",
  "link": "https://...",
  "translation_elapsed_ms": 0,
  "translation_status": "ok"
}
```

Notes:

- Preserve JSON item order.
- Use 1-based `index` for observation memo consistency.
- Store translation status per item, for example `ok`, `fallback`, `timeout`, `empty_output`, or `parse_error`.
- Do not include secrets, Groq configuration, auth headers, or HTTP bodies.
- Do not use translated text to alter category, score, or selection.

## Translation Observation Memo Design

Proposed memo sections:

```markdown
# Hy-MT2 Translation Observation Memo

generated_at:
model:
source_json:
items:

## Item 1

- category:
- source:
- published_date:
- link:

### Title

Original:

Translated:

### Description

Original:

Translated:

### Observation

- OK:
- 要注意:
- NG:
- 次回確認:
```

Review points:

- Numbers and times are preserved.
- Place names remain recognizable.
- Agencies such as JPJ, MetMalaysia, MOH, MCMC are not mistranslated.
- Malay administrative phrases are handled faithfully.
- Translation does not add facts or life-impact interpretation.
- Output does not include extra explanations.
- Japanese is not too literal or too stiff for later summarization.

## Phase 2C Roadmap

### Phase 2C.1: Minimal Translation Script

Create a local-only script such as:

```text
scripts/translate_selected_items_with_hymt2.py
```

Responsibilities:

- Read `selected_items.json`.
- Translate `title` and `description` only.
- Write `translated_items.json`.
- Use `llama-completion` or a controlled subprocess wrapper.
- Enforce per-field timeout.
- Keep item order and metadata unchanged.

### Phase 2C.2: Translation Observation Memo

Create a memo renderer:

```text
scripts/render_hymt2_translation_memo.py
```

Responsibilities:

- Read `translated_items.json`.
- Render original and translated title/description side by side.
- Support fast human review.

### Phase 2C.3: Hy-MT2 Translation -> Groq Summary Comparison

Run two local experiments:

```text
A: selected_items.json -> Groq display summary
B: selected_items.json -> Hy-MT2 translated_items.json -> Groq display summary
```

Compare:

- Japanese naturalness
- Faithfulness
- dateline cleanup
- BM/English handling
- hallucination risk
- Groq acceptance/fallback rate

### Phase 2C.4: BM-Only or Weak-Summary-Only Translation

If full translation is too slow or unnecessary, use Hy-MT2 only for:

- BM-heavy titles/descriptions
- items where Groq rendering is weak
- items with mixed Malay/English institutional phrasing

## Recommendation

Hy-MT2-1.8B Q4_K_M is feasible enough to continue local experiments on this MacBook Air, but not ready for production integration.

Recommended next step:

1. Use the already downloaded local GGUF file instead of `llama-cli -hf`.
2. Switch to `llama-completion` or a timeout-controlled wrapper.
3. Translate three `selected_items.json` items only.
4. Produce `translated_items.json` and a translation observation memo.
5. Decide whether Hy-MT2 improves Groq summaries enough to justify the extra local step.

## References

- Hy-MT2-1.8B: https://huggingface.co/tencent/Hy-MT2-1.8B
- Hy-MT2-1.8B-GGUF: https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF
- Hugging Face GGUF and llama.cpp: https://huggingface.co/docs/hub/en/gguf-llamacpp
- llama.cpp build documentation: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
