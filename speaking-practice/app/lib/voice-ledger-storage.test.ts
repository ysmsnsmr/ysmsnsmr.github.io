import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  appendVoicePracticeEntry,
  loadVoicePracticeLedger,
  VoiceLedgerWriteBlockedError,
  type VoiceLedgerStorage
} from "./voice-ledger-storage";
import { decodeVoicePracticeLedger } from "./voice-ledger";
import type { VoicePracticeEntry } from "@/types/voice-ledger";

function loadFixture(name: string): unknown {
  return JSON.parse(
    readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8")
  );
}

function createMemoryStorage(
  initialValue: string | null,
  options: { failOnSet?: boolean } = {}
) {
  const state = {
    value: initialValue,
    setCalls: 0
  };
  const storage: VoiceLedgerStorage = {
    getItem() {
      return state.value;
    },
    setItem(_key, value) {
      state.setCalls += 1;
      if (options.failOnSet) {
        throw new Error("quota exceeded");
      }
      state.value = value;
    }
  };

  return { state, storage };
}

function loadValidEntry(): VoicePracticeEntry {
  const decoded = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  );
  return decoded.ledger.entries[0];
}

test("loads an empty ledger without writing to storage", () => {
  const { state, storage } = createMemoryStorage(null);

  const result = loadVoicePracticeLedger(storage);

  assert.equal(result.status, "empty");
  assert.equal(result.canWrite, true);
  assert.deepEqual(result.ledger.entries, []);
  assert.equal(state.setCalls, 0);
});

test("appends and reloads a canonical manual entry", () => {
  const { state, storage } = createMemoryStorage(null);
  const entry = {
    ...loadValidEntry(),
    sourceKind: "manual" as const,
    sourceText: "must not be stored",
    transcript: "must not be stored"
  };

  const saved = appendVoicePracticeEntry(entry, storage);
  const reloaded = loadVoicePracticeLedger(storage);

  assert.equal(saved.entries.length, 1);
  assert.equal(reloaded.status, "ok");
  assert.equal(reloaded.ledger.entries[0].sourceKind, "manual");
  assert.equal(state.setCalls, 1);
  assert.ok(!state.value?.includes("sourceText"));
  assert.ok(!state.value?.includes("transcript"));
});

test("appends a parsed Voice summary without retaining its raw source", () => {
  const { state, storage } = createMemoryStorage(null);
  const entry = {
    ...loadValidEntry(),
    sourceKind: "chatgpt_summary" as const,
    sourceText: "full Voice summary must not be stored",
    rawTranscript: "must not be stored"
  };

  const saved = appendVoicePracticeEntry(entry, storage);

  assert.equal(saved.entries[0].sourceKind, "chatgpt_summary");
  assert.ok(!state.value?.includes("full Voice summary"));
  assert.ok(!state.value?.includes("rawTranscript"));
});

test("blocks writes when future-version data already exists", () => {
  const original = JSON.stringify(
    loadFixture("voice-ledger-v2-future.json")
  );
  const { state, storage } = createMemoryStorage(original);

  assert.throws(
    () => appendVoicePracticeEntry(loadValidEntry(), storage),
    VoiceLedgerWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes when stored JSON is invalid", () => {
  const original = "{not-json";
  const { state, storage } = createMemoryStorage(original);

  assert.throws(
    () => appendVoicePracticeEntry(loadValidEntry(), storage),
    VoiceLedgerWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("does not change the in-memory ledger when storage rejects a write", () => {
  const { state, storage } = createMemoryStorage(null, {
    failOnSet: true
  });

  assert.throws(
    () => appendVoicePracticeEntry(loadValidEntry(), storage),
    /quota exceeded/
  );
  assert.equal(state.value, null);
  assert.equal(state.setCalls, 1);
});
