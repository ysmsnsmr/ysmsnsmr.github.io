import type {
  VoicePracticeContext,
  VoicePracticeEntry,
  VoicePracticeLedger,
  VoicePracticeSourceKind
} from "@/types/voice-ledger";

export const VOICE_LEDGER_SCHEMA_VERSION = 1 as const;
export const VOICE_LEDGER_LIMITS = {
  maxListItems: 5
} as const;

const contexts = new Set<VoicePracticeContext>([
  "work",
  "travel",
  "daily",
  "other"
]);
const sourceKinds = new Set<VoicePracticeSourceKind>([
  "voice_transcript",
  "chatgpt_summary",
  "manual"
]);

export type VoiceLedgerDiagnosticCode =
  | "invalid_root"
  | "missing_schema_version"
  | "invalid_schema_version"
  | "unsupported_future_version"
  | "invalid_entries"
  | "dropped_invalid_entry";

export type VoiceLedgerDecodeDiagnostics = {
  sourceVersion: number | null;
  acceptedEntryCount: number;
  droppedEntryCount: number;
  codes: VoiceLedgerDiagnosticCode[];
};

export type VoiceLedgerDecodeResult = {
  status: "ok" | "invalid" | "unsupported_version";
  ledger: VoicePracticeLedger;
  canWrite: boolean;
  diagnostics: VoiceLedgerDecodeDiagnostics;
};

export function decodeVoicePracticeLedger(
  input: unknown
): VoiceLedgerDecodeResult {
  if (!isRecord(input)) {
    return createDecodeResult("invalid", false, ["invalid_root"]);
  }

  if (!Object.prototype.hasOwnProperty.call(input, "schemaVersion")) {
    return createDecodeResult("invalid", false, ["missing_schema_version"]);
  }

  const sourceVersion = normalizeSchemaVersion(input.schemaVersion);
  if (sourceVersion === null) {
    return createDecodeResult("invalid", false, ["invalid_schema_version"]);
  }
  if (sourceVersion > VOICE_LEDGER_SCHEMA_VERSION) {
    return createDecodeResult(
      "unsupported_version",
      false,
      ["unsupported_future_version"],
      sourceVersion
    );
  }
  if (!Array.isArray(input.entries)) {
    return createDecodeResult(
      "invalid",
      false,
      ["invalid_entries"],
      sourceVersion
    );
  }

  const entries = input.entries
    .map(normalizeVoicePracticeEntry)
    .filter((entry): entry is VoicePracticeEntry => entry !== null);
  const droppedEntryCount = input.entries.length - entries.length;
  const codes: VoiceLedgerDiagnosticCode[] =
    droppedEntryCount > 0 ? ["dropped_invalid_entry"] : [];

  return {
    status: "ok",
    ledger: {
      schemaVersion: VOICE_LEDGER_SCHEMA_VERSION,
      entries
    },
    canWrite: droppedEntryCount === 0,
    diagnostics: {
      sourceVersion,
      acceptedEntryCount: entries.length,
      droppedEntryCount,
      codes
    }
  };
}

export function normalizeVoicePracticeLedger(
  input: unknown
): VoicePracticeLedger | null {
  const decoded = decodeVoicePracticeLedger(input);
  return decoded.status === "ok" && decoded.canWrite
    ? decoded.ledger
    : null;
}

export function normalizeVoicePracticeEntry(
  input: unknown
): VoicePracticeEntry | null {
  if (!isRecord(input)) {
    return null;
  }

  const id = normalizeRequiredString(input.id);
  const practicedAt = normalizeDateTime(input.practicedAt);
  const createdAt = normalizeDateTime(input.createdAt);
  const updatedAt = normalizeDateTime(input.updatedAt);
  const title = normalizeRequiredString(input.title);
  const context = normalizeContext(input.context);
  const sessionMinutes = normalizeSessionMinutes(input.sessionMinutes);
  const summary = normalizeRequiredString(input.summary);
  const usefulExpressions = normalizeStringList(input.usefulExpressions);
  const stickingPoints = normalizeStringList(input.stickingPoints);
  const corrections = normalizeStringList(input.corrections);
  const nextMission = normalizeRequiredString(input.nextMission);
  const selfNote = normalizeOptionalString(input.selfNote);
  const sourceKind = normalizeSourceKind(input.sourceKind);

  if (
    !id ||
    !practicedAt ||
    !createdAt ||
    !updatedAt ||
    !title ||
    !context ||
    sessionMinutes === undefined ||
    !summary ||
    !usefulExpressions ||
    !stickingPoints ||
    !corrections ||
    !nextMission ||
    selfNote === undefined ||
    !sourceKind
  ) {
    return null;
  }

  return {
    id,
    practicedAt,
    createdAt,
    updatedAt,
    title,
    context,
    sessionMinutes,
    summary,
    usefulExpressions,
    stickingPoints,
    corrections,
    nextMission,
    selfNote,
    sourceKind
  };
}

function createDecodeResult(
  status: VoiceLedgerDecodeResult["status"],
  canWrite: boolean,
  codes: VoiceLedgerDiagnosticCode[],
  sourceVersion: number | null = null
): VoiceLedgerDecodeResult {
  return {
    status,
    ledger: createEmptyVoicePracticeLedger(),
    canWrite,
    diagnostics: {
      sourceVersion,
      acceptedEntryCount: 0,
      droppedEntryCount: 0,
      codes
    }
  };
}

export function createEmptyVoicePracticeLedger(): VoicePracticeLedger {
  return {
    schemaVersion: VOICE_LEDGER_SCHEMA_VERSION,
    entries: []
  };
}

function normalizeSchemaVersion(value: unknown): number | null {
  return typeof value === "number" &&
    Number.isInteger(value) &&
    value >= VOICE_LEDGER_SCHEMA_VERSION
    ? value
    : null;
}

function normalizeContext(value: unknown): VoicePracticeContext | null {
  return typeof value === "string" &&
    contexts.has(value as VoicePracticeContext)
    ? (value as VoicePracticeContext)
    : null;
}

function normalizeSourceKind(
  value: unknown
): VoicePracticeSourceKind | null {
  return typeof value === "string" &&
    sourceKinds.has(value as VoicePracticeSourceKind)
    ? (value as VoicePracticeSourceKind)
    : null;
}

function normalizeSessionMinutes(value: unknown): number | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }

  return typeof value === "number" &&
    Number.isInteger(value) &&
    value > 0
    ? value
    : undefined;
}

function normalizeDateTime(value: unknown): string | null {
  const normalized = normalizeRequiredString(value);
  if (!normalized || Number.isNaN(Date.parse(normalized))) {
    return null;
  }

  return normalized;
}

function normalizeStringList(value: unknown): string[] | null {
  if (
    !Array.isArray(value) ||
    value.length > VOICE_LEDGER_LIMITS.maxListItems
  ) {
    return null;
  }

  const normalized = value.map(normalizeRequiredString);
  return normalized.every((item): item is string => item !== null)
    ? normalized
    : null;
}

function normalizeRequiredString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized || null;
}

function normalizeOptionalString(
  value: unknown
): string | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    return undefined;
  }

  return normalizeRequiredString(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
