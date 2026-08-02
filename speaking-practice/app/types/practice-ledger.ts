import type { FocusSound, InterviewPracticeReview } from "@/types/speaking";
import type {
  VoicePracticeContext,
  VoicePracticeSourceKind
} from "@/types/voice-ledger";

export type PracticeKind = "voice" | "interview" | "sentence";

export type LedgerPracticeSource =
  | "chatgpt_voice"
  | "in_app_recording"
  | "quiet_mode"
  | "sentence_practice";

export type PracticeReviewBasis =
  | "self_report"
  | "transcript_based"
  | "none";

export type PracticeLedgerEntryBase = {
  id: string;
  practicedAt: string;
  createdAt: string | null;
  updatedAt: string | null;
  practiceKind: PracticeKind;
  practiceSource: LedgerPracticeSource;
  reviewBasis: PracticeReviewBasis;
  context: VoicePracticeContext | null;
  title: string;
  summary: string;
  nextAction: string | null;
  plannedFocusSound: FocusSound | null;
  observedFocusSoundCandidate: FocusSound | null;
  nextFocusSound: FocusSound | null;
};

export type VoicePracticeLedgerEntry = PracticeLedgerEntryBase & {
  practiceKind: "voice";
  practiceSource: "chatgpt_voice";
  reviewBasis: "self_report";
  details: {
    sourceKind: VoicePracticeSourceKind;
    sessionMinutes: number | null;
    usefulExpressions: string[];
    stickingPoints: string[];
    corrections: string[];
    selfNote: string | null;
  };
};

export type InterviewPracticeLedgerEntry = PracticeLedgerEntryBase & {
  practiceKind: "interview";
  practiceSource: "in_app_recording" | "quiet_mode";
  reviewBasis: "self_report" | "transcript_based";
  details: {
    targetRole: string;
    answer30: string;
    answer30Ipa: string;
    questions: string[];
    repairPhrases: string[];
    pronunciationTip: string;
    completedMode: "recording" | "quiet";
    review: InterviewPracticeReview;
  };
};

export type SentencePracticeLedgerEntry = PracticeLedgerEntryBase & {
  practiceKind: "sentence";
  practiceSource: "sentence_practice";
  reviewBasis: "none";
  details: {
    lessonId: string;
    sentence: string;
    scenario: string;
    level: string;
  };
};

export type PracticeLedgerEntry =
  | VoicePracticeLedgerEntry
  | InterviewPracticeLedgerEntry
  | SentencePracticeLedgerEntry;

export type PracticeLedgerV2 = {
  schemaVersion: 2;
  entries: PracticeLedgerEntry[];
};
