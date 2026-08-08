import {
  loadProgressWithDiagnostics,
  type ProgressStorage
} from "@/lib/progress";
import {
  convertLegacyPracticeDataToLedgerV2,
  type LegacyPracticeLedgerV2ConversionResult
} from "@/lib/practice-ledger-v2";
import {
  loadVoicePracticeLedger,
  type VoiceLedgerStorage
} from "@/lib/voice-ledger-storage";
import type { PracticeLedgerV2 } from "@/types/practice-ledger";
import type { ProgressRecord } from "@/types/speaking";
import type { VoicePracticeLedger } from "@/types/voice-ledger";

export const PRACTICE_LEDGER_EXPORT_VERSION = 1 as const;
export const PRACTICE_LEDGER_MIGRATION_BACKUP_KEY =
  "speaking-practice-migration-backup-v1";

export type PracticeLedgerExport = {
  format: "speaking-practice-ledger-export";
  exportVersion: 1;
  exportedAt: string;
  ledger: PracticeLedgerV2;
  pendingSentenceHistory: string[];
};

export type PracticeLedgerMigrationBackup = {
  format: "speaking-practice-migration-backup";
  backupVersion: 1;
  createdAt: string;
  source: {
    voiceLedger: VoicePracticeLedger;
    progress: ProgressRecord;
  };
};

export type LedgerExportStorage = Pick<Storage, "getItem" | "setItem">;

export class MigrationBackupWriteBlockedError extends Error {
  readonly code:
    | "backup_already_exists"
    | "storage_unavailable"
    | "storage_write_failed";

  constructor(
    code:
      | "backup_already_exists"
      | "storage_unavailable"
      | "storage_write_failed"
  ) {
    super(`Migration backup write blocked: ${code}`);
    this.name = "MigrationBackupWriteBlockedError";
    this.code = code;
  }
}

export function createPracticeLedgerExport(input: {
  ledger: PracticeLedgerV2;
  pendingSentenceHistory: string[];
  exportedAt?: string;
}): PracticeLedgerExport {
  return {
    format: "speaking-practice-ledger-export",
    exportVersion: PRACTICE_LEDGER_EXPORT_VERSION,
    exportedAt: input.exportedAt ?? new Date().toISOString(),
    ledger: cloneLedger(input.ledger),
    pendingSentenceHistory: [...input.pendingSentenceHistory]
  };
}

export function createPracticeLedgerExportJson(input: {
  ledger: PracticeLedgerV2;
  pendingSentenceHistory: string[];
  exportedAt?: string;
}): string {
  return JSON.stringify(createPracticeLedgerExport(input), null, 2);
}

export function createMigrationBackup(input: {
  voiceLedger: VoicePracticeLedger;
  progress: ProgressRecord;
  createdAt?: string;
}): PracticeLedgerMigrationBackup {
  return {
    format: "speaking-practice-migration-backup",
    backupVersion: 1,
    createdAt: input.createdAt ?? new Date().toISOString(),
    source: {
      voiceLedger: cloneVoiceLedger(input.voiceLedger),
      progress: cloneProgress(input.progress)
    }
  };
}

export function createMigrationBackupJson(input: {
  voiceLedger: VoicePracticeLedger;
  progress: ProgressRecord;
  createdAt?: string;
}): string {
  return JSON.stringify(createMigrationBackup(input), null, 2);
}

export function saveMigrationBackup(
  backup: PracticeLedgerMigrationBackup,
  storage: LedgerExportStorage | null = getBrowserStorage()
): void {
  if (!storage) {
    throw new MigrationBackupWriteBlockedError("storage_unavailable");
  }

  let existing: string | null;
  try {
    existing = storage.getItem(PRACTICE_LEDGER_MIGRATION_BACKUP_KEY);
  } catch {
    throw new MigrationBackupWriteBlockedError("storage_write_failed");
  }

  if (existing) {
    throw new MigrationBackupWriteBlockedError("backup_already_exists");
  }

  try {
    storage.setItem(
      PRACTICE_LEDGER_MIGRATION_BACKUP_KEY,
      JSON.stringify(backup)
    );
  } catch {
    throw new MigrationBackupWriteBlockedError("storage_write_failed");
  }
}

export function loadSafeLegacySources(
  storage: (VoiceLedgerStorage & ProgressStorage) | null = getBrowserStorage()
): {
  status: "ok" | "blocked";
  conversion: LegacyPracticeLedgerV2ConversionResult;
  source: {
    voiceLedger: VoicePracticeLedger;
    progress: ProgressRecord;
  } | null;
} {
  if (!storage) {
    return {
      status: "blocked",
      conversion: convertLegacyPracticeDataToLedgerV2({
        voiceLedger: null,
        progress: null
      }),
      source: null
    };
  }

  const voice = loadVoicePracticeLedger(storage);
  const progress = loadProgressWithDiagnostics(storage);
  const conversion = convertLegacyPracticeDataToLedgerV2({
    voiceLedger: voice.ledger,
    progress: progress.progress
  });
  const safe = voice.canWrite && progress.canWrite && conversion.status === "ok";

  return {
    status: safe ? "ok" : "blocked",
    conversion: safe
      ? conversion
      : {
          ...conversion,
          status: "blocked",
          ledger: null
        },
    source: safe
      ? { voiceLedger: voice.ledger, progress: progress.progress }
      : null
  };
}

export function downloadJsonFile(
  json: string,
  filename: string,
  documentRef: Pick<Document, "createElement" | "body"> = document
): void {
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = documentRef.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  documentRef.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function cloneLedger(ledger: PracticeLedgerV2): PracticeLedgerV2 {
  return JSON.parse(JSON.stringify(ledger)) as PracticeLedgerV2;
}

function cloneVoiceLedger(ledger: VoicePracticeLedger): VoicePracticeLedger {
  return JSON.parse(JSON.stringify(ledger)) as VoicePracticeLedger;
}

function cloneProgress(progress: ProgressRecord): ProgressRecord {
  return JSON.parse(JSON.stringify(progress)) as ProgressRecord;
}

function getBrowserStorage(): LedgerExportStorage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
