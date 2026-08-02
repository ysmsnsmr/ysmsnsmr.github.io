import type {
  FocusSound,
  InterviewPracticeReview,
  InterviewPracticeSession,
  PracticeSession,
  ProgressRecord
} from "@/types/speaking";

export const PROGRESS_STORAGE_KEY = "speaking-practice-progress";
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

export type ProgressStorage = Pick<Storage, "getItem" | "setItem">;

export type ProgressDiagnosticCode =
  | "invalid_root"
  | "invalid_schema_version"
  | "unsupported_future_version"
  | "dropped_invalid_session";

export type ProgressDecodeDiagnostics = {
  sourceVersion: number | null;
  acceptedSessionCount: number;
  droppedSessionCount: number;
  codes: ProgressDiagnosticCode[];
};

export type ProgressDecodeResult = {
  status: "ok" | "invalid" | "unsupported_version";
  progress: ProgressRecord;
  canWrite: boolean;
  diagnostics: ProgressDecodeDiagnostics;
};

export type ProgressLoadResult = {
  status:
    | "ok"
    | "empty"
    | "invalid"
    | "unsupported_version"
    | "unavailable";
  progress: ProgressRecord;
  canWrite: boolean;
  errorCode:
    | "storage_unavailable"
    | "storage_read_failed"
    | "invalid_json"
    | "invalid_progress"
    | "unsupported_future_version"
    | null;
  diagnostics: ProgressDecodeDiagnostics | null;
};

export class ProgressWriteBlockedError extends Error {
  readonly code:
    | "unsafe_stored_progress"
    | "invalid_outgoing_progress"
    | "storage_unavailable";

  constructor(
    code:
      | "unsafe_stored_progress"
      | "invalid_outgoing_progress"
      | "storage_unavailable"
  ) {
    super(`Progress write blocked: ${code}`);
    this.name = "ProgressWriteBlockedError";
    this.code = code;
  }
}

export const defaultProgress: ProgressRecord = {
  schemaVersion: CURRENT_SCHEMA_VERSION,
  completedCardIds: [],
  practiceDate: null,
  sentenceCount: 0,
  streakDots: [false, false, false, false, false, false, false],
  privacyNoticeAccepted: false,
  practiceSessions: []
};

export function loadProgress(): ProgressRecord {
  return loadProgressWithDiagnostics().progress;
}

export function loadProgressWithDiagnostics(
  storage: ProgressStorage | null = getBrowserStorage()
): ProgressLoadResult {
  if (!storage) {
    return createLoadResult(
      "unavailable",
      false,
      "storage_unavailable"
    );
  }

  let stored: string | null;
  try {
    stored = storage.getItem(PROGRESS_STORAGE_KEY);
  } catch {
    return createLoadResult(
      "unavailable",
      false,
      "storage_read_failed"
    );
  }

  if (!stored) {
    return createLoadResult("empty", true, null);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stored);
  } catch {
    return createLoadResult("invalid", false, "invalid_json");
  }

  const decoded = decodeProgress(parsed);
  return {
    status: decoded.status,
    progress: decoded.progress,
    canWrite: decoded.canWrite,
    errorCode:
      decoded.status === "unsupported_version"
        ? "unsupported_future_version"
        : decoded.canWrite
          ? null
          : "invalid_progress",
    diagnostics: decoded.diagnostics
  };
}

export function saveProgress(
  progress: ProgressRecord,
  storage: ProgressStorage | null = getBrowserStorage()
): ProgressRecord {
  if (!storage) {
    throw new ProgressWriteBlockedError("storage_unavailable");
  }

  const current = loadProgressWithDiagnostics(storage);
  if (!current.canWrite) {
    throw new ProgressWriteBlockedError("unsafe_stored_progress");
  }

  const decoded = decodeProgress(progress);
  if (decoded.status !== "ok" || !decoded.canWrite) {
    throw new ProgressWriteBlockedError("invalid_outgoing_progress");
  }

  storage.setItem(PROGRESS_STORAGE_KEY, JSON.stringify(decoded.progress));
  return decoded.progress;
}

export function decodeProgress(input: unknown): ProgressDecodeResult {
  if (!isRecord(input)) {
    return createDecodeResult("invalid", false, ["invalid_root"]);
  }

  const sourceVersion = normalizeSchemaVersion(input.schemaVersion);
  if (sourceVersion === "invalid") {
    return createDecodeResult("invalid", false, ["invalid_schema_version"]);
  }
  if (sourceVersion !== null && sourceVersion > CURRENT_SCHEMA_VERSION) {
    return createDecodeResult(
      "unsupported_version",
      false,
      ["unsupported_future_version"],
      sourceVersion
    );
  }

  const rawSessions = Array.isArray(input.practiceSessions)
    ? input.practiceSessions
    : Array.isArray(input.interviewSessions)
      ? input.interviewSessions
      : [];
  const practiceSessions = rawSessions
    .map(normalizePracticeSession)
    .filter((session): session is PracticeSession => session !== null);
  const droppedSessionCount = rawSessions.length - practiceSessions.length;
  const codes: ProgressDiagnosticCode[] =
    droppedSessionCount > 0 ? ["dropped_invalid_session"] : [];

  return {
    status: "ok",
    progress: {
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
      practiceSessions
    },
    canWrite: droppedSessionCount === 0,
    diagnostics: {
      sourceVersion,
      acceptedSessionCount: practiceSessions.length,
      droppedSessionCount,
      codes
    }
  };
}

export function migrateProgress(input: unknown): ProgressRecord {
  return decodeProgress(input).progress;
}

export function acceptPrivacyNotice(): ProgressRecord {
  const next = {
    ...loadProgress(),
    privacyNoticeAccepted: true
  };
  return saveProgress(next);
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

  return saveProgress(next);
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

  return saveProgress(next);
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

function createDecodeResult(
  status: ProgressDecodeResult["status"],
  canWrite: boolean,
  codes: ProgressDiagnosticCode[],
  sourceVersion: number | null = null
): ProgressDecodeResult {
  return {
    status,
    progress: createDefaultProgress(),
    canWrite,
    diagnostics: {
      sourceVersion,
      acceptedSessionCount: 0,
      droppedSessionCount: 0,
      codes
    }
  };
}

function createLoadResult(
  status: ProgressLoadResult["status"],
  canWrite: boolean,
  errorCode: ProgressLoadResult["errorCode"]
): ProgressLoadResult {
  return {
    status,
    progress: createDefaultProgress(),
    canWrite,
    errorCode,
    diagnostics: null
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

function normalizeSchemaVersion(value: unknown): number | null | "invalid" {
  if (value === undefined) {
    return null;
  }

  return typeof value === "number" && Number.isInteger(value) && value >= 1
    ? value
    : "invalid";
}

function getBrowserStorage(): ProgressStorage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
