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
import {
  decodeProgress,
  type ProgressDecodeDiagnostics
} from "./progress";
import {
  decodeVoicePracticeLedger,
  type VoiceLedgerDecodeDiagnostics
} from "./voice-ledger";

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

export type LegacyPracticeLedgerV2ConversionDiagnostics = {
  voiceLedger: {
    status: ReturnType<typeof decodeVoicePracticeLedger>["status"];
    canWrite: boolean;
    details: VoiceLedgerDecodeDiagnostics;
  };
  progress: {
    status: ReturnType<typeof decodeProgress>["status"];
    canWrite: boolean;
    details: ProgressDecodeDiagnostics;
  };
};

export type LegacyPracticeLedgerV2ConversionResult = {
  status: "ok" | "blocked";
  ledger: PracticeLedgerV2 | null;
  diagnostics: LegacyPracticeLedgerV2ConversionDiagnostics;
};

/**
 * Adapts the two legacy stores without writing to either source. A rejected or
 * partially corrupt source blocks the v2 output, so callers cannot replace a
 * source ledger with a silently incomplete migration.
 */
export function convertLegacyPracticeDataToLedgerV2(input: {
  voiceLedger: unknown;
  progress: unknown;
}): LegacyPracticeLedgerV2ConversionResult {
  const voiceLedger = decodeVoicePracticeLedger(input.voiceLedger);
  const progress = decodeProgress(input.progress);
  const diagnostics = {
    voiceLedger: {
      status: voiceLedger.status,
      canWrite: voiceLedger.canWrite,
      details: voiceLedger.diagnostics
    },
    progress: {
      status: progress.status,
      canWrite: progress.canWrite,
      details: progress.diagnostics
    }
  };

  if (!voiceLedger.canWrite || !progress.canWrite) {
    return {
      status: "blocked",
      ledger: null,
      diagnostics
    };
  }

  return {
    status: "ok",
    ledger: convertToPracticeLedgerV2({
      voiceLedger: voiceLedger.ledger,
      progress: progress.progress
    }).ledger,
    diagnostics
  };
}

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
    occurredAt: entry.practicedAt,
    createdAt: entry.createdAt,
    updatedAt: entry.updatedAt,
    practiceKind: "voice",
    source: "external_voice",
    reviewBasis: "self_report",
    context: entry.context,
    title: entry.title,
    summary: entry.summary,
    nextMission: entry.nextMission,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
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
    occurredAt: session.date,
    createdAt: null,
    updatedAt: null,
    practiceKind: "interview",
    source:
      session.practiceSource === "in_app_recording"
        ? "in_app_recording"
        : "quiet_mode",
    reviewBasis: session.reflectionKind,
    context: "work",
    title: session.topic,
    summary: session.review.positive,
    nextMission: session.review.structureSuggestion,
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
      completionMode:
        session.completedMode === "recording" ? "recorded" : "quiet",
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
    occurredAt: session.date,
    createdAt: null,
    updatedAt: null,
    practiceKind: "voice",
    source: "external_voice",
    reviewBasis: "self_report",
    context: null,
    title: session.topic,
    summary:
      session.whatWentWell ?? session.stuckOn ?? session.topic,
    nextMission: session.nextPracticeFocus,
    plannedFocusSound: null,
    observedFocusSoundCandidate: null,
    nextFocusSound: null,
    details: {
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
    Date.parse(right.occurredAt) - Date.parse(left.occurredAt) ||
    left.id.localeCompare(right.id)
  );
}
