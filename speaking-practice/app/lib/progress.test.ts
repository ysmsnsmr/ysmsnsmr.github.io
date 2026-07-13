import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { migrateProgress } from "./progress";

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

test("migrates legacy recording and quiet sessions to schema version 2", () => {
  const progress = migrateProgress(loadFixture("progress-v1-valid.json"));

  assert.equal(progress.schemaVersion, 2);
  assert.equal(progress.practiceSessions.length, 2);
  assert.equal(progress.practiceSessions[0].practiceSource, "in_app_recording");
  assert.equal(progress.practiceSessions[0].reflectionKind, "transcript_based");
  assert.equal(progress.practiceSessions[1].practiceSource, "quiet_mode");
  assert.equal(progress.practiceSessions[1].reflectionKind, "self_report");
  assert.equal(progress.practiceSessions[0].whatWentWell, null);
  assert.equal(progress.practiceSessions[0].stuckOn, null);
  assert.equal(progress.practiceSessions[0].nextPracticeFocus, null);
  assert.equal(progress.practiceSessions[0].topic, "Workflow improvement");
});

test("removes non-canonical private fields during migration", () => {
  const progress = migrateProgress(loadFixture("progress-v1-valid.json"));
  const keys = collectKeys(progress);

  assert.ok(!keys.has("interviewSessions"));
  assert.ok(!keys.has("transcript"));
  assert.ok(!keys.has("rawTranscript"));
  assert.ok(!keys.has("audio"));
  assert.ok(!keys.has("workLog"));
});

test("keeps valid sessions when corrupt history entries are present", () => {
  const progress = migrateProgress(loadFixture("progress-v1-corrupt.json"));

  assert.equal(progress.practiceSessions.length, 1);
  assert.equal(progress.practiceSessions[0].id, "valid-among-corrupt");
});

test("normalizes an external Voice self-report without transcript data", () => {
  const progress = migrateProgress(loadFixture("progress-v2-external.json"));
  const session = progress.practiceSessions[0];

  assert.equal(session.practiceSource, "chatgpt_voice");
  assert.equal(session.reflectionKind, "self_report");
  assert.equal(session.whatWentWell, "I used a fixed clarification phrase.");
  assert.equal(
    session.nextPracticeFocus,
    "Clarify, then answer directly in one sentence."
  );
  assert.ok(!collectKeys(progress).has("transcript"));
  assert.ok(!collectKeys(progress).has("rawAudio"));
});

test("normalization is idempotent and never emits acoustic measurement", () => {
  const fixture = loadFixture("progress-v2-external.json") as {
    practiceSessions: Array<Record<string, unknown>>;
  };
  fixture.practiceSessions[0].reflectionKind = "acoustic_measurement";

  const once = migrateProgress(fixture);
  const twice = migrateProgress(once);

  assert.deepEqual(twice, once);
  assert.equal(once.practiceSessions[0].reflectionKind, "self_report");
  assert.ok(!JSON.stringify(twice).includes("acoustic_measurement"));
});

test("returns a fresh schema version 2 default for unusable input", () => {
  const first = migrateProgress(null);
  const second = migrateProgress(null);

  assert.equal(first.schemaVersion, 2);
  assert.deepEqual(first.practiceSessions, []);
  assert.notEqual(first.practiceSessions, second.practiceSessions);
});
