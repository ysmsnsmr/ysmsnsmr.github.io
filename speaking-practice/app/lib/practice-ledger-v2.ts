import type {
  InterviewPracticeSession,
  PracticeSession,
  ProgressRecord
} from "@/types/speaking";
import type {
  InterviewPracticeLedgerEntry,
  PracticeLedgerEntry,
  PracticeLedgerV2,
  VoicePracticeLedgerEntry
} from "@/types/practice-ledger";
import type {
  VoicePracticeEntry,
  VoicePracticeLedger
} from "@/types/voice-ledger";

export const PRACTICE_LEDGER_SCHEMA_VERSION = 2 as const;

export type PracticeLedgerV2ConversionDiagnostics = {
  convertedVoiceEntryCount: number;
  convertedInterviewSessionCount: number;
  convertedExternalVoiceSessionCount: number;
  unconvertedSentenceHistory: {
    completedCardIds: string[];
  };
};

export type PracticeLedgerV2ConversionResult = {
  ledger: PracticeLedgerV2;
  diagnostics: PracticeLedgerV2ConversionDiagnostics;
};

export function convertToPracticeLedgerV2(input: {
  voiceLedger: VoicePracticeLedger;
  progress: ProgressRecord;
}): PracticeLedgerV2ConversionResult {
  const voiceEntries = input.voiceLedger.entries.map(convertVoicePracticeEntry);
  const progressEntries = input.progress.practiceSessions.map(
    convertPracticeSession
  );

  return {
    ledger: {
      schemaVersion: PRACTICE_LEDGER_SCHEMA_VERSION,
      entries: [...voiceEntries, ...progressEntries].sort(compareEntries)
    },
    diagnostics: {
      convertedVoiceEntryCount: voiceEntries.length,
      convertedInterviewSessionCount: input.progress.practiceSessions.filter(
        (session) => "review" in session
      ).length,
      convertedExternalVoiceSessionCount: input.progress.practiceSessions.filter(
        (session) => session.practiceSource === "chatgpt_voice"
      ).length,
      unconvertedSentenceHistory: {
        completedCardIds: [...input.progress.completedCardIds]
      }
    }
  };
}

export function convertVoicePracticeEntry(
  entry: VoicePracticeEntry
): VoicePracticeLedgerEntry {
  return {
    id: entry.id,
    practicedAt: entry.practicedAt,
    createdAt: entry.createdAt,
    updatedAt: entry.updatedAt,
    practiceKind: "voice",
    practiceSource: "chatgpt_voice",
    reviewBasis: "self_report",
    context: entry.context,
    title: entry.title,
    summary: entry.summary,
    nextAction: entry.nextMission,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
      sourceKind: entry.sourceKind,
      sessionMinutes: entry.sessionMinutes,
      usefulExpressions: [...entry.usefulExpressions],
      stickingPoints: [...entry.stickingPoints],
      corrections: [...entry.corrections],
      selfNote: entry.selfNote
    }
  };
}

export function convertPracticeSession(
  session: PracticeSession
): PracticeLedgerEntry {
  return "review" in session
    ? convertInterviewPracticeSession(session)
    : convertExternalVoicePracticeSession(session);
}

export function convertInterviewPracticeSession(
  session: InterviewPracticeSession
): InterviewPracticeLedgerEntry {
  return {
    id: session.id,
    practicedAt: session.date,
    createdAt: null,
    updatedAt: null,
    practiceKind: "interview",
    practiceSource: session.practiceSource,
    reviewBasis: session.reflectionKind,
    context: "work",
    title: session.topic,
    summary: session.review.positive,
    nextAction: session.review.structureSuggestion,
    plannedFocusSound: session.focusSound,
    observedFocusSoundCandidate: null,
    nextFocusSound: session.review.nextFocus,
    details: {
      targetRole: session.targetRole,
      answer30: session.answer30,
      answer30Ipa: session.answer30Ipa,
      questions: [...session.questions],
      repairPhrases: [...session.repairPhrases],
      pronunciationTip: session.pronunciationTip,
      completedMode: session.completedMode,
      review: {
        ...session.review,
        fixPoints: [...session.review.fixPoints]
      }
    }
  };
}

function convertExternalVoicePracticeSession(
  session: Exclude<PracticeSession, InterviewPracticeSession>
): VoicePracticeLedgerEntry {
  return {
    id: session.id,
    practicedAt: session.date,
    createdAt: null,
    updatedAt: null,
    practiceKind: "voice",
    practiceSource: "chatgpt_voice",
    reviewBasis: "self_report",
    context: null,
    title: session.topic,
    summary:
      session.whatWentWell ?? session.stuckOn ?? session.topic,
    nextAction: session.nextPracticeFocus,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
      sourceKind: "manual",
      sessionMinutes: null,
      usefulExpressions: [],
      stickingPoints: session.stuckOn ? [session.stuckOn] : [],
      corrections: [],
      selfNote: session.whatWentWell
    }
  };
}

function compareEntries(left: PracticeLedgerEntry, right: PracticeLedgerEntry) {
  return (
    Date.parse(right.practicedAt) - Date.parse(left.practicedAt) ||
    left.id.localeCompare(right.id)
  );
}
