# Speaking Practice MVP

An isolated Next.js MVP for calm, mobile-first English speaking practice.

This app is intentionally separate from the static portfolio site at the repository root.

## What It Does

- Turns one Japanese work log into English interview practice material.
- Generates a 30-second answer, IPA, three questions, two repair phrases, and one focus-sound tip.
- Lets the learner rehearse, answer one question, and complete one transcript-based review.
- Provides a quiet mode for days when speaking is not practical.
- Keeps the original sentence-repeat MVP available as sentence mode.
- Stores only generated practice material and review summaries in `localStorage`.
- Does not require API text-to-speech in interview mode.

## Privacy Defaults

This first pass does not save raw audio files or the original work log.

The typed work log is sent to the server-side material generation route. If
`OPENAI_API_KEY` is set, that route calls the OpenAI API. If no key is set, it
returns a local fallback with the same JSON shape.

Audio is only captured after the mic is tapped, sent to the feedback route for
that attempt, transcribed with Groq Whisper when configured, and then discarded
by the UI. Progress stays on the device.

The transcript is shown on the review screen for that attempt only. It is not
saved to `localStorage`.

Stored progress:

- completed card IDs
- practice date
- sentence count
- streak dots
- privacy notice acknowledgement
- generated interview practice sessions

Before generating material, replace customer names, company names, project
names, and exact internal numbers with generic labels.

## Audio API Defaults

Interview mode uses Groq Whisper for speech-to-text:

```bash
GROQ_API_KEY=...
GROQ_STT_MODEL=whisper-large-v3-turbo
```

`GROQ_STT_MODEL` is optional. The accepted values are:

- `whisper-large-v3-turbo`
- `whisper-large-v3`

The MVP accepts direct browser recordings when their base MIME type is supported
by Groq STT. MIME parameters are ignored for support checks, so
`audio/webm;codecs=opus` is treated as `audio/webm`. The accepted base MIME
types are `audio/webm`, `audio/mp4`, `audio/mpeg`, `audio/mpga`, `audio/m4a`,
`audio/ogg`, and `audio/wav`. The primary target is Chrome/Edge `audio/webm`.
The app does not convert audio formats, chunk large audio, or run ffmpeg in this
phase.

If `GROQ_API_KEY` is not set, interview recording review does not return a fake
transcript or placeholder success. Use quiet mode instead.

Interview mode does not implement OpenAI TTS or Groq Orpheus. The sentence mode
browser read-aloud remains separate.

## Run Locally

```bash
cd speaking-practice
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Useful Commands

```bash
npm run typecheck
npm run build
```

## Feedback Routes

The mock server route is at:

```text
app/api/speaking-feedback/route.ts
```

Interview material generation is at:

```text
app/api/interview-materials/route.ts
```

For sentence mode, the feedback route still returns the existing mock:

- transcript: `I like chicken rice please`
- correction: `I would like chicken rice, please.`
- positive feedback: `Nice speaking!`
- next action: `Say it once more`

For interview mode, the same feedback route sends the current recording to Groq
Whisper and returns the transcript for the current review screen. It also returns
a structured communication review with one positive note, one or two fix points,
a structure suggestion, a focus-sound note, and the next focus sound.
