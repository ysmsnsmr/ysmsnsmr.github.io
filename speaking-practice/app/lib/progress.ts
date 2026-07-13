import type {
  FocusSound,
  InterviewPracticeReview,
  InterviewPracticeSession,
  PracticeSession,
  ProgressRecord
} from "@/types/speaking";

const STORAGE_KEY = "speaking-practice-progress";
const CURRENT_SCHEMA_VERSION = 2 as const;
const focusSounds = new Set<FocusSound>([
  "/h/",
  "/f/",
  "/v/",
  "/uː/",
  "/ʊ/",
  "/l/",
  "/r/",
  "/θ/",
  "/ð/"
]);

type InterviewPracticeSessionInput = Omit<
  InterviewPracticeSession,
  | "practiceSource"
  | "reflectionKind"
  | "whatWentWell"
  | "stuckOn"
  | "nextPracticeFocus"
>;

export const defaultProgress: ProgressRecord = {
  schemaVersion: CURRENT_SCHEMA_VERSION,
  completedCardIds: [],
  practiceDate: null,
  sentenceCount: 0,
  streakDots: [false, false, false, false, false, false, false],
  privacyNoticeAccepted: false,
  practiceSessions: []
};

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

export function loadProgress(): ProgressRecord {
  if (!canUseStorage()) {
    return defaultProgress;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return defaultProgress;
    }

    const progress = migrateProgress(JSON.parse(stored));

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
    } catch {
      // Reading valid progress should still succeed when storage is full.
    }

    return progress;
  } catch {
    return defaultProgress;
  }
}

export function saveProgress(progress: ProgressRecord) {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(migrateProgress(progress))
  );
}

export function migrateProgress(input: unknown): ProgressRecord {
  if (!isRecord(input)) {
    return createDefaultProgress();
  }

  const rawSessions = Array.isArray(input.practiceSessions)
    ? input.practiceSessions
    : Array.isArray(input.interviewSessions)
      ? input.interviewSessions
      : [];

  return {
    schemaVersion: CURRENT_SCHEMA_VERSION,
    completedCardIds: normalizeStringArray(input.completedCardIds),
    practiceDate:
      typeof input.practiceDate === "string" ? input.practiceDate : null,
    sentenceCount: normalizeCount(input.sentenceCount),
    streakDots: normalizeStreakDots(input.streakDots),
    privacyNoticeAccepted:
      typeof input.privacyNoticeAccepted === "boolean"
        ? input.privacyNoticeAccepted
        : false,
    practiceSessions: rawSessions
      .map(normalizePracticeSession)
      .filter((session): session is PracticeSession => session !== null)
  };
}

export function acceptPrivacyNotice(): ProgressRecord {
  const next = {
    ...loadProgress(),
    privacyNoticeAccepted: true
  };
  saveProgress(next);
  return next;
}

export function completeCard(cardId: string): ProgressRecord {
  const current = loadProgress();
  const today = new Date().toISOString().slice(0, 10);
  const completedCardIds = current.completedCardIds.includes(cardId)
    ? current.completedCardIds
    : [...current.completedCardIds, cardId];

  const next: ProgressRecord = {
    ...current,
    completedCardIds,
    practiceDate: today,
    sentenceCount: current.sentenceCount + 1,
    streakDots: [...current.streakDots.slice(1), true]
  };

  saveProgress(next);
  return next;
}

export function completeInterviewSession(
  session: InterviewPracticeSessionInput
): ProgressRecord {
  const current = loadProgress();
  const today = new Date().toISOString().slice(0, 10);
  const normalizedSession: InterviewPracticeSession = {
    ...session,
    practiceSource:
      session.completedMode === "recording"
        ? "in_app_recording"
        : "quiet_mode",
    reflectionKind:
      session.completedMode === "recording"
        ? "transcript_based"
        : "self_report",
    whatWentWell: null,
    stuckOn: null,
    nextPracticeFocus: null
  };
  const existingSessions = current.practiceSessions.filter(
    (item) => item.id !== session.id
  );

  const next: ProgressRecord = {
    ...current,
    practiceSessions: [normalizedSession, ...existingSessions].slice(0, 30),
    practiceDate: today,
    sentenceCount: current.sentenceCount + 1,
    streakDots: [...current.streakDots.slice(1), true]
  };

  saveProgress(next);
  return next;
}

function normalizePracticeSession(input: unknown): PracticeSession | null {
  if (!isRecord(input)) {
    return null;
  }

  const id = normalizeRequiredString(input.id);
  const date = normalizeRequiredString(input.date);
  const topic = normalizeRequiredString(input.topic);
  if (!id || !date || !topic) {
    return null;
  }

  const reflection = {
    whatWentWell: normalizeOptionalString(input.whatWentWell),
    stuckOn: normalizeOptionalString(input.stuckOn),
    nextPracticeFocus: normalizeOptionalString(input.nextPracticeFocus)
  };

  if (input.practiceSource === "chatgpt_voice") {
    return {
      id,
      date,
      topic,
      practiceSource: "chatgpt_voice",
      reflectionKind: "self_report",
      ...reflection
    };
  }

  const completedMode =
    input.completedMode === "recording" || input.completedMode === "quiet"
      ? input.completedMode
      : null;
  const focusSound = normalizeFocusSound(input.focusSound);
  const review = normalizeReview(input.review, focusSound);
  if (!completedMode || !focusSound || !review) {
    return null;
  }

  const targetRole = normalizeRequiredString(input.targetRole);
  const answer30 = normalizeRequiredString(input.answer30);
  const answer30Ipa = normalizeRequiredString(input.answer30Ipa);
  const pronunciationTip = normalizeRequiredString(input.pronunciationTip);
  if (!targetRole || !answer30 || !answer30Ipa || !pronunciationTip) {
    return null;
  }

  return {
    id,
    date,
    topic,
    practiceSource:
      completedMode === "recording" ? "in_app_recording" : "quiet_mode",
    reflectionKind:
      completedMode === "recording" ? "transcript_based" : "self_report",
    ...reflection,
    targetRole,
    focusSound,
    answer30,
    answer30Ipa,
    questions: normalizeStringArray(input.questions),
    repairPhrases: normalizeStringArray(input.repairPhrases),
    pronunciationTip,
    review,
    completedMode
  };
}

function normalizeReview(
  input: unknown,
  fallbackFocusSound: FocusSound | null
): InterviewPracticeReview | null {
  if (!isRecord(input) || !fallbackFocusSound) {
    return null;
  }

  const positive = normalizeRequiredString(input.positive);
  const structureSuggestion = normalizeRequiredString(
    input.structureSuggestion
  );
  const legacyPronunciationNote = normalizeOptionalString(
    input.pronunciationNote
  );
  const focusSoundNote =
    normalizeRequiredString(input.focusSoundNote) ?? legacyPronunciationNote;
  if (!positive || !structureSuggestion || !focusSoundNote) {
    return null;
  }

  const review: InterviewPracticeReview = {
    positive,
    fixPoints: normalizeStringArray(input.fixPoints),
    structureSuggestion,
    focusSoundNote,
    nextFocus: normalizeFocusSound(input.nextFocus) ?? fallbackFocusSound
  };

  if (legacyPronunciationNote) {
    review.pronunciationNote = legacyPronunciationNote;
  }

  return review;
}

function createDefaultProgress(): ProgressRecord {
  return {
    ...defaultProgress,
    completedCardIds: [],
    streakDots: [...defaultProgress.streakDots],
    practiceSessions: []
  };
}

function normalizeCount(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : 0;
}

function normalizeStreakDots(value: unknown) {
  if (
    Array.isArray(value) &&
    value.length === defaultProgress.streakDots.length &&
    value.every((item) => typeof item === "boolean")
  ) {
    return [...value];
  }

  return [...defaultProgress.streakDots];
}

function normalizeStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function normalizeRequiredString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized || null;
}

function normalizeOptionalString(value: unknown) {
  return normalizeRequiredString(value);
}

function normalizeFocusSound(value: unknown): FocusSound | null {
  return typeof value === "string" && focusSounds.has(value as FocusSound)
    ? (value as FocusSound)
    : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
