export type VoicePracticeContext = "work" | "travel" | "daily" | "other";

export type VoicePracticeSourceKind =
  | "voice_transcript"
  | "chatgpt_summary"
  | "manual";

export type VoicePracticeEntry = {
  id: string;
  practicedAt: string;
  createdAt: string;
  updatedAt: string;
  title: string;
  context: VoicePracticeContext;
  sessionMinutes: number | null;
  summary: string;
  usefulExpressions: string[];
  stickingPoints: string[];
  corrections: string[];
  nextMission: string;
  selfNote: string | null;
  sourceKind: VoicePracticeSourceKind;
};

export type VoicePracticeLedger = {
  schemaVersion: 1;
  entries: VoicePracticeEntry[];
};
