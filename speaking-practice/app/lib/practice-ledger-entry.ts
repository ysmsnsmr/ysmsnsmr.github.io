import type { SentencePracticeLedgerEntry } from "@/types/practice-ledger";
import type { LessonCard } from "@/types/speaking";

export function createSentencePracticeLedgerEntry(
  lesson: LessonCard,
  occurredAt = new Date().toISOString(),
  id = `sentence-${lesson.id}-${occurredAt}`
): SentencePracticeLedgerEntry {
  return {
    id,
    occurredAt,
    createdAt: occurredAt,
    updatedAt: occurredAt,
    practiceKind: "sentence",
    source: "sentence_practice",
    reviewBasis: "none",
    context: null,
    title: lesson.scenario,
    summary: lesson.sentence,
    nextMission: null,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
      lessonId: lesson.id,
      sentence: lesson.sentence,
      scenario: lesson.scenario,
      level: lesson.level
    }
  };
}
