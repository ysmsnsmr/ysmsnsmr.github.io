import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createSentencePracticeLedgerEntry } from "./practice-ledger-entry";
import {
  appendPracticeLedgerEntryToV2,
  syncLegacySourcesAndAppendPracticeLedgerEntry,
  syncLegacySourcesToPracticeLedgerV2
} from "./practice-ledger-sync";
import { PRACTICE_LEDGER_V2_STORAGE_KEY } from "./practice-ledger-import";
import type { LessonCard } from "@/types/speaking";

function loadFixture(name: string): string {
  return readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8");
}

function createStorage() {
  const values = new Map<string, string>();
  values.set("voice-practice-ledger", loadFixture("voice-ledger-v1-valid.json"));
  values.set("speaking-practice-progress", loadFixture("progress-v1-valid.json"));
  return {
    values,
    storage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value)
    }
  };
}

const lesson: LessonCard = {
  id: "restaurant-order",
  scenario: "Ordering at a restaurant",
  mode: "repeat",
  sentence: "Could I have the menu, please?",
  level: "beginner"
};

test("creates a service-independent Sentence Ledger entry", () => {
  const entry = createSentencePracticeLedgerEntry(
    lesson,
    "2026-08-06T10:00:00.000Z",
    "sentence-entry-1"
  );

  assert.deepEqual(entry, {
    id: "sentence-entry-1",
    occurredAt: "2026-08-06T10:00:00.000Z",
    createdAt: "2026-08-06T10:00:00.000Z",
    updatedAt: "2026-08-06T10:00:00.000Z",
    practiceKind: "sentence",
    source: "sentence_practice",
    reviewBasis: "none",
    context: null,
    title: "Ordering at a restaurant",
    summary: "Could I have the menu, please?",
    nextMission: null,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
      lessonId: "restaurant-order",
      sentence: "Could I have the menu, please?",
      scenario: "Ordering at a restaurant",
      level: "beginner"
    }
  });
});

test("syncs completed Interview history and appends a new Sentence entry to v2", () => {
  const { values, storage } = createStorage();
  const synced = syncLegacySourcesToPracticeLedgerV2(storage);
  assert.equal(synced.entries.length, 4);

  const entry = createSentencePracticeLedgerEntry(
    lesson,
    "2026-08-06T10:00:00.000Z",
    "sentence-entry-2"
  );
  const result = syncLegacySourcesAndAppendPracticeLedgerEntry(
    entry,
    [lesson.id],
    storage
  );

  assert.equal(result.addedEntryCount, 1);
  assert.ok(result.ledger.entries.some((item) => item.id === "sentence-entry-2"));
  assert.ok(values.has(PRACTICE_LEDGER_V2_STORAGE_KEY));
});

test("appends a new Interview or Sentence entry without changing the legacy keys", () => {
  const { values, storage } = createStorage();
  const voiceBefore = values.get("voice-practice-ledger");
  const progressBefore = values.get("speaking-practice-progress");
  const entry = createSentencePracticeLedgerEntry(
    lesson,
    "2026-08-06T11:00:00.000Z",
    "sentence-entry-3"
  );

  appendPracticeLedgerEntryToV2(entry, [lesson.id], storage);

  assert.equal(values.get("voice-practice-ledger"), voiceBefore);
  assert.equal(values.get("speaking-practice-progress"), progressBefore);
});
