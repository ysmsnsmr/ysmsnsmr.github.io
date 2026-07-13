export type LessonMode = "repeat";

export type FocusSound =
  | "/h/"
  | "/f/"
  | "/v/"
  | "/uː/"
  | "/ʊ/"
  | "/l/"
  | "/r/"
  | "/θ/"
  | "/ð/";

export type LessonCard = {
  id: string;
  scenario: string;
  mode: LessonMode;
  sentence: string;
  japaneseHint?: string;
  level: string;
};

export type SpeakingState =
  | "idle"
  | "arming"
  | "recording"
  | "processing"
  | "transcript"
  | "correction"
  | "repeat"
  | "success"
  | "unclear";

export type MicState = "idle" | "arming" | "recording" | "processing";

export type TranscriptSource = "mock" | "groq_whisper" | "manual" | "none";

export type ReviewMode = "sentence_mock" | "transcript_based";

export type SttStatus =
  | "success"
  | "not_configured"
  | "missing_audio"
  | "empty_audio"
  | "too_short"
  | "too_large"
  | "unsupported_format"
  | "failed";

export type SttErrorCode = Exclude<SttStatus, "success">;

export type FeedbackResult = {
  transcript: string;
  correction: string;
  positive: string;
  nextAction: string;
  clarity: "clear" | "unclear";
  transcriptSource?: TranscriptSource;
  reviewMode?: ReviewMode;
  sttStatus?: SttStatus;
  sttErrorCode?: SttErrorCode;
  review?: InterviewPracticeReview;
};

export type InterviewMaterials = {
  id: string;
  createdAt: string;
  topic: string;
  focusSound: FocusSound;
  summaryBullets: string[];
  answer30: string;
  answer30Ipa: string;
  questions: string[];
  repairPhrases: string[];
  pronunciationTip: string;
  privacyWarnings: string[];
};

export type InterviewPracticeReview = {
  positive: string;
  fixPoints: string[];
  structureSuggestion: string;
  focusSoundNote: string;
  pronunciationNote?: string;
  nextFocus: FocusSound;
};

export type PracticeSource =
  | "in_app_recording"
  | "quiet_mode"
  | "chatgpt_voice";

export type ReflectionKind = "self_report" | "transcript_based";

export type PracticeSessionBase = {
  id: string;
  date: string;
  topic: string;
  whatWentWell: string | null;
  stuckOn: string | null;
  nextPracticeFocus: string | null;
};

export type InterviewPracticeSession = PracticeSessionBase & {
  practiceSource: "in_app_recording" | "quiet_mode";
  reflectionKind: ReflectionKind;
  targetRole: string;
  focusSound: FocusSound;
  answer30: string;
  answer30Ipa: string;
  questions: string[];
  repairPhrases: string[];
  pronunciationTip: string;
  review: InterviewPracticeReview;
  completedMode: "recording" | "quiet";
};

export type ExternalVoicePracticeSession = PracticeSessionBase & {
  practiceSource: "chatgpt_voice";
  reflectionKind: "self_report";
};

export type PracticeSession =
  | InterviewPracticeSession
  | ExternalVoicePracticeSession;

export type ProgressRecord = {
  schemaVersion: 2;
  completedCardIds: string[];
  practiceDate: string | null;
  sentenceCount: number;
  streakDots: boolean[];
  privacyNoticeAccepted: boolean;
  practiceSessions: PracticeSession[];
};
