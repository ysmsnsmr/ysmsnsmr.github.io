import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  importPracticeLedgerV2NonDestructively,
  loadStoredPracticeLedgerV2,
  PRACTICE_LEDGER_PENDING_SENTENCE_HISTORY_KEY,
  PRACTICE_LEDGER_V2_STORAGE_KEY,
  previewPracticeLedgerImportJson,
  PracticeLedgerImportWriteBlockedError,
  type PracticeLedgerV2Storage
} from "./practice-ledger-import";

function loadFixture(name: string): string {
  return readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8");
}

function createStorage(initial: string | null = null) {
  const state = new Map<string, string>();
  if (initial) {
    state.set(PRACTICE_LEDGER_V2_STORAGE_KEY, initial);
  }
  const storage: PracticeLedgerV2Storage = {
    getItem: (key) => state.get(key) ?? null,
    setItem: (key, value) => state.set(key, value)
  };
  return { state, storage };
}

test("previews a valid Ledger v2 export without writing storage", () => {
  const { state } = createStorage();
  const preview = previewPracticeLedgerImportJson(
    loadFixture("practice-ledger-v2-export.json")
  );

  assert.equal(preview.status, "valid");
  assert.equal(preview.source, "ledger_export");
  assert.equal(preview.entryCount, 1);
  assert.equal(preview.newEntryCount, 1);
  assert.equal(state.size, 0);
});

test("rejects invalid JSON and private fields without writing storage", () => {
  const invalid = JSON.stringify({
    format: "speaking-practice-ledger-export",
    exportVersion: 1,
    ledger: {
      schemaVersion: 2,
      entries: [
        {
          id: "unsafe",
          practiceKind: "voice",
          source: "external_voice",
          reviewBasis: "self_report",
          transcript: "must not be imported"
        }
      ]
    },
    pendingSentenceHistory: []
  });
  const preview = previewPracticeLedgerImportJson(invalid);

  assert.equal(preview.status, "invalid");
  assert.ok(preview.errors.length > 0);
});

test("shows duplicate entries in preview and preserves existing entries on apply", () => {
  const imported = JSON.parse(loadFixture("practice-ledger-v2-export.json"));
  const existing = JSON.parse(JSON.stringify(imported.ledger));
  const { state, storage } = createStorage(JSON.stringify(existing));
  const preview = previewPracticeLedgerImportJson(
    JSON.stringify(imported),
    existing
  );

  assert.equal(preview.status, "valid");
  assert.equal(preview.newEntryCount, 0);
  assert.equal(preview.duplicateEntryCount, 1);

  const result = importPracticeLedgerV2NonDestructively(preview.ledger!, storage);
  assert.equal(result.addedEntryCount, 0);
  assert.equal(result.duplicateEntryCount, 1);
  assert.deepEqual(JSON.parse(state.get(PRACTICE_LEDGER_V2_STORAGE_KEY)!), existing);
});

test("imports into a separate v2 key and keeps legacy keys untouched", () => {
  const imported = JSON.parse(loadFixture("practice-ledger-v2-export.json"));
  const { state, storage } = createStorage();
  state.set("voice-practice-ledger", "legacy voice data");
  state.set("speaking-practice-progress", "legacy progress data");

  const result = importPracticeLedgerV2NonDestructively(imported.ledger, storage);

  assert.equal(result.addedEntryCount, 1);
  assert.equal(state.get("voice-practice-ledger"), "legacy voice data");
  assert.equal(state.get("speaking-practice-progress"), "legacy progress data");
  assert.equal(loadStoredPracticeLedgerV2(storage).status, "ok");
});

test("keeps pending Sentence history during non-destructive import", () => {
  const imported = JSON.parse(loadFixture("practice-ledger-v2-export.json"));
  const { state, storage } = createStorage();

  importPracticeLedgerV2NonDestructively(
    imported.ledger,
    storage,
    ["restaurant-order"]
  );

  assert.deepEqual(
    JSON.parse(state.get(PRACTICE_LEDGER_PENDING_SENTENCE_HISTORY_KEY)!),
    ["restaurant-order"]
  );
});

test("blocks import when the existing v2 ledger is invalid", () => {
  const { storage } = createStorage("{not-json");
  const imported = JSON.parse(loadFixture("practice-ledger-v2-export.json"));

  assert.throws(
    () => importPracticeLedgerV2NonDestructively(imported.ledger, storage),
    (error: unknown) =>
      error instanceof PracticeLedgerImportWriteBlockedError &&
      error.code === "unsafe_stored_ledger"
  );
});
