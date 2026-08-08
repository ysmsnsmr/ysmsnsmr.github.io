"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  createMigrationBackup,
  createMigrationBackupJson,
  createPracticeLedgerExportJson,
  downloadJsonFile,
  loadSafeLegacySources,
  MigrationBackupWriteBlockedError,
  saveMigrationBackup
} from "@/lib/ledger-export";
import {
  importPracticeLedgerV2NonDestructively,
  loadStoredPracticeLedgerV2,
  previewPracticeLedgerImportJson,
  PracticeLedgerImportWriteBlockedError,
  type PracticeLedgerImportPreview
} from "@/lib/practice-ledger-import";
import type { PracticeLedgerEntry } from "@/types/practice-ledger";
import { normalizeVoicePracticeEntry } from "@/lib/voice-ledger";
import {
  appendVoicePracticeEntry,
  loadVoicePracticeLedger,
  VoiceLedgerWriteBlockedError
} from "@/lib/voice-ledger-storage";
import {
  parseVoiceSessionLog,
  VOICE_SESSION_LOG_PROMPT,
  type ManualEntryForm,
  type VoiceSessionLogParseResult
} from "@/lib/voice-session-log";
import type {
  VoicePracticeContext,
  VoicePracticeSourceKind
} from "@/types/voice-ledger";

type EntryMode = "paste" | "manual";
type ListFieldName =
  | "usefulExpressions"
  | "stickingPoints"
  | "corrections";
type UpdateField = <K extends keyof ManualEntryForm>(
  field: K,
  value: ManualEntryForm[K]
) => void;
type StatusMessage = {
  kind: "success" | "error" | "info";
  text: string;
};

const contextOptions: Array<{
  value: VoicePracticeContext;
  label: string;
}> = [
  { value: "work", label: "仕事" },
  { value: "travel", label: "旅行" },
  { value: "daily", label: "日常" },
  { value: "other", label: "その他" }
];

export default function VoiceLedgerApp() {
  const [entryMode, setEntryMode] = useState<EntryMode>("paste");
  const [form, setForm] = useState<ManualEntryForm>(createInitialForm);
  const [rawLog, setRawLog] = useState("");
  const [parseResult, setParseResult] =
    useState<VoiceSessionLogParseResult | null>(null);
  const [entries, setEntries] = useState<PracticeLedgerEntry[]>([]);
  const [ready, setReady] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [statusMessage, setStatusMessage] =
    useState<StatusMessage | null>(null);
  const [importPreview, setImportPreview] =
    useState<PracticeLedgerImportPreview | null>(null);

  useEffect(() => {
    const loaded = loadVoicePracticeLedger();
    setCanWrite(loaded.canWrite);

    const storedV2 = loadStoredPracticeLedgerV2();
    if (storedV2.status === "ok") {
      setEntries(storedV2.ledger.entries);
    } else if (storedV2.status === "empty") {
      const legacyProjection = loadSafeLegacySources();
      setEntries(legacyProjection.conversion.ledger?.entries ?? []);
    } else {
      setStatusMessage({
        kind: "error",
        text: "v2台帳を安全に読み込めないため、表示を停止しています。"
      });
    }
    setReady(true);

    if (loaded.errorCode === "unsupported_future_version") {
      setStatusMessage({
        kind: "error",
        text: "この台帳は新しいバージョンで作成されています。内容は変更していません。"
      });
    } else if (!loaded.canWrite) {
      setStatusMessage({
        kind: "error",
        text: "保存済みの台帳を安全に読めないため、保存を停止しています。"
      });
    }
  }, []);

  const sortedEntries = useMemo(
    () =>
      [...entries].sort(
        (left, right) =>
          Date.parse(right.occurredAt) - Date.parse(left.occurredAt) ||
          Date.parse(right.createdAt ?? "") - Date.parse(left.createdAt ?? "")
      ),
    [entries]
  );
  const trialCount = Math.min(entries.length, 10);
  const canSave = ready && canWrite;

  function updateField<K extends keyof ManualEntryForm>(
    field: K,
    value: ManualEntryForm[K]
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateListItem(
    field: ListFieldName,
    index: number,
    value: string
  ) {
    setForm((current) => {
      const nextItems = [...current[field]];
      nextItems[index] = value;
      return { ...current, [field]: nextItems };
    });
  }

  function addListItem(field: ListFieldName) {
    setForm((current) => {
      if (current[field].length >= 5) {
        return current;
      }
      return { ...current, [field]: [...current[field], ""] };
    });
  }

  function removeListItem(field: ListFieldName, index: number) {
    setForm((current) => {
      const nextItems = current[field].filter(
        (_item, itemIndex) => itemIndex !== index
      );
      return { ...current, [field]: nextItems };
    });
  }

  function changeEntryMode(nextMode: EntryMode) {
    if (nextMode === entryMode) {
      return;
    }
    clearPasteState();
    setEntryMode(nextMode);
    setStatusMessage(null);
  }

  function clearPasteState() {
    setRawLog("");
    setParseResult(null);
  }

  function convertPasteToDraft() {
    if (!rawLog.trim()) {
      setStatusMessage({
        kind: "error",
        text: "Voice練習後のまとめを貼り付けてください。"
      });
      return;
    }

    const result = parseVoiceSessionLog(rawLog, {
      practicedAt: form.practicedAt,
      context: form.context
    });
    setForm(result.draft);
    setParseResult(result);
    setStatusMessage(null);
  }

  async function copySessionPrompt() {
    try {
      if (!navigator.clipboard) {
        throw new Error("clipboard unavailable");
      }
      await navigator.clipboard.writeText(VOICE_SESSION_LOG_PROMPT);
      setStatusMessage({
        kind: "success",
        text: "まとめ用テンプレートをコピーしました。"
      });
    } catch {
      setStatusMessage({
        kind: "info",
        text: "コピーできませんでした。下のテンプレートを選択してコピーしてください。"
      });
    }
  }

  function cancelPasteDraft() {
    const preserved = {
      practicedAt: form.practicedAt,
      context: form.context
    };
    clearPasteState();
    setForm(createInitialForm(preserved));
    setStatusMessage({
      kind: "info",
      text: "貼り付けた内容と下書きを破棄しました。"
    });
  }

  function handleExport() {
    const loaded = loadSafeLegacySources();
    if (loaded.status !== "ok" || !loaded.conversion.ledger || !loaded.source) {
      setStatusMessage({
        kind: "error",
        text: "保存済みデータを安全に読み込めないため、JSONを書き出せません。"
      });
      return;
    }

    const json = createPracticeLedgerExportJson({
      ledger: loaded.conversion.ledger,
      pendingSentenceHistory: loaded.source.progress.completedCardIds
    });
    downloadJsonFile(json, `speaking-practice-ledger-${getFileDate()}.json`);
    setStatusMessage({
      kind: "success",
      text: "Ledger v2のJSONを書き出しました。"
    });
  }

  function handleMigrationBackup() {
    const loaded = loadSafeLegacySources();
    if (loaded.status !== "ok" || !loaded.source) {
      setStatusMessage({
        kind: "error",
        text: "保存済みデータを安全に読み込めないため、バックアップを作成できません。"
      });
      return;
    }

    const backup = createMigrationBackup(loaded.source);
    try {
      saveMigrationBackup(backup);
      downloadJsonFile(
        createMigrationBackupJson({
          ...loaded.source,
          createdAt: backup.createdAt
        }),
        `speaking-practice-migration-backup-${getFileDate()}.json`
      );
      setStatusMessage({
        kind: "success",
        text: "移行前バックアップを保存し、JSONもダウンロードしました。"
      });
    } catch (error) {
      setStatusMessage({
        kind: "error",
        text:
          error instanceof MigrationBackupWriteBlockedError &&
          error.code === "backup_already_exists"
            ? "移行前バックアップはすでに作成済みです。既存のバックアップは上書きしません。"
            : "移行前バックアップを保存できませんでした。既存データは変更していません。"
      });
    }
  }

  async function handleImportFile(
    event: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) {
      return;
    }

    const json = await file.text();
    const stored = loadStoredPracticeLedgerV2();
    const preview = previewPracticeLedgerImportJson(
      json,
      stored.status === "ok" ? stored.ledger : null
    );
    setImportPreview(preview);
    setStatusMessage(
      preview.status === "valid"
        ? {
            kind: "info",
            text: "JSONを検証しました。内容を確認してから追加してください。"
          }
        : {
            kind: "error",
            text: "JSONを読み込めませんでした。内容を確認してください。"
          }
    );
  }

  function handleImportApply() {
    if (!importPreview || importPreview.status !== "valid" || !importPreview.ledger) {
      return;
    }

    try {
      const result = importPracticeLedgerV2NonDestructively(
        importPreview.ledger,
        undefined,
        importPreview.pendingSentenceHistory
      );
      setImportPreview(null);
      setStatusMessage({
        kind: "success",
        text: `v2台帳へ${result.addedEntryCount}件を追加しました。既存のVoice履歴は変更していません。`
      });
    } catch (error) {
      setStatusMessage({
        kind: "error",
        text:
          error instanceof PracticeLedgerImportWriteBlockedError &&
          error.code === "unsafe_stored_ledger"
            ? "既存のv2台帳を安全に読めないため、追加を停止しました。"
            : "v2台帳へ追加できませんでした。既存データは変更していません。"
      });
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage(null);

    if (entryMode === "paste" && !parseResult) {
      setStatusMessage({
        kind: "error",
        text: "貼り付けたログを下書きへ変換してから保存してください。"
      });
      return;
    }

    const now = new Date().toISOString();
    const sourceKind: VoicePracticeSourceKind =
      entryMode === "paste" ? "chatgpt_summary" : "manual";
    const candidate = normalizeVoicePracticeEntry({
      id: createEntryId(),
      practicedAt: form.practicedAt,
      createdAt: now,
      updatedAt: now,
      title: form.title,
      context: form.context,
      sessionMinutes:
        form.sessionMinutes.trim() === ""
          ? null
          : Number(form.sessionMinutes),
      summary: form.summary,
      usefulExpressions: compactList(form.usefulExpressions),
      stickingPoints: compactList(form.stickingPoints),
      corrections: compactList(form.corrections),
      nextMission: form.nextMission,
      selfNote: form.selfNote,
      sourceKind
    });

    if (!candidate) {
      setStatusMessage({
        kind: "error",
        text: "練習日、テーマ、要約、最優先の修正点、次回の課題を確認してください。練習時間は入力する場合、正の整数にします。"
      });
      return;
    }

    try {
      appendVoicePracticeEntry(candidate);
      let canonicalSyncSucceeded = true;
      const canonical = loadSafeLegacySources();
      if (canonical.status === "ok" && canonical.conversion.ledger && canonical.source) {
        const storedV2 = loadStoredPracticeLedgerV2();
        if (storedV2.status === "ok" || storedV2.status === "empty") {
          try {
            const imported = importPracticeLedgerV2NonDestructively(
              canonical.conversion.ledger,
              undefined,
              canonical.source.progress.completedCardIds
            );
            setEntries(imported.ledger.entries);
          } catch {
            canonicalSyncSucceeded = false;
            setCanWrite(false);
            setEntries([]);
            setStatusMessage({
              kind: "error",
              text: "v2台帳を安全に更新できないため、保存後の表示を停止しました。"
            });
          }
        } else {
          canonicalSyncSucceeded = false;
          setCanWrite(false);
          setEntries([]);
          setStatusMessage({
            kind: "error",
            text: "v2台帳を安全に読み込めないため、表示を停止しました。"
          });
        }
      } else {
        canonicalSyncSucceeded = false;
        setEntries([]);
        setStatusMessage({
          kind: "error",
          text: "旧データを安全に読み込めないため、v2台帳を更新できませんでした。"
        });
      }
      setForm(
        createInitialForm({
          practicedAt: form.practicedAt,
          context: form.context
        })
      );
      clearPasteState();
      if (canonicalSyncSucceeded) {
        setStatusMessage({
          kind: "success",
          text: "練習記録を保存しました。"
        });
      }
    } catch (error) {
      setCanWrite(
        error instanceof VoiceLedgerWriteBlockedError ? false : canWrite
      );
      setStatusMessage({
        kind: "error",
        text:
          error instanceof VoiceLedgerWriteBlockedError
            ? "保存済みデータを保護するため、保存を停止しています。"
            : "この端末に保存できませんでした。既存の記録は変更していません。"
      });
    }
  }

  return (
    <main className="min-h-dvh bg-[#F3F7F6] px-4 py-5 text-slate-800 sm:px-6 sm:py-7">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.08em] text-calm">
              Voice practice ledger
            </p>
            <h1 className="mt-1 text-2xl font-bold leading-tight text-slate-950 sm:text-3xl">
              Voice練習ノート
            </h1>
          </div>
          <Link
            href="/"
            className="rounded-lg bg-white px-4 py-2 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
          >
            現在の練習へ
          </Link>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleExport}
              className="min-h-10 rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
            >
              JSONを書き出す
            </button>
            <button
              type="button"
              onClick={handleMigrationBackup}
              className="min-h-10 rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
            >
              移行前バックアップ
            </button>
            <label className="min-h-10 cursor-pointer rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50">
              JSONを読み込む
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) => void handleImportFile(event)}
                className="sr-only"
              />
            </label>
          </div>
        </header>

        {importPreview && (
          <ImportPreviewPanel
            preview={importPreview}
            onApply={handleImportApply}
            onCancel={() => setImportPreview(null)}
          />
        )}

        <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <section className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-slate-100 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.08em] text-calm">
                  新しい記録
                </p>
                <h2 className="mt-1 text-xl font-bold text-slate-950">
                  Voice練習のあとに残す
                </h2>
              </div>
              <span className="rounded-full bg-calm-soft px-3 py-1 text-xs font-bold text-calm">
                この端末のみ
              </span>
            </div>

            <div
              role="tablist"
              aria-label="記録方法"
              className="mt-5 grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1"
            >
              <ModeButton
                active={entryMode === "paste"}
                label="ログを貼り付け"
                onClick={() => changeEntryMode("paste")}
              />
              <ModeButton
                active={entryMode === "manual"}
                label="手入力に切り替え"
                onClick={() => changeEntryMode("manual")}
              />
            </div>

            <form noValidate onSubmit={handleSubmit} className="mt-5">
              {entryMode === "paste" ? (
                <section id="paste-entry" role="tabpanel">
                  <div className="rounded-lg border border-calm/20 bg-calm-soft/50 p-4">
                    <p className="text-sm font-semibold leading-relaxed text-slate-700">
                      ChatGPT Voiceを終えたら、先にこのテンプレートを渡して短くまとめます。会話全文は貼り付けません。
                    </p>
                    <button
                      type="button"
                      onClick={() => void copySessionPrompt()}
                      className="mt-3 min-h-11 rounded-lg bg-calm px-4 py-2 text-sm font-bold text-white transition hover:bg-[#0B625C]"
                    >
                      まとめ用テンプレートをコピー
                    </button>
                    <details className="mt-3 rounded-lg bg-white/80 p-3">
                      <summary className="cursor-pointer text-sm font-bold text-slate-700">
                        コピーできない場合のテンプレート
                      </summary>
                      <textarea
                        readOnly
                        value={VOICE_SESSION_LOG_PROMPT}
                        rows={13}
                        className={`${inputClassName} resize-y bg-white text-sm leading-relaxed`}
                        aria-label="コピー用テンプレート"
                      />
                    </details>
                  </div>

                  <label className="mt-5 block text-sm font-semibold text-slate-700">
                    Voice練習後のまとめを貼り付け
                    <textarea
                      rows={10}
                      value={rawLog}
                      onChange={(event) => {
                        setRawLog(event.target.value);
                        setParseResult(null);
                      }}
                      className={`${inputClassName} resize-y leading-relaxed`}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={!rawLog.trim()}
                    onClick={convertPasteToDraft}
                    className="mt-3 min-h-11 rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    下書きに変換
                  </button>

                  {parseResult && (
                    <ParseFeedback parseResult={parseResult} />
                  )}

                  {parseResult && (
                    <div className="mt-5 border-t border-slate-100 pt-5">
                      <p className="text-sm font-bold text-slate-950">
                        内容を確認して保存
                      </p>
                      <EntryEditor
                        compact
                        form={form}
                        updateField={updateField}
                        updateListItem={updateListItem}
                        addListItem={addListItem}
                        removeListItem={removeListItem}
                      />
                      <div className="mt-5 flex flex-wrap gap-3">
                        <button
                          type="submit"
                          disabled={!canSave}
                          className="min-h-11 rounded-lg bg-calm px-5 py-2 text-sm font-bold text-white transition hover:bg-[#0B625C] disabled:cursor-not-allowed disabled:bg-slate-300"
                        >
                          記録を保存
                        </button>
                        <button
                          type="button"
                          onClick={cancelPasteDraft}
                          className="min-h-11 rounded-lg px-4 py-2 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
                        >
                          貼り付け内容を破棄
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              ) : (
                <section id="manual-entry" role="tabpanel">
                  <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-600">
                    Voiceのまとめがない日は、ここから短く手入力できます。
                  </p>
                  <EntryEditor
                    form={form}
                    updateField={updateField}
                    updateListItem={updateListItem}
                    addListItem={addListItem}
                    removeListItem={removeListItem}
                  />
                  <button
                    type="submit"
                    disabled={!canSave}
                    className="mt-5 min-h-11 w-full rounded-lg bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-[#0B625C] active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    記録を保存
                  </button>
                </section>
              )}

              <StatusNotice message={statusMessage} />
            </form>
          </section>

          <aside className="lg:sticky lg:top-5">
            <section className="border-b border-slate-200 pb-4">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.08em] text-calm">
                    試用の進み具合
                  </p>
                  <h2 className="mt-1 text-xl font-bold text-slate-950">
                    最近の記録
                  </h2>
                </div>
                <p className="text-sm font-bold text-slate-600">
                  {trialCount} / 10
                </p>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-honey transition-[width]"
                  style={{ width: `${trialCount * 10}%` }}
                />
              </div>
            </section>

            <div className="mt-4 grid gap-3">
              {!ready && (
                <p className="rounded-lg bg-white px-4 py-5 text-sm font-semibold text-slate-500 ring-1 ring-slate-100">
                  台帳を読み込んでいます...
                </p>
              )}
              {ready && sortedEntries.length === 0 && (
                <p className="rounded-lg bg-white px-4 py-5 text-sm leading-relaxed text-slate-600 ring-1 ring-slate-100">
                  まだ記録はありません。
                </p>
              )}
              {sortedEntries.map((entry) => (
                <article
                  key={entry.id}
                  className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-100"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-calm">
                      {formatContext(entry.context ?? "other")}
                    </p>
                    <time className="text-xs font-semibold text-slate-500">
                      {formatDate(entry.occurredAt)}
                    </time>
                  </div>
                  <h3 className="mt-2 text-base font-bold leading-snug text-slate-950">
                    {entry.title}
                  </h3>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    {formatLedgerSource(entry.source)} ・ {formatReviewBasis(entry.reviewBasis)}
                  </p>
                  <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-600">
                    {entry.summary}
                  </p>
                  <div className="mt-3 border-l-4 border-honey bg-[#FFF9E8] px-3 py-2">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">
                      次回の課題
                    </p>
                    <p className="mt-1 whitespace-pre-line text-sm font-semibold leading-relaxed text-slate-800">
                      {entry.nextMission}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}

type ModeButtonProps = {
  active: boolean;
  label: string;
  onClick: () => void;
};

function ModeButton({ active, label, onClick }: ModeButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={[
        "min-h-11 rounded-md px-3 py-2 text-sm font-bold transition",
        active
          ? "bg-white text-slate-950 shadow-sm"
          : "text-slate-600 hover:bg-white/70"
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function ParseFeedback({
  parseResult
}: {
  parseResult: VoiceSessionLogParseResult;
}) {
  return (
    <div className="mt-4 grid gap-3">
      {parseResult.status === "incomplete" && (
        <p className="rounded-lg bg-coral/10 px-4 py-3 text-sm font-semibold leading-relaxed text-[#A13C2A]">
          保存前に入力してください: {parseResult.missingFields.join("、")}
        </p>
      )}
      {parseResult.warnings.map((warning) => (
        <p
          key={warning}
          className="rounded-lg bg-[#FFF9E8] px-4 py-3 text-sm leading-relaxed text-slate-700"
        >
          {warning}
        </p>
      ))}
    </div>
  );
}

function ImportPreviewPanel({
  preview,
  onApply,
  onCancel
}: {
  preview: PracticeLedgerImportPreview;
  onApply: () => void;
  onCancel: () => void;
}) {
  return (
    <section className="mt-5 rounded-lg bg-white p-5 shadow-soft ring-1 ring-slate-100 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.08em] text-calm">
            Import preview
          </p>
          <h2 className="mt-1 text-xl font-bold text-slate-950">
            JSONの検証結果
          </h2>
        </div>
        <span
          className={[
            "rounded-full px-3 py-1 text-xs font-bold",
            preview.status === "valid"
              ? "bg-calm-soft text-calm"
              : "bg-coral/10 text-[#A13C2A]"
          ].join(" ")}
        >
          {preview.status === "valid" ? "読み込み可能" : "読み込み不可"}
        </span>
      </div>

      {preview.status === "valid" ? (
        <>
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <ImportStat label="対象" value={formatImportSource(preview.source)} />
            <ImportStat label="追加予定" value={`${preview.newEntryCount}件`} />
            <ImportStat label="重複" value={`${preview.duplicateEntryCount}件`} />
          </dl>
          <p className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-600">
            適用するとv2専用台帳へ追加します。既存のVoice LedgerとProgressは変更しません。
          </p>
          {preview.warnings.map((warning) => (
            <p
              key={warning}
              className="mt-3 rounded-lg bg-[#FFF9E8] px-4 py-3 text-sm leading-relaxed text-slate-700"
            >
              {warning}
            </p>
          ))}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onApply}
              className="min-h-11 rounded-lg bg-calm px-5 py-2 text-sm font-bold text-white transition hover:bg-[#0B625C]"
            >
              この内容をv2台帳へ追加
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="min-h-11 rounded-lg px-4 py-2 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
            >
              キャンセル
            </button>
          </div>
        </>
      ) : (
        <div className="mt-4 grid gap-3">
          {preview.errors.map((error) => (
            <p
              key={error}
              className="rounded-lg bg-coral/10 px-4 py-3 text-sm font-semibold leading-relaxed text-[#A13C2A]"
            >
              {error}
            </p>
          ))}
          <button
            type="button"
            onClick={onCancel}
            className="min-h-11 w-fit rounded-lg px-4 py-2 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
          >
            閉じる
          </button>
        </div>
      )}
    </section>
  );
}

function ImportStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3">
      <dt className="text-xs font-bold text-slate-500">{label}</dt>
      <dd className="mt-1 text-lg font-bold text-slate-950">{value}</dd>
    </div>
  );
}

function formatImportSource(
  source: PracticeLedgerImportPreview["source"]
) {
  return source === "migration_backup" ? "移行前バックアップ" : "Ledger v2 JSON";
}

type EntryEditorProps = {
  compact?: boolean;
  form: ManualEntryForm;
  updateField: UpdateField;
  updateListItem: (field: ListFieldName, index: number, value: string) => void;
  addListItem: (field: ListFieldName) => void;
  removeListItem: (field: ListFieldName, index: number) => void;
};

function EntryEditor({
  compact = false,
  form,
  updateField,
  updateListItem,
  addListItem,
  removeListItem
}: EntryEditorProps) {
  return (
    <div className="mt-4">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_140px]">
        <label className="block text-sm font-semibold text-slate-700">
          練習日 <span aria-hidden="true">*</span>
          <input
            type="date"
            aria-required="true"
            value={form.practicedAt}
            onChange={(event) => updateField("practicedAt", event.target.value)}
            className={inputClassName}
          />
        </label>
        {!compact && (
          <MinutesField form={form} updateField={updateField} />
        )}
      </div>

      <fieldset className="mt-4">
        <legend className="text-sm font-semibold text-slate-700">場面</legend>
        <div className="mt-2 grid grid-cols-4 gap-2">
          {contextOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={form.context === option.value}
              onClick={() => updateField("context", option.value)}
              className={[
                "min-h-11 rounded-lg px-2 text-sm font-bold ring-1 transition",
                form.context === option.value
                  ? "bg-calm text-white ring-calm"
                  : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
              ].join(" ")}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="mt-4 block text-sm font-semibold text-slate-700">
        テーマ <span aria-hidden="true">*</span>
        <input
          aria-required="true"
          value={form.title}
          onChange={(event) => updateField("title", event.target.value)}
          className={inputClassName}
        />
      </label>

      <label className="mt-4 block text-sm font-semibold text-slate-700">
        要約 <span aria-hidden="true">*</span>
        <textarea
          aria-required="true"
          rows={4}
          value={form.summary}
          onChange={(event) => updateField("summary", event.target.value)}
          className={`${inputClassName} resize-y leading-relaxed`}
        />
      </label>

      <ListField
        id="corrections"
        label="最優先の修正点"
        values={form.corrections}
        onChange={(index, value) => updateListItem("corrections", index, value)}
        onAdd={() => addListItem("corrections")}
        onRemove={(index) => removeListItem("corrections", index)}
      />

      <label className="mt-5 block text-sm font-semibold text-slate-700">
        次回の課題 <span aria-hidden="true">*</span>
        <textarea
          aria-required="true"
          rows={3}
          value={form.nextMission}
          onChange={(event) => updateField("nextMission", event.target.value)}
          className={`${inputClassName} resize-y leading-relaxed`}
        />
      </label>

      {compact ? (
        <details className="mt-5 rounded-lg border border-slate-200 p-4">
          <summary className="cursor-pointer text-sm font-bold text-slate-700">
            詳細を編集
          </summary>
          <div className="mt-4">
            <MinutesField form={form} updateField={updateField} />
            <OptionalFields
              form={form}
              updateField={updateField}
              updateListItem={updateListItem}
              addListItem={addListItem}
              removeListItem={removeListItem}
            />
          </div>
        </details>
      ) : (
        <OptionalFields
          form={form}
          updateField={updateField}
          updateListItem={updateListItem}
          addListItem={addListItem}
          removeListItem={removeListItem}
        />
      )}
    </div>
  );
}

function MinutesField({
  form,
  updateField
}: Pick<EntryEditorProps, "form" | "updateField">) {
  return (
    <label className="block text-sm font-semibold text-slate-700">
      練習時間（分）
      <input
        type="number"
        min="1"
        step="1"
        inputMode="numeric"
        value={form.sessionMinutes}
        onChange={(event) => updateField("sessionMinutes", event.target.value)}
        className={inputClassName}
      />
    </label>
  );
}

function OptionalFields({
  form,
  updateField,
  updateListItem,
  addListItem,
  removeListItem
}: Omit<EntryEditorProps, "compact">) {
  return (
    <div className="mt-5 border-t border-slate-100 pt-5">
      <ListField
        id="useful-expressions"
        label="練習した自然な文"
        values={form.usefulExpressions}
        onChange={(index, value) =>
          updateListItem("usefulExpressions", index, value)
        }
        onAdd={() => addListItem("usefulExpressions")}
        onRemove={(index) => removeListItem("usefulExpressions", index)}
      />
      <ListField
        id="sticking-points"
        label="重点音・聞き取りにくかった表現"
        values={form.stickingPoints}
        onChange={(index, value) => updateListItem("stickingPoints", index, value)}
        onAdd={() => addListItem("stickingPoints")}
        onRemove={(index) => removeListItem("stickingPoints", index)}
      />
      <label className="mt-5 block text-sm font-semibold text-slate-700">
        前回からの変化
        <textarea
          rows={2}
          value={form.selfNote}
          onChange={(event) => updateField("selfNote", event.target.value)}
          className={`${inputClassName} resize-y leading-relaxed`}
        />
      </label>
    </div>
  );
}

type ListFieldProps = {
  id: string;
  label: string;
  values: string[];
  onChange: (index: number, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
};

function ListField({
  id,
  label,
  values,
  onChange,
  onAdd,
  onRemove
}: ListFieldProps) {
  return (
    <fieldset className="mt-5">
      <div className="flex items-center justify-between gap-3">
        <legend className="text-sm font-semibold text-slate-700">{label}</legend>
        {values.length < 5 && (
          <button
            type="button"
            onClick={onAdd}
            className="min-h-9 rounded-lg px-2 py-1 text-xs font-bold text-calm transition hover:bg-calm-soft"
          >
            追加
          </button>
        )}
      </div>
      {values.length > 0 && (
        <div className="mt-2 grid gap-2">
          {values.map((value, index) => (
            <div
              key={`${id}-${index}`}
              className="grid grid-cols-[minmax(0,1fr)_auto] gap-2"
            >
              <input
                aria-label={`${label} ${index + 1}`}
                value={value}
                onChange={(event) => onChange(index, event.target.value)}
                className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-calm focus:ring-4 focus:ring-calm/15"
              />
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="min-h-11 rounded-lg px-3 text-xs font-bold text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50"
              >
                削除
              </button>
            </div>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function StatusNotice({ message }: { message: StatusMessage | null }) {
  const className =
    message?.kind === "error"
      ? "bg-coral/10 text-[#A13C2A]"
      : message?.kind === "success"
        ? "bg-calm-soft text-calm"
        : "bg-slate-50 text-slate-600";

  return (
    <div
      aria-live="polite"
      className={`mt-4 min-h-11 rounded-lg px-3 py-3 text-sm font-semibold ${className}`}
    >
      {message?.text ?? "保存するのは、確認した構造化メモだけです。"}
    </div>
  );
}

const inputClassName =
  "mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-base text-slate-900 outline-none transition focus:border-calm focus:ring-4 focus:ring-calm/15";

function createInitialForm(
  preserved: Partial<Pick<ManualEntryForm, "practicedAt" | "context">> = {}
): ManualEntryForm {
  return {
    practicedAt: preserved.practicedAt ?? getLocalDate(),
    title: "",
    context: preserved.context ?? "work",
    sessionMinutes: "",
    summary: "",
    usefulExpressions: [""],
    stickingPoints: [""],
    corrections: [""],
    nextMission: "",
    selfNote: ""
  };
}

function getLocalDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function compactList(values: string[]) {
  return values.map((value) => value.trim()).filter(Boolean);
}

function createEntryId() {
  if (
    typeof globalThis.crypto !== "undefined" &&
    typeof globalThis.crypto.randomUUID === "function"
  ) {
    return globalThis.crypto.randomUUID();
  }

  return `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getFileDate() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function formatDate(value: string) {
  const date = new Date(
    value.length === 10 ? `${value}T00:00:00` : value
  );
  return new Intl.DateTimeFormat("ja-JP", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(date);
}

function formatContext(context: VoicePracticeContext) {
  return contextOptions.find((option) => option.value === context)?.label ?? "その他";
}

function formatLedgerSource(source: PracticeLedgerEntry["source"]) {
  switch (source) {
    case "external_voice":
      return "外部Voice";
    case "in_app_recording":
      return "アプリ録音";
    case "quiet_mode":
      return "quiet mode";
    case "sentence_practice":
      return "Sentence練習";
  }
}

function formatReviewBasis(basis: PracticeLedgerEntry["reviewBasis"]) {
  switch (basis) {
    case "self_report":
      return "自己申告";
    case "transcript_based":
      return "文字起こしベース";
    case "none":
      return "記録のみ";
  }
}
