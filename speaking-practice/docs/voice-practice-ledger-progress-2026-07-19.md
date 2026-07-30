# Voice Practice Ledger 進捗整理

更新日: 2026-07-19

## 1. 現在の方針

`Speaking Practice`を会話エンジンや発音採点器として拡張せず、ChatGPT Voiceなどで行った練習を次回の練習へつなぐ学習台帳として育てる。

役割分担は以下のとおり。

- ChatGPT Voice: 会話、面接、言い直し、聞き返し
- Voice Practice Ledger: 本人が確認した要約、表現、詰まり、訂正、次回ミッション
- Groq Whisper: 既存Interview modeでの文字起こしベース確認
- 既存Interview/Sentence mode: 現状維持
- 音響測定と発音スコア: 今回の対象外

新台帳は既存の`PracticeSession`や`speaking-practice-progress`へ統合せず、独立したデータ契約とlocalStorageキーを使用する。

## 2. チェックポイント状況

| チェックポイント | 状況 | 内容 |
|---|---|---|
| CP1 | 完了 | 現行progressの非破壊load、future-version拒否、診断結果 |
| CP2a | 完了 | `VoicePracticeEntry`型、純粋なdecode/normalize、fixtureテスト |
| CP2b | 一部のみ | CP3に必要なload・append・再読込を実装。編集・削除・JSON exportは未実装 |
| CP3 | 実装完了 | `/ledger`でAPIなしの手動記録、履歴、試用件数を実装 |
| 実使用観察 | 未完了 | 自動テスト5件は完了。実際のVoice練習後の5〜10件記録はこれから |
| 解析API | 未着手 | 手動記録の負担を確認するまで実装しない |

## 3. CP1: 既存progressの安全化

対象:

- `app/lib/progress.ts`
- `app/lib/progress.test.ts`
- `app/lib/__fixtures__/progress-v3-future.json`

実施内容:

- `loadProgress()`による読み込み時のlocalStorage書き戻しを廃止
- 互換APIを維持したまま`loadProgressWithDiagnostics()`を追加
- 純粋な`decodeProgress()`を追加
- `schemaVersion > 2`を拒否し、v2へのダウングレードを防止
- 不正JSONや無効セッションを含む履歴への保存を停止
- `ProgressWriteBlockedError`で危険な保存操作を明示的に拒否

診断結果:

- 元schema version
- 移行の有無
- 受理セッション数
- 除外セッション数
- 内容を含まない理由コード

これにより、旧データは読み込むだけでは変更されず、future-versionや破損データも自動上書きされない。

## 4. CP2a: 新台帳の純粋なデータ契約

対象:

- `app/types/voice-ledger.ts`
- `app/lib/voice-ledger.ts`
- `app/lib/voice-ledger.test.ts`
- `app/lib/__fixtures__/voice-ledger-v1-valid.json`
- `app/lib/__fixtures__/voice-ledger-v1-corrupt.json`
- `app/lib/__fixtures__/voice-ledger-v2-future.json`

現在の保存型:

```ts
type VoicePracticeEntry = {
  id: string;
  practicedAt: string;
  createdAt: string;
  updatedAt: string;
  title: string;
  context: "work" | "travel" | "daily" | "other";
  sessionMinutes: number | null;
  summary: string;
  usefulExpressions: string[];
  stickingPoints: string[];
  corrections: string[];
  nextMission: string;
  selfNote: string | null;
  sourceKind: "voice_transcript" | "chatgpt_summary" | "manual";
};

type VoicePracticeLedger = {
  schemaVersion: 1;
  entries: VoicePracticeEntry[];
};
```

実装した純粋関数:

- `decodeVoicePracticeLedger()`
- `normalizeVoicePracticeLedger()`
- `normalizeVoicePracticeEntry()`
- `createEmptyVoicePracticeLedger()`

正規化方針:

- 未知フィールドは保存契約へ取り込まない
- `sourceText`、transcript、raw audioは正規化結果に残さない
- 必須文字列の空文字を拒否
- 配列は最大5件
- 配列内の空文字と文字列以外を拒否
- contextとsource kindは定義済み値だけを許可
- future schemaはダウングレードしない
- 不正entryが一件でも除外された場合、`canWrite: false`とする

## 5. CP3: APIなしの手動記録

対象:

- `app/ledger/page.tsx`
- `app/components/VoiceLedgerApp.tsx`
- `app/lib/voice-ledger-storage.ts`
- `app/lib/voice-ledger-storage.test.ts`

利用URL:

```text
/ledger
```

実装済みの入力:

- 練習日
- 場面
- 練習時間
- タイトル
- 要約
- 役立った表現
- 詰まった点
- 訂正
- 次回ミッション
- 自己メモ

実装済みの表示:

- 最近の履歴
- 場面、日付、タイトル、要約
- 次回ミッション
- `0 / 10`から`10 / 10`までの試用件数

保存動作:

- localStorageキーは`voice-practice-ledger`
- 読み込み時には書き戻さない
- 保存成功後だけReact stateを更新
- 保存容量エラー時は既存データと画面上の履歴を変更しない
- future-version、不正JSON、欠落entryがある場合は保存を停止
- 同じIDを保存する場合は重複させず先頭へ置く
- 自動削除と件数上限は設けていない

## 6. 現在の画面と既存機能

- `/`: 既存Interview/Sentence切り替え画面のまま
- `/ledger`: 新しい手動Voice Practice Ledger
- `/api/interview-materials`: 変更なし
- `/api/speaking-feedback`: 変更なし
- Groq Whisper経路: 変更なし
- `pronunciation-lab`: 変更なし

`/`から`/legacy`への移動はまだ行っていない。新台帳の実使用価値を確認する前に既存入口を変更しない方針。

## 7. プライバシーとデータ境界

現在の`/ledger`は完全手動で、解析APIを呼び出さない。

保存するもの:

- 本人が入力・確認した構造化記録
- 次回ミッション
- 任意の自己メモ

保存しないもの:

- ChatGPT Voiceの全文
- 貼り付け原文
- raw transcript
- raw audio
- 元仕事ログ
- 発音スコア
- 音響測定結果

未知フィールドを含むオブジェクトが渡されても、正規化後の保存データには含まれない。

## 8. 検証結果

自動検証:

- `npm test`: 23件成功
- `npm run typecheck`: 成功
- `npm run build`: 成功
- `git diff --check`: 成功
- production buildで`/ledger`を静的生成

単体テストで確認済み:

- 既存progressのv1からv2への移行
- progressの非破壊load
- progress future-version拒否
- Voice Ledgerの正常・破損・future fixture
- Voice Ledger正規化の冪等性
- 原文、transcript、raw audioの除去
- 空のledgerへの追加と再読込
- future-version、不正JSONへの保存拒否
- localStorage保存失敗時の既存データ維持

ブラウザ確認:

- APIを使わず5件を連続保存
- 保存後に`5 / 10`が表示される
- 再読込後も5件すべて表示される
- 最新記録が先頭に表示される
- デスクトップ表示を目視確認

未確認:

- モバイルviewportの自動スクリーンショットはlocalhostに対するブラウザ制限で未実施
- 実際のChatGPT Voice練習後に5〜10件を継続記録できるか
- 1件を60秒から2分以内で保存できるか

## 9. ここから行う実使用観察

実際のChatGPT Voice練習後に5〜10件記録し、次を確認する。

- 保存完了までの時間
- 必須項目が多すぎないか
- `usefulExpressions`、`stickingPoints`、`corrections`を毎回使うか
- `sessionMinutes`が必要か
- `nextMission`を次回に実際に再利用できたか
- Voiceとブラウザを往復しても記録を継続できるか
- 全文を保存しなくても履歴として十分か

この観察が終わるまでは、入力項目やschemaを大きく増やさない。

## 10. 次の判断候補

実使用で手動入力が成立した場合:

1. 編集
2. 削除
3. JSON export
4. 検索と場面フィルター
5. 直近の`nextMission`からVoice用プロンプトを決定的に生成

手動入力の負担が明確な問題だった場合のみ:

1. `/api/voice-session-analysis`の必要性を再評価
2. 解析対象と保存対象のプライバシー説明を確定
3. 最大1回のLLM呼び出しで編集可能な下書きを生成
4. API失敗時は原文を画面に残し、手動入力へ戻す

## 11. 今回まだ行わないこと

- LLM解析API
- ChatGPT履歴の自動取得
- transcriptや原文の永続保存
- 発音、流暢さ、沈黙の自動推定
- 発音スコアと音響測定
- 正規表現や機密語辞書による安全判定
- 既存`PracticeSession`との統合
- Interview/Sentence/Groq経路の変更
- `/`と`/legacy`の入れ替え
- 頻出表現集約、グラフ、復習キュー
- 新しい依存ライブラリ

## 12. 開発コマンド

```bash
cd speaking-practice
npm test
npm run typecheck
npm run build
npm run dev
```

ローカル確認:

```text
http://127.0.0.1:3000/ledger
```

## 13. 作業ツリー上の注意

CP1からCP3までの変更は、現時点の作業ツリーに存在する。`next-env.d.ts`には作業開始前からの生成ファイル変更があり、今回の実装対象として編集・整理していない。

リポジトリ直下のMalaysia News関連ファイル、Lazyweb関連ファイル、既存の未追跡docsには触れていない。
