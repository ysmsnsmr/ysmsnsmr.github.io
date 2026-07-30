import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  parseVoiceSessionLog,
  VOICE_SESSION_LOG_PROMPT
} from "./voice-session-log";

const defaults = {
  practicedAt: "2026-07-22",
  context: "work" as const
};

function loadFixture(name: string) {
  return readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8");
}

test("converts the complete ten-label Markdown log into a ledger draft", () => {
  const result = parseVoiceSessionLog(
    loadFixture("voice-session-log-complete.md").replaceAll("\n", "\r\n"),
    defaults
  );

  assert.equal(result.status, "ready");
  assert.deepEqual(result.missingFields, []);
  assert.equal(result.draft.practicedAt, "2026-07-21");
  assert.equal(result.draft.context, "work");
  assert.equal(result.draft.title, "顧客への優先順位の説明: 緊急案件");
  assert.equal(result.draft.sessionMinutes, "15");
  assert.equal(
    result.draft.summary,
    "良かった点: I gave the conclusion first.\n最優先で直す点: I need to pause before explaining details."
  );
  assert.deepEqual(result.draft.usefulExpressions, [
    "Could you clarify what you mean?",
    "I would handle the urgent task first."
  ]);
  assert.deepEqual(result.draft.stickingPoints, [
    "重点音: /h/",
    "聞き取りにくかった表現: priority"
  ]);
  assert.deepEqual(result.draft.corrections, [
    "I need to pause before explaining details."
  ]);
  assert.equal(
    result.draft.nextMission,
    "次回の課題: Answer the question in one sentence first.\n5分宿題: Say the first sentence three times."
  );
  assert.equal(
    result.draft.selfNote,
    "I used a clarification phrase without stopping."
  );
  assert.ok(!JSON.stringify(result).includes("内部メモ"));
  assert.ok(!JSON.stringify(result).includes("That is all"));
});

test("returns warnings and defaults for missing or invalid optional values", () => {
  const result = parseVoiceSessionLog(
    "# 2026-02-30\nテーマ: Daily update\n練習時間: fifteen\n良かった点: I started quickly.\n最優先で直す点: Keep the answer shorter.\n次回の課題: Give one direct sentence first.",
    defaults
  );

  assert.equal(result.status, "ready");
  assert.equal(result.draft.practicedAt, defaults.practicedAt);
  assert.equal(result.draft.sessionMinutes, "");
  assert.ok(result.warnings.some((warning) => warning.includes("日付が不正")));
  assert.ok(result.warnings.some((warning) => warning.includes("練習時間は正の整数")));
  assert.ok(result.warnings.some((warning) => warning.includes("任意項目")));
});

test("keeps an incomplete draft editable when a required label is absent", () => {
  const result = parseVoiceSessionLog(
    "テーマ: Small improvement\n良かった点: I explained the result.\n次回の課題: Practice one direct answer.",
    defaults
  );

  assert.equal(result.status, "incomplete");
  assert.deepEqual(result.missingFields, ["最優先で直す点"]);
  assert.equal(result.draft.title, "Small improvement");
  assert.equal(result.draft.nextMission, "次回の課題: Practice one direct answer.");
});

test("treats none markers as blank and only returns known fields", () => {
  const result = parseVoiceSessionLog(
    "# 2026-07-22\nテーマ: Test\n練習時間: 10\n今日の重点音: なし\n良かった点: Good\n最優先で直す点: Improve\n聞き取りにくかった単語・表現: N/A\n練習した自然な文: 特になし\n前回からの変化: なし\n次回の課題: Repeat\n5分宿題: N/A\ntranscript: confidential source text",
    defaults
  );

  assert.equal(result.status, "ready");
  assert.deepEqual(result.draft.usefulExpressions, []);
  assert.deepEqual(result.draft.stickingPoints, []);
  assert.equal(result.draft.selfNote, "");
  assert.ok(!result.warnings.some((warning) => warning.includes("任意項目")));
  assert.ok(!JSON.stringify(result).includes("confidential source text"));
});

test("prompt gives the exact date heading and all ten expected labels", () => {
  assert.ok(VOICE_SESSION_LOG_PROMPT.includes("# YYYY-MM-DD"));
  [
    "テーマ",
    "練習時間",
    "今日の重点音",
    "良かった点",
    "最優先で直す点",
    "聞き取りにくかった単語・表現",
    "練習した自然な文",
    "前回からの変化",
    "次回の課題",
    "5分宿題"
  ].forEach((label) => assert.ok(VOICE_SESSION_LOG_PROMPT.includes(label)));
});
