import {
  convertLegacyPracticeDataToLedgerV2
} from "@/lib/practice-ledger-v2";
import type {
  InterviewPracticeLedgerEntry,
  PracticeLedgerEntry,
  PracticeLedgerV2,
  SentencePracticeLedgerEntry,
  VoicePracticeLedgerEntry
} from "@/types/practice-ledger";
import type { FocusSound } from "@/types/speaking";
import type { VoicePracticeContext } from "@/types/voice-ledger";

type ImportEntryBase = {
  id: string;
  occurredAt: string;
  createdAt: string | null;
  updatedAt: string | null;
  practiceKind: unknown;
  source: string;
  reviewBasis: string;
  context: VoicePracticeContext | null;
  title: string;
  summary: string;
  nextMission: string | null;
  plannedFocusSound: FocusSound | null;
  observedFocusSoundCandidate: FocusSound | null;
  nextFocusSound: FocusSound | null;
};

export const PRACTICE_LEDGER_V2_STORAGE_KEY =
  "speaking-practice-ledger-v2";
export const PRACTICE_LEDGER_PENDING_SENTENCE_HISTORY_KEY =
  "speaking-practice-ledger-v2-pending-sentence-history";

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
const practiceSources = new Set([
  "external_voice",
  "in_app_recording",
  "quiet_mode",
  "sentence_practice"
]);
const reviewBases = new Set(["self_report", "transcript_based", "none"]);

export type PracticeLedgerImportSource =
  | "ledger_export"
  | "migration_backup";

export type PracticeLedgerImportPreview = {
  status: "valid" | "invalid";
  source: PracticeLedgerImportSource | null;
  ledger: PracticeLedgerV2 | null;
  pendingSentenceHistory: string[];
  entryCount: number;
  newEntryCount: number;
  duplicateEntryCount: number;
  errors: string[];
  warnings: string[];
};

export type PracticeLedgerV2Storage = Pick<Storage, "getItem" | "setItem">;

export type StoredPracticeLedgerV2Result = {
  status: "ok" | "empty" | "invalid" | "unsupported_version" | "unavailable";
  ledger: PracticeLedgerV2;
  canWrite: boolean;
};

export type PracticeLedgerImportResult = {
  ledger: PracticeLedgerV2;
  addedEntryCount: number;
  duplicateEntryCount: number;
  pendingSentenceHistory: string[];
};

export class PracticeLedgerImportWriteBlockedError extends Error {
  readonly code:
    | "storage_unavailable"
    | "unsafe_stored_ledger"
    | "storage_write_failed";

  constructor(
    code:
      | "storage_unavailable"
      | "unsafe_stored_ledger"
      | "storage_write_failed"
  ) {
    super(`Practice Ledger import blocked: ${code}`);
    this.name = "PracticeLedgerImportWriteBlockedError";
    this.code = code;
  }
}

export function previewPracticeLedgerImportJson(
  json: string,
  existingLedger: PracticeLedgerV2 | null = null
): PracticeLedgerImportPreview {
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    return invalidPreview("JSONを読み取れませんでした。");
  }

  const parsed = parsePracticeLedgerImport(value);
  if (parsed.status === "invalid") {
    return parsed;
  }

  const ledger = parsed.ledger;
  if (!ledger) {
    return invalidPreview("Ledger v2の内容がありません。");
  }
  const existingIds = new Set(existingLedger?.entries.map((entry) => entry.id));
  const duplicateEntryCount = ledger.entries.filter((entry) =>
    existingIds.has(entry.id)
  ).length;

  return {
    ...parsed,
    newEntryCount: ledger.entries.length - duplicateEntryCount,
    duplicateEntryCount,
    warnings:
      duplicateEntryCount > 0
        ? [
            `${duplicateEntryCount}件は同じIDがあるため、既存の記録を優先して追加しません。`
          ]
        : parsed.warnings
  };
}

export function parsePracticeLedgerImport(
  value: unknown
): PracticeLedgerImportPreview {
  if (!isRecord(value)) {
    return invalidPreview("JSONの形式が正しくありません。");
  }

  if (
    value.format === "speaking-practice-ledger-export" &&
    value.exportVersion === 1
  ) {
    const ledger = normalizePracticeLedger(value.ledger);
    const pendingSentenceHistory = normalizeStringArray(
      value.pendingSentenceHistory
    );
    if (!ledger || !pendingSentenceHistory) {
      return invalidPreview(
        "Ledger v2の必須項目、または未移行Sentence履歴の形式を確認してください。"
      );
    }

    return validPreview("ledger_export", ledger, pendingSentenceHistory);
  }

  if (
    value.format === "speaking-practice-migration-backup" &&
    value.backupVersion === 1
  ) {
    if (!isRecord(value.source)) {
      return invalidPreview("移行前バックアップのsourceがありません。");
    }

    const conversion = convertLegacyPracticeDataToLedgerV2({
      voiceLedger: value.source.voiceLedger,
      progress: value.source.progress
    });
    const pendingSentenceHistory = normalizeStringArray(
      value.source.progress &&
        isRecord(value.source.progress) &&
        value.source.progress.completedCardIds
    );
    if (conversion.status !== "ok" || !conversion.ledger || !pendingSentenceHistory) {
      return invalidPreview(
        "移行前バックアップを安全に検証できないため、読み込みを停止しました。"
      );
    }

    return validPreview(
      "migration_backup",
      conversion.ledger,
      pendingSentenceHistory
    );
  }

  return invalidPreview(
    "対応していないJSONです。Speaking Practiceから書き出したJSONを選んでください。"
  );
}

export function loadStoredPracticeLedgerV2(
  storage: PracticeLedgerV2Storage | null = getBrowserStorage()
): StoredPracticeLedgerV2Result {
  if (!storage) {
    return {
      status: "unavailable",
      ledger: emptyLedger(),
      canWrite: false
    };
  }

  let stored: string | null;
  try {
    stored = storage.getItem(PRACTICE_LEDGER_V2_STORAGE_KEY);
  } catch {
    return {
      status: "unavailable",
      ledger: emptyLedger(),
      canWrite: false
    };
  }

  if (!stored) {
    return { status: "empty", ledger: emptyLedger(), canWrite: true };
  }

  let value: unknown;
  try {
    value = JSON.parse(stored);
  } catch {
    return { status: "invalid", ledger: emptyLedger(), canWrite: false };
  }

  const ledger = normalizePracticeLedger(value);
  if (!ledger) {
    return {
      status:
        isRecord(value) &&
        typeof value.schemaVersion === "number" &&
        value.schemaVersion > 2
          ? "unsupported_version"
          : "invalid",
      ledger: emptyLedger(),
      canWrite: false
    };
  }

  return { status: "ok", ledger, canWrite: true };
}

export function mergePracticeLedgers(
  existing: PracticeLedgerV2,
  incoming: PracticeLedgerV2,
  pendingHistory: string[] = []
): PracticeLedgerImportResult {
  const existingIds = new Set(existing.entries.map((entry) => entry.id));
  const newEntries = incoming.entries.filter((entry) => !existingIds.has(entry.id));
  const pendingSentenceHistory = [...new Set([
    ...existing.entries
      .filter((entry) => entry.practiceKind === "sentence")
      .map((entry) => entry.details.lessonId),
    ...incoming.entries
      .filter((entry) => entry.practiceKind === "sentence")
      .map((entry) => entry.details.lessonId),
    ...pendingHistory
  ])];

  return {
    ledger: {
      schemaVersion: 2,
      entries: [...existing.entries, ...newEntries].sort(compareEntries)
    },
    addedEntryCount: newEntries.length,
    duplicateEntryCount: incoming.entries.length - newEntries.length,
    pendingSentenceHistory
  };
}

export function importPracticeLedgerV2NonDestructively(
  incoming: PracticeLedgerV2,
  storage: PracticeLedgerV2Storage | null = getBrowserStorage(),
  incomingPendingSentenceHistory: string[] = []
): PracticeLedgerImportResult {
  if (!storage) {
    throw new PracticeLedgerImportWriteBlockedError("storage_unavailable");
  }

  const current = loadStoredPracticeLedgerV2(storage);
  if (!current.canWrite) {
    throw new PracticeLedgerImportWriteBlockedError("unsafe_stored_ledger");
  }

  const existingPending = loadPendingSentenceHistory(storage);
  if (existingPending === null) {
    throw new PracticeLedgerImportWriteBlockedError("unsafe_stored_ledger");
  }
  const result = mergePracticeLedgers(current.ledger, incoming, [
    ...existingPending,
    ...incomingPendingSentenceHistory
  ]);
  try {
    storage.setItem(
      PRACTICE_LEDGER_V2_STORAGE_KEY,
      JSON.stringify(result.ledger)
    );
    storage.setItem(
      PRACTICE_LEDGER_PENDING_SENTENCE_HISTORY_KEY,
      JSON.stringify(result.pendingSentenceHistory)
    );
  } catch {
    throw new PracticeLedgerImportWriteBlockedError("storage_write_failed");
  }

  return result;
}

function loadPendingSentenceHistory(
  storage: PracticeLedgerV2Storage
): string[] | null {
  let stored: string | null;
  try {
    stored = storage.getItem(PRACTICE_LEDGER_PENDING_SENTENCE_HISTORY_KEY);
  } catch {
    return null;
  }
  if (!stored) {
    return [];
  }
  try {
    return normalizeStringArray(JSON.parse(stored));
  } catch {
    return null;
  }
}

function validPreview(
  source: PracticeLedgerImportSource,
  ledger: PracticeLedgerV2,
  pendingSentenceHistory: string[]
): PracticeLedgerImportPreview {
  return {
    status: "valid",
    source,
    ledger,
    pendingSentenceHistory,
    entryCount: ledger.entries.length,
    newEntryCount: ledger.entries.length,
    duplicateEntryCount: 0,
    errors: [],
    warnings: []
  };
}

function invalidPreview(error: string): PracticeLedgerImportPreview {
  return {
    status: "invalid",
    source: null,
    ledger: null,
    pendingSentenceHistory: [],
    entryCount: 0,
    newEntryCount: 0,
    duplicateEntryCount: 0,
    errors: [error],
    warnings: []
  };
}

function normalizePracticeLedger(value: unknown): PracticeLedgerV2 | null {
  if (!isRecord(value) || value.schemaVersion !== 2 || !Array.isArray(value.entries)) {
    return null;
  }

  const entries = value.entries.map(normalizeEntry);
  if (entries.some((entry) => entry === null)) {
    return null;
  }

  const normalizedEntries = entries as PracticeLedgerEntry[];
  const ids = new Set<string>();
  if (normalizedEntries.some((entry) => ids.has(entry.id) || !ids.add(entry.id))) {
    return null;
  }

  return {
    schemaVersion: 2,
    entries: normalizedEntries.sort(compareEntries)
  };
}

function normalizeEntry(value: unknown): PracticeLedgerEntry | null {
  if (!isRecord(value)) {
    return null;
  }

  const id = requiredString(value.id);
  const occurredAt = requiredString(value.occurredAt);
  const createdAt = nullableString(value.createdAt);
  const updatedAt = nullableString(value.updatedAt);
  const source = value.source;
  const reviewBasis = value.reviewBasis;
  const context = nullableContext(value.context);
  const title = requiredString(value.title);
  const summary = requiredString(value.summary);
  const nextMission = nullableString(value.nextMission);
  const plannedFocusSound = nullableFocusSound(value.plannedFocusSound);
  const observedFocusSoundCandidate = nullableFocusSound(
    value.observedFocusSoundCandidate
  );
  const nextFocusSound = nullableFocusSound(value.nextFocusSound);

  if (
    !id ||
    !occurredAt ||
    createdAt === undefined ||
    updatedAt === undefined ||
    typeof source !== "string" ||
    !practiceSources.has(source) ||
    typeof reviewBasis !== "string" ||
    !reviewBases.has(reviewBasis) ||
    context === undefined ||
    !title ||
    !summary ||
    nextMission === undefined ||
    plannedFocusSound === undefined ||
    observedFocusSoundCandidate === undefined ||
    nextFocusSound === undefined
  ) {
    return null;
  }

  const base: ImportEntryBase = {
    id,
    occurredAt,
    createdAt,
    updatedAt,
    practiceKind: value.practiceKind,
    source,
    reviewBasis,
    context,
    title,
    summary,
    nextMission,
    plannedFocusSound,
    observedFocusSoundCandidate,
    nextFocusSound
  };

  if (base.practiceKind === "voice") {
    return normalizeVoiceEntry(value, base);
  }
  if (base.practiceKind === "interview") {
    return normalizeInterviewEntry(value, base);
  }
  if (base.practiceKind === "sentence") {
    return normalizeSentenceEntry(value, base);
  }
  return null;
}

function normalizeVoiceEntry(
  value: Record<string, unknown>,
  base: ImportEntryBase
): VoicePracticeLedgerEntry | null {
  if (
    base.source !== "external_voice" ||
    base.reviewBasis !== "self_report" ||
    !isRecord(value.details) ||
    !positiveIntegerOrNull(value.details.sessionMinutes) ||
    !stringArray(value.details.usefulExpressions) ||
    !stringArray(value.details.stickingPoints) ||
    !stringArray(value.details.corrections) ||
    nullableString(value.details.selfNote) === undefined
  ) {
    return null;
  }

  return {
    ...base,
    practiceKind: "voice",
    source: "external_voice",
    reviewBasis: "self_report",
    details: {
      sessionMinutes: value.details.sessionMinutes as number | null,
      usefulExpressions: value.details.usefulExpressions as string[],
      stickingPoints: value.details.stickingPoints as string[],
      corrections: value.details.corrections as string[],
      selfNote: value.details.selfNote as string | null
    }
  };
}

function normalizeInterviewEntry(
  value: Record<string, unknown>,
  base: ImportEntryBase
): InterviewPracticeLedgerEntry | null {
  if (
    (base.source !== "in_app_recording" && base.source !== "quiet_mode") ||
    (base.reviewBasis !== "self_report" && base.reviewBasis !== "transcript_based") ||
    !isRecord(value.details) ||
    !requiredString(value.details.targetRole) ||
    !requiredString(value.details.answer30) ||
    !requiredString(value.details.answer30Ipa) ||
    !stringArray(value.details.questions) ||
    !stringArray(value.details.repairPhrases) ||
    !requiredString(value.details.pronunciationTip) ||
    (value.details.completionMode !== "recorded" &&
      value.details.completionMode !== "quiet") ||
    !normalizeReview(value.details.review)
  ) {
    return null;
  }

  const review = normalizeReview(value.details.review);
  if (!review) {
    return null;
  }

  return {
    ...base,
    practiceKind: "interview",
    source: base.source as "in_app_recording" | "quiet_mode",
    reviewBasis: base.reviewBasis as "self_report" | "transcript_based",
    details: {
      targetRole: value.details.targetRole as string,
      answer30: value.details.answer30 as string,
      answer30Ipa: value.details.answer30Ipa as string,
      questions: value.details.questions as string[],
      repairPhrases: value.details.repairPhrases as string[],
      pronunciationTip: value.details.pronunciationTip as string,
      completionMode: value.details.completionMode as "recorded" | "quiet",
      review
    }
  };
}

function normalizeSentenceEntry(
  value: Record<string, unknown>,
  base: ImportEntryBase
): SentencePracticeLedgerEntry | null {
  if (
    base.source !== "sentence_practice" ||
    base.reviewBasis !== "none" ||
    !isRecord(value.details) ||
    !requiredString(value.details.lessonId) ||
    !requiredString(value.details.sentence) ||
    !requiredString(value.details.scenario) ||
    !requiredString(value.details.level)
  ) {
    return null;
  }

  return {
    ...base,
    practiceKind: "sentence",
    source: "sentence_practice",
    reviewBasis: "none",
    details: {
      lessonId: value.details.lessonId as string,
      sentence: value.details.sentence as string,
      scenario: value.details.scenario as string,
      level: value.details.level as string
    }
  };
}

function normalizeReview(value: unknown): InterviewPracticeLedgerEntry["details"]["review"] | null {
  if (!isRecord(value)) {
    return null;
  }
  const focusSound = nullableFocusSound(value.nextFocus);
  const hasPronunciationNote = Object.prototype.hasOwnProperty.call(
    value,
    "pronunciationNote"
  );
  const pronunciationNote = hasPronunciationNote
    ? requiredString(value.pronunciationNote)
    : null;
  if (
    !requiredString(value.positive) ||
    !stringArray(value.fixPoints) ||
    !requiredString(value.structureSuggestion) ||
    !requiredString(value.focusSoundNote) ||
    !focusSound ||
    (hasPronunciationNote && !pronunciationNote)
  ) {
    return null;
  }

  return {
    positive: value.positive as string,
    fixPoints: value.fixPoints as string[],
    structureSuggestion: value.structureSuggestion as string,
    focusSoundNote: value.focusSoundNote as string,
    nextFocus: focusSound,
    ...(pronunciationNote ? { pronunciationNote } : {})
  };
}

function requiredString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function nullableString(value: unknown): string | null | undefined {
  return value === null || typeof value === "string" ? value : undefined;
}

function nullableContext(value: unknown): VoicePracticeContext | null | undefined {
  return value === null || value === "work" || value === "travel" || value === "daily" || value === "other"
    ? value
    : undefined;
}

function nullableFocusSound(value: unknown): FocusSound | null | undefined {
  return value === null || focusSounds.has(value as FocusSound)
    ? value as FocusSound | null
    : undefined;
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function normalizeStringArray(value: unknown): string[] | null {
  return stringArray(value) ? [...value] : null;
}

function positiveIntegerOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value) && value > 0);
}

function emptyLedger(): PracticeLedgerV2 {
  return { schemaVersion: 2, entries: [] };
}

function compareEntries(left: PracticeLedgerEntry, right: PracticeLedgerEntry) {
  return Date.parse(right.occurredAt) - Date.parse(left.occurredAt) || left.id.localeCompare(right.id);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getBrowserStorage(): PracticeLedgerV2Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
