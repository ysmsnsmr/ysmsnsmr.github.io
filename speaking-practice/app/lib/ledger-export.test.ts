import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  createMigrationBackup,
  createPracticeLedgerExport,
  createPracticeLedgerExportJson,
  MigrationBackupWriteBlockedError,
  PRACTICE_LEDGER_MIGRATION_BACKUP_KEY,
  saveMigrationBackup,
  type LedgerExportStorage
} from "./ledger-export";
import { migrateProgress } from "./progress";
import { convertLegacyPracticeDataToLedgerV2 } from "./practice-ledger-v2";
import { decodeVoicePracticeLedger } from "./voice-ledger";

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

function loadCanonicalSources() {
  const voiceLedger = decodeVoicePracticeLedger(
    loadFixture("voice-ledger-v1-valid.json")
  ).ledger;
  const progress = migrateProgress(loadFixture("progress-v1-valid.json"));
  const conversion = convertLegacyPracticeDataToLedgerV2({
    voiceLedger,
    progress
  });
  assert.ok(conversion.ledger);
  return { voiceLedger, progress, ledger: conversion.ledger };
}

test("exports only Ledger v2 and preserves pending sentence history", () => {
  const { ledger } = loadCanonicalSources();
  const exportData = createPracticeLedgerExport({
    ledger,
    pendingSentenceHistory: ["restaurant-order"],
    exportedAt: "2026-08-06T00:00:00.000Z"
  });

  assert.equal(exportData.format, "speaking-practice-ledger-export");
  assert.equal(exportData.exportVersion, 1);
  assert.equal(exportData.ledger.schemaVersion, 2);
  assert.deepEqual(exportData.pendingSentenceHistory, ["restaurant-order"]);
  assert.deepEqual(JSON.parse(createPracticeLedgerExportJson({
    ledger,
    pendingSentenceHistory: ["restaurant-order"],
    exportedAt: "2026-08-06T00:00:00.000Z"
  })), exportData);
});

test("does not include adapter or private source fields in the JSON export", () => {
  const { ledger } = loadCanonicalSources();
  const exported = JSON.parse(
    createPracticeLedgerExportJson({
      ledger,
      pendingSentenceHistory: []
    })
  );
  const keys = collectKeys(exported);
  const serialized = JSON.stringify(exported);

  assert.ok(!keys.has("sourceKind"));
  assert.ok(!keys.has("practiceSource"));
  assert.ok(!keys.has("transcript"));
  assert.ok(!keys.has("rawTranscript"));
  assert.ok(!keys.has("audio"));
  assert.ok(!keys.has("workLog"));
  assert.ok(!serialized.includes("raw source must not survive"));
});

test("creates a normalized migration backup without mutating its inputs", () => {
  const { voiceLedger, progress } = loadCanonicalSources();
  const backup = createMigrationBackup({
    voiceLedger,
    progress,
    createdAt: "2026-08-06T00:00:00.000Z"
  });

  assert.equal(backup.format, "speaking-practice-migration-backup");
  assert.equal(backup.backupVersion, 1);
  assert.equal(backup.createdAt, "2026-08-06T00:00:00.000Z");
  assert.notEqual(backup.source.voiceLedger, voiceLedger);
  assert.notEqual(backup.source.progress, progress);
  assert.ok(!JSON.stringify(backup).includes("sourceText"));
  assert.ok(!JSON.stringify(backup).includes("rawAudio"));
  assert.ok(!JSON.stringify(backup).includes("rawTranscript"));
});

test("writes a migration backup once and never overwrites it implicitly", () => {
  const { voiceLedger, progress } = loadCanonicalSources();
  const state = new Map<string, string>();
  const storage: LedgerExportStorage = {
    getItem(key) {
      return state.get(key) ?? null;
    },
    setItem(key, value) {
      state.set(key, value);
    }
  };
  const backup = createMigrationBackup({
    voiceLedger,
    progress,
    createdAt: "2026-08-06T00:00:00.000Z"
  });

  saveMigrationBackup(backup, storage);
  const original = state.get(PRACTICE_LEDGER_MIGRATION_BACKUP_KEY);
  assert.ok(original);

  assert.throws(
    () => saveMigrationBackup(backup, storage),
    (error: unknown) =>
      error instanceof MigrationBackupWriteBlockedError &&
      error.code === "backup_already_exists"
  );
  assert.equal(state.get(PRACTICE_LEDGER_MIGRATION_BACKUP_KEY), original);
});
