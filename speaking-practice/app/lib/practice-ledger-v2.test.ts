import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { migrateProgress } from "./progress";
import {
  convertLegacyPracticeDataToLedgerV2,
  convertToPracticeLedgerV2
} from "./practice-ledger-v2";
import { decodeVoicePracticeLedger } from "./voice-ledger";
import type {
  InterviewPracticeSession,
  PracticeSession
} from "@/types/speaking";
import type { VoicePracticeLedger } from "@/types/voice-ledger";

function loadFixture(name: string): unknown {
  return JSON.parse(
    readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8")
  );
}

function collectKeys(value: unknown, keys = new Set<string>()): Set<string> {
  if (Array.isArray(value)) {
    value.forEach((item) => collectKeys(item, keys));
    return keys;
  }

  if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, child]) => {
      keys.add(key);
      collectKeys(child, keys);
    });
  }

  return keys;
}

function collectStringValues(
  value: unknown,
  values = new Set<string>()
): Set<string> {
  if (Array.isArray(value)) {
    value.forEach((item) => collectStringValues(item, values));
    return values;
  }

  if (typeof value === "string") {
    values.add(value);
    return values;
  }

  if (value && typeof value === "object") {
    Object.values(value).forEach((child) => collectStringValues(child, values));
  }

  return values;
}

test("converts canonical Voice Ledger and Interview history into Ledger v2", () => {
  const voiceDecoded = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const progress = migrateProgress(loadFixture("progress-v1-valid.json"));

  assert.equal(voiceDecoded.canWrite, true);

  const result = convertToPracticeLedgerV2({
    voiceLedger: voiceDecoded.ledger,
    progress
  });

  assert.equal(result.ledger.schemaVersion, 2);
  assert.equal(result.ledger.entries.length, 4);
  assert.deepEqual(result.ledger.entries.map((entry) => entry.id), [
    "voice-session-2",
    "voice-session-1",
    "legacy-recording",
    "legacy-quiet"
  ]);
  assert.deepEqual(result.diagnostics, {
    convertedVoiceEntryCount: 2,
    convertedInterviewSessionCount: 2,
    convertedExternalVoiceSessionCount: 0,
    unconvertedSentenceHistory: {
      completedCardIds: ["restaurant-order"]
    }
  });

  const interviewEntry = result.ledger.entries.find(
    (entry) => entry.id === "legacy-recording"
  );
  assert.ok(interviewEntry && interviewEntry.practiceKind === "interview");
  assert.equal(interviewEntry.source, "in_app_recording");
  assert.equal(interviewEntry.reviewBasis, "transcript_based");
  assert.equal(interviewEntry.plannedFocusSound, "/h/");
  assert.equal(interviewEntry.observedFocusSoundCandidate, null);
  assert.equal(interviewEntry.nextFocusSound, "/h/");
  assert.equal(interviewEntry.nextMission, "Use result, action, impact.");
  assert.equal(interviewEntry.details.completionMode, "recorded");
});

test("converts Voice Ledger v1 and Progress fixtures into the expected v2 ledger", () => {
  const result = convertLegacyPracticeDataToLedgerV2({
    voiceLedger: loadFixture("voice-ledger-v1-valid.json"),
    progress: loadFixture("progress-v1-valid.json")
  });

  assert.equal(result.status, "ok");
  assert.ok(result.ledger);
  assert.deepEqual(
    result.ledger,
    loadFixture("practice-ledger-v2-from-v1-and-progress.json")
  );
  assert.deepEqual(result.diagnostics, {
    voiceLedger: {
      status: "ok",
      canWrite: true,
      details: {
        sourceVersion: 1,
        acceptedEntryCount: 2,
        droppedEntryCount: 0,
        codes: []
      }
    },
    progress: {
      status: "ok",
      canWrite: true,
      details: {
        sourceVersion: null,
        acceptedSessionCount: 2,
        droppedSessionCount: 0,
        codes: []
      }
    }
  });
});

test("blocks Ledger v2 output when either legacy source cannot be safely read", () => {
  const result = convertLegacyPracticeDataToLedgerV2({
    voiceLedger: loadFixture("voice-ledger-v2-future.json"),
    progress: loadFixture("progress-v3-future.json")
  });

  assert.equal(result.status, "blocked");
  assert.equal(result.ledger, null);
  assert.equal(result.diagnostics.voiceLedger.status, "unsupported_version");
  assert.equal(result.diagnostics.progress.status, "unsupported_version");
});

test("converts an external Voice self-report without inventing focus-sound data", () => {
  const result = convertToPracticeLedgerV2({
    voiceLedger: emptyVoiceLedger(),
    progress: migrateProgress(loadFixture("progress-v2-external.json"))
  });
  const entry = result.ledger.entries[0];

  assert.ok(entry && entry.practiceKind === "voice");
  assert.equal(entry.source, "external_voice");
  assert.equal(entry.reviewBasis, "self_report");
  assert.equal(entry.context, null);
  assert.equal(entry.summary, "I used a fixed clarification phrase.");
  assert.equal(
    entry.nextMission,
    "Clarify, then answer directly in one sentence."
  );
  assert.equal(entry.plannedFocusSound, null);
  assert.equal(entry.observedFocusSoundCandidate, null);
  assert.equal(entry.nextFocusSound, null);
  assert.deepEqual(entry.details.stickingPoints, [
    "I initially misunderstood the question."
  ]);
});

test("does not retain raw audio, transcripts, or source text in the converted ledger", () => {
  const voiceDecoded = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const result = convertToPracticeLedgerV2({
    voiceLedger: voiceDecoded.ledger,
    progress: migrateProgress(loadFixture("progress-v1-valid.json"))
  });
  const keys = collectKeys(result.ledger);

  assert.ok(!keys.has("audio"));
  assert.ok(!keys.has("rawAudio"));
  assert.ok(!keys.has("transcript"));
  assert.ok(!keys.has("rawTranscript"));
  assert.ok(!keys.has("sourceText"));
  assert.ok(!keys.has("workLog"));
});

test("keeps service and input-adapter identifiers out of the canonical ledger", () => {
  const voiceDecoded = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const result = convertToPracticeLedgerV2({
    voiceLedger: voiceDecoded.ledger,
    progress: migrateProgress(loadFixture("progress-v2-external.json"))
  });
  const keys = collectKeys(result.ledger);
  const values = collectStringValues(result.ledger);

  assert.ok(!keys.has("practiceSource"));
  assert.ok(!keys.has("sourceKind"));
  assert.ok(!values.has("chatgpt_voice"));
  assert.ok(!values.has("voice_transcript"));
  assert.ok(!values.has("chatgpt_summary"));
  assert.ok(!values.has("manual"));
});

test("returns cloned arrays so conversion never mutates its inputs", () => {
  const voiceDecoded = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const progress = migrateProgress(loadFixture("progress-v1-valid.json"));
  const result = convertToPracticeLedgerV2({
    voiceLedger: voiceDecoded.ledger,
    progress
  });
  const voiceEntry = result.ledger.entries.find(
    (entry) => entry.id === "voice-session-1"
  );
  const interviewEntry = result.ledger.entries.find(
    (entry) => entry.id === "legacy-recording"
  );
  const originalInterview = progress.practiceSessions.find(
    isInterviewPracticeSession
  );

  assert.ok(voiceEntry && voiceEntry.practiceKind === "voice");
  assert.ok(interviewEntry && interviewEntry.practiceKind === "interview");
  assert.ok(originalInterview);

  voiceEntry.details.usefulExpressions.push("Changed after conversion");
  interviewEntry.details.review.fixPoints.push("Changed after conversion");

  assert.equal(
    voiceDecoded.ledger.entries[0].usefulExpressions.includes(
      "Changed after conversion"
    ),
    false
  );
  assert.equal(
    originalInterview.review.fixPoints.includes(
      "Changed after conversion"
    ),
    false
  );
});

function emptyVoiceLedger(): VoicePracticeLedger {
  return {
    schemaVersion: 1,
    entries: []
  };
}

function isInterviewPracticeSession(
  session: PracticeSession
): session is InterviewPracticeSession {
  return "review" in session;
}
