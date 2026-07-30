import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  decodeVoicePracticeLedger,
  normalizeVoicePracticeEntry,
  normalizeVoicePracticeLedger
} from "./voice-ledger";

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

test("decodes a valid schema version 1 ledger", () => {
  const result = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );

  assert.equal(result.status, "ok");
  assert.equal(result.canWrite, true);
  assert.equal(result.ledger.schemaVersion, 1);
  assert.equal(result.ledger.entries.length, 2);
  assert.deepEqual(result.diagnostics, {
    sourceVersion: 1,
    acceptedEntryCount: 2,
    droppedEntryCount: 0,
    codes: []
  });
});

test("normalizes strings and optional values into the canonical entry shape", () => {
  const result = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const entry = result.ledger.entries[0];

  assert.equal(entry.id, "voice-session-1");
  assert.equal(entry.title, "Clarifying a work question");
  assert.equal(
    entry.usefulExpressions[0],
    "Could you clarify what you mean?"
  );
  assert.equal(entry.selfNote, null);
  assert.equal(entry.sourceKind, "voice_transcript");
});

test("never emits pasted source, transcript, or raw audio fields", () => {
  const ledger = normalizeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const keys = collectKeys(ledger);

  assert.ok(!keys.has("sourceText"));
  assert.ok(!keys.has("transcript"));
  assert.ok(!keys.has("rawTranscript"));
  assert.ok(!keys.has("audio"));
  assert.ok(!keys.has("rawAudio"));
});

test("keeps valid entries and diagnoses corrupt entries without allowing writes", () => {
  const fixture = loadFixture("voice-ledger-v1-corrupt.json");
  const result = decodeVoicePracticeLedger(
    fixture
  );

  assert.equal(result.status, "ok");
  assert.equal(result.canWrite, false);
  assert.equal(result.ledger.entries.length, 1);
  assert.equal(result.ledger.entries[0].id, "valid-entry");
  assert.equal(result.diagnostics.acceptedEntryCount, 1);
  assert.equal(result.diagnostics.droppedEntryCount, 4);
  assert.deepEqual(result.diagnostics.codes, ["dropped_invalid_entry"]);
  assert.equal(normalizeVoicePracticeLedger(fixture), null);
});

test("rejects future schema versions instead of downgrading them", () => {
  const result = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v2-future.json")
  );

  assert.equal(result.status, "unsupported_version");
  assert.equal(result.canWrite, false);
  assert.equal(result.diagnostics.sourceVersion, 2);
  assert.deepEqual(result.diagnostics.codes, [
    "unsupported_future_version"
  ]);
  assert.deepEqual(result.ledger.entries, []);
});

test("requires an explicit schema version and entries array", () => {
  const missingVersion = decodeVoicePracticeLedger({ entries: [] });
  const missingEntries = decodeVoicePracticeLedger({ schemaVersion: 1 });

  assert.equal(missingVersion.status, "invalid");
  assert.deepEqual(missingVersion.diagnostics.codes, [
    "missing_schema_version"
  ]);
  assert.equal(missingEntries.status, "invalid");
  assert.deepEqual(missingEntries.diagnostics.codes, ["invalid_entries"]);
});

test("normalization is idempotent", () => {
  const once = normalizeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  const twice = normalizeVoicePracticeLedger(once);

  assert.deepEqual(twice, once);
});

test("rejects invalid entry enums, durations, and empty list items", () => {
  const validLedger = loadFixture("voice-ledger-v1-valid.json") as {
    entries: Array<Record<string, unknown>>;
  };
  const validEntry = validLedger.entries[0];

  assert.equal(
    normalizeVoicePracticeEntry({ ...validEntry, context: "unknown" }),
    null
  );
  assert.equal(
    normalizeVoicePracticeEntry({ ...validEntry, sessionMinutes: 0 }),
    null
  );
  assert.equal(
    normalizeVoicePracticeEntry({
      ...validEntry,
      usefulExpressions: [""]
    }),
    null
  );
  assert.equal(
    normalizeVoicePracticeEntry({ ...validEntry, selfNote: 42 }),
    null
  );
});
