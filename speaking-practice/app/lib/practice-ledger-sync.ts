import {
  importPracticeLedgerV2NonDestructively,
  type PracticeLedgerImportResult,
  type PracticeLedgerV2Storage
} from "@/lib/practice-ledger-import";
import { loadSafeLegacySources } from "@/lib/ledger-export";
import type { PracticeLedgerEntry, PracticeLedgerV2 } from "@/types/practice-ledger";

export class PracticeLedgerSyncBlockedError extends Error {
  constructor() {
    super("Practice Ledger v2 sync blocked");
    this.name = "PracticeLedgerSyncBlockedError";
  }
}

export function syncLegacySourcesToPracticeLedgerV2(
  storage?: PracticeLedgerV2Storage | null
): PracticeLedgerV2 {
  const loaded = loadSafeLegacySources(storage);
  if (loaded.status !== "ok" || !loaded.conversion.ledger || !loaded.source) {
    throw new PracticeLedgerSyncBlockedError();
  }

  return importPracticeLedgerV2NonDestructively(
    loaded.conversion.ledger,
    storage,
    loaded.source.progress.completedCardIds
  ).ledger;
}

export function appendPracticeLedgerEntryToV2(
  entry: PracticeLedgerEntry,
  pendingSentenceHistory: string[] = [],
  storage?: PracticeLedgerV2Storage | null
): PracticeLedgerImportResult {
  return importPracticeLedgerV2NonDestructively(
    {
      schemaVersion: 2,
      entries: [entry]
    },
    storage,
    pendingSentenceHistory
  );
}

export function syncLegacySourcesAndAppendPracticeLedgerEntry(
  entry: PracticeLedgerEntry,
  pendingSentenceHistory: string[] = [],
  storage?: PracticeLedgerV2Storage | null
): PracticeLedgerImportResult {
  syncLegacySourcesToPracticeLedgerV2(storage);
  return appendPracticeLedgerEntryToV2(
    entry,
    pendingSentenceHistory,
    storage
  );
}
