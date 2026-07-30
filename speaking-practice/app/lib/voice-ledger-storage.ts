import {
  createEmptyVoicePracticeLedger,
  decodeVoicePracticeLedger,
  normalizeVoicePracticeEntry,
  normalizeVoicePracticeLedger,
  type VoiceLedgerDecodeDiagnostics
} from "@/lib/voice-ledger";
import type {
  VoicePracticeEntry,
  VoicePracticeLedger
} from "@/types/voice-ledger";

export const VOICE_LEDGER_STORAGE_KEY = "voice-practice-ledger";

export type VoiceLedgerStorage = Pick<Storage, "getItem" | "setItem">;

export type VoiceLedgerLoadResult = {
  status:
    | "ok"
    | "empty"
    | "invalid"
    | "unsupported_version"
    | "unavailable";
  ledger: VoicePracticeLedger;
  canWrite: boolean;
  errorCode:
    | "storage_read_failed"
    | "invalid_json"
    | "invalid_ledger"
    | "unsupported_future_version"
    | null;
  diagnostics: VoiceLedgerDecodeDiagnostics | null;
};

export class VoiceLedgerWriteBlockedError extends Error {
  readonly code:
    | "unsafe_stored_ledger"
    | "invalid_outgoing_ledger"
    | "storage_unavailable";

  constructor(
    code:
      | "unsafe_stored_ledger"
      | "invalid_outgoing_ledger"
      | "storage_unavailable"
  ) {
    super(`Voice ledger write blocked: ${code}`);
    this.name = "VoiceLedgerWriteBlockedError";
    this.code = code;
  }
}

export function loadVoicePracticeLedger(
  storage: VoiceLedgerStorage | null = getBrowserStorage()
): VoiceLedgerLoadResult {
  if (!storage) {
    return createLoadResult(
      "unavailable",
      false,
      "storage_read_failed"
    );
  }

  let stored: string | null;
  try {
    stored = storage.getItem(VOICE_LEDGER_STORAGE_KEY);
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

  const decoded = decodeVoicePracticeLedger(parsed);
  return {
    status: decoded.status,
    ledger: decoded.ledger,
    canWrite: decoded.canWrite,
    errorCode:
      decoded.status === "unsupported_version"
        ? "unsupported_future_version"
        : decoded.canWrite
          ? null
          : "invalid_ledger",
    diagnostics: decoded.diagnostics
  };
}

export function appendVoicePracticeEntry(
  entry: VoicePracticeEntry,
  storage: VoiceLedgerStorage | null = getBrowserStorage()
): VoicePracticeLedger {
  if (!storage) {
    throw new VoiceLedgerWriteBlockedError("storage_unavailable");
  }

  const current = loadVoicePracticeLedger(storage);
  if (!current.canWrite) {
    throw new VoiceLedgerWriteBlockedError("unsafe_stored_ledger");
  }

  const normalizedEntry = normalizeVoicePracticeEntry(entry);
  if (!normalizedEntry) {
    throw new VoiceLedgerWriteBlockedError("invalid_outgoing_ledger");
  }

  const nextLedger: VoicePracticeLedger = {
    schemaVersion: 1,
    entries: [
      normalizedEntry,
      ...current.ledger.entries.filter(
        (existing) => existing.id !== normalizedEntry.id
      )
    ]
  };
  const normalizedLedger = normalizeVoicePracticeLedger(nextLedger);
  if (!normalizedLedger) {
    throw new VoiceLedgerWriteBlockedError("invalid_outgoing_ledger");
  }

  storage.setItem(
    VOICE_LEDGER_STORAGE_KEY,
    JSON.stringify(normalizedLedger)
  );
  return normalizedLedger;
}

function getBrowserStorage(): VoiceLedgerStorage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function createLoadResult(
  status: VoiceLedgerLoadResult["status"],
  canWrite: boolean,
  errorCode: VoiceLedgerLoadResult["errorCode"]
): VoiceLedgerLoadResult {
  return {
    status,
    ledger: createEmptyVoicePracticeLedger(),
    canWrite,
    errorCode,
    diagnostics: null
  };
}
