const assert = require("assert");
const lab = require("./app.js");

const rightLesson = lab.LESSONS.find((lesson) => lesson.id === "r-l-right-light-013");

function assertSingleImprovement(result) {
  assert.strictEqual(typeof result.improvement, "string");
  assert.ok(result.improvement.length > 0);
  assert.ok(!Array.isArray(result.improvement));
}

for (const lesson of lab.LESSONS) {
  const validation = lab.validateLesson(lesson);
  assert.deepStrictEqual(validation, { ok: true }, `${lesson.id} should be valid`);
}

assert.deepStrictEqual(
  lab.normalizeToTokens("  I turned RIGHT, at   the light. "),
  ["i", "turned", "right", "at", "the", "light"]
);

{
  const result = lab.judgeTranscript(rightLesson, "I turned light at the light.");
  assert.strictEqual(result.status, "common_mishearing");
  assert.strictEqual(
    result.message,
    "right /raɪt/ が light /laɪt/ に聞こえた可能性があります"
  );
  assertSingleImprovement(result);
}

{
  const result = lab.judgeTranscript(rightLesson, "I turned right at the light.");
  assert.strictEqual(result.status, "focus_match");
  assert.strictEqual(
    result.message,
    "right /raɪt/ の /r/ は再現できている可能性があります"
  );
  assert.strictEqual(result.scoreNote, "文字起こしベースの推定");
  assertSingleImprovement(result);
}

{
  const result = lab.judgeTranscript(rightLesson, "I turned right at the light.");
  assert.notStrictEqual(result.status, "common_mishearing");
}

{
  const result = lab.judgeTranscript(rightLesson, "I turned bright at the light.");
  assert.strictEqual(result.status, "focus_token_missing");
  assert.strictEqual(result.message, "重点語が文字起こしに含まれていません");
  assertSingleImprovement(result);
}

{
  const result = lab.judgeTranscript(rightLesson, "I turned");
  assert.strictEqual(result.status, "unable");
  assert.strictEqual(result.reason, "too_short");
  assert.strictEqual(result.score, null);
  assert.strictEqual(result.title, "判定できません");
}

{
  const result = lab.judgeTranscript(rightLesson, "");
  assert.strictEqual(result.reason, "empty_transcript");
  assert.strictEqual(result.score, null);
}

{
  const result = lab.judgeTranscript(rightLesson, "今日は");
  assert.strictEqual(result.reason, "non_english_transcript");
  assert.strictEqual(result.score, null);
}

{
  const result = lab.judgeTranscript(rightLesson, "we enjoy coffee today");
  assert.strictEqual(result.reason, "transcript_too_different");
  assert.strictEqual(result.score, null);
}

{
  const invalidLesson = {
    ...rightLesson,
    id: "invalid-focus-index",
    focusTokenIndex: 3
  };
  const validation = lab.validateLesson(invalidLesson);
  assert.strictEqual(validation.ok, false);
  assert.strictEqual(validation.reason, "focus_token_index_mismatch");
}

{
  assert.strictEqual(lab.getCuePriorityField("/h/"), "airCue");
  assert.strictEqual(lab.getCuePriorityField("/f/"), "mouthCue");
  assert.strictEqual(lab.getCuePriorityField("/v/"), "mouthCue");
  assert.strictEqual(lab.getCuePriorityField("/uː/"), "durationCue");
  assert.strictEqual(lab.getCuePriorityField("/ʊ/"), "durationCue");
  assert.strictEqual(lab.getCuePriorityField("/aɪ/"), "movementCue");
  assert.strictEqual(lab.getCuePriorityField("/eɪ/"), "movementCue");
  assert.strictEqual(lab.getCuePriorityField("/oʊ/"), "movementCue");
  assert.strictEqual(lab.getCuePriorityField("/aʊ/"), "movementCue");
  assert.strictEqual(lab.getCuePriorityField("/ɔɪ/"), "movementCue");
  assert.strictEqual(lab.getCuePriorityField("/r/"), "tongueCue");
  assert.strictEqual(lab.getCuePriorityField("/l/"), "tongueCue");
  assert.strictEqual(lab.getCuePriorityField("/θ/"), "tongueCue");
  assert.strictEqual(lab.getCuePriorityField("/ð/"), "tongueCue");
}

{
  const ipaValues = lab.LESSONS.flatMap((lesson) => [
    lesson.focusSound,
    lesson.targetWordIPA,
    lesson.targetSentenceIPA,
    lesson.focusTokenIPA,
    lesson.contrastWordIPA || "",
    ...(lesson.commonMishearings || []).map((item) => item.heardIPA)
  ]);
  const joined = ipaValues.join(" ");
  assert.ok(joined.includes("/aɪ/"));
  assert.ok(joined.includes("/eɪ/"));
  assert.ok(joined.includes("/oʊ/"));
  assert.ok(joined.includes("ɝː"));
  assert.ok(joined.includes("/uː/"));
  assert.ok(joined.includes("/ʊ/"));
  assert.ok(joined.includes("/θ/"));
  assert.ok(joined.includes("/ð/"));
  const forbiddenAsciiLikeIpa = [
    ["a", "i"],
    ["e", "i"],
    ["o", "u"],
    ["r", ":"],
    ["u", ":"],
    ["t", "h"]
  ].map((parts) => `/${parts.join("")}/`);
  for (const forbidden of forbiddenAsciiLikeIpa) {
    assert.ok(!joined.includes(forbidden), `${forbidden} should not appear in IPA data`);
  }
}

console.log("pronunciation-lab MVP tests passed");
