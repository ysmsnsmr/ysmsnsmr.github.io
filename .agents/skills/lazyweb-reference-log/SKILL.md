---
name: lazyweb-reference-log
description: "Create one article-specific Lazyweb Reference Log from article.md and lazyweb-research.md using the repository template, with a deterministic validator, exact URL provenance checks, hashed run manifests, atomic no-overwrite publication, minimal logging, and a final PROCESSED marker. Use for scheduled processing of the oldest eligible lazyweb/inbox folder, a manually specified single input folder, failure-fixture validation, or review and updates of this workflow without running it."
---

# Lazyweb Reference Log

プロジェクトルートからの相対パスだけを使い、1回につき最大1入力のReference Logを安全に作成する。

## 不変条件

- プロジェクトルートで作業する。skill内や生成物へ絶対パスを固定しない。
- 次の相対パスを使う。
  - テンプレート: `lazyweb/template/reference-log-template.md`
  - 入力: `lazyweb/inbox/<YYYY-MM-DD-slug>/`
  - 出力: `lazyweb/output/`
  - ログ: `lazyweb/logs/<入力フォルダ名>/`
  - 実行manifest: `lazyweb/logs/<入力フォルダ名>/<ログ名の拡張子を除いた部分>.manifest.json`
  - quarantine: `lazyweb/quarantine/<入力フォルダ名>/`
- Web検索、ブラウザー、MCP、外部URL取得、画像生成を行わない。
- 選択した入力の `article.md` と `lazyweb-research.md`、およびテンプレートだけを内容資料として使う。
- `READY`を変更または削除しない。
- 既存の正式出力、既存の一時出力、既存ログ、既存の`PROCESSED`を上書きまたは削除しない。
- 失敗時に残った一時出力を自動削除しない。
- skillの作成、更新、内容確認、構造検証を依頼されているだけなら実処理を開始しない。`lazyweb/inbox/`内の本文を読まず、`lazyweb/output/`、`lazyweb/logs/`、`PROCESSED`を作成・変更しない。

## 決定的な実行境界

- LLMは対象選定後のReference Log draft作成だけを担当する。
- 状態判定、URL検証、Safety Review、公開可否、原子的確定、実行ログ、manifest、`PROCESSED`作成は `scripts/lazyweb_reference_log.py` にだけ担当させる。
- LLMが正式出力、実行ログ、manifest、`PROCESSED`を直接作成・変更しない。
- 実行前に次を使い、返されたJSONが `status: ready` の場合だけdraftを作る。

```bash
python3 .agents/skills/lazyweb-reference-log/scripts/lazyweb_reference_log.py \
  --project-root . prepare \
  --input-folder lazyweb/inbox/<入力フォルダ名>
```

- draftを、返された `temporary_output` へ生成する。
- 正式化の判断は次だけに任せる。`prepare`が返した `context_sha256` を変更せず渡す。

```bash
python3 .agents/skills/lazyweb-reference-log/scripts/lazyweb_reference_log.py \
  --project-root . finalize \
  --input-folder lazyweb/inbox/<入力フォルダ名> \
  --temporary-output <prepareが返した相対パス> \
  --expected-context-sha256 <prepareが返した値>
```

- `prepare`後に入力、template、skillのいずれかが変わった場合、validatorは公開せず `processing_failed` にする。
- validatorの終了コードとJSONを結果として扱う。LLMの自己判定で成功へ変更しない。

## 実行モードと対象選定

### Scheduled実行

1. `lazyweb/inbox/`直下のフォルダだけを調べる。
2. 次をすべて満たすフォルダだけを対象候補にする。
   - `READY`が存在する。
   - `PROCESSED`が存在しない。
   - `article.md`が存在する。
   - `lazyweb-research.md`が存在する。
   - `lazyweb/template/reference-log-template.md`が存在する。
3. フォルダ名をバイト順の昇順で並べ、先頭の1件だけを選ぶ。
4. 選んだ1件を明示入力としてvalidatorの`prepare`へ渡す。
5. 候補がなければ何も生成せず、no-opとして報告する。入力別ログの保存先を決められないためログも作らない。

### 手動実行

1. 明示された `lazyweb/inbox/<入力フォルダ名>/` の1件だけを扱う。別フォルダへ自動フォールバックしない。
2. 入力が `lazyweb/inbox/` の直下にない場合は処理せず、ユーザーへ停止理由を報告する。
3. validatorの`prepare`に明示入力を渡す。validatorは状態を次の優先順で検査し、停止時は可能な限りその入力の実行ログとmanifestだけを残す。
   - `PROCESSED`あり: `already_processed`
   - `READY`なし: `processing_failed`、停止理由を `READY missing` とする。
   - `article.md`なし: `missing_article`
   - `lazyweb-research.md`なし: `missing_research`
   - テンプレートなし: `missing_template`

Scheduled選択後または処理中に状態が変わった場合も、同じ検査と停止規則を使う。

## 名前と時刻

1. 入力フォルダ名が `YYYY-MM-DD-<slug>` 形式で、`<slug>`が空でないことを確認する。
2. 先頭の `YYYY-MM-DD-` だけを除いた文字列をslugとしてそのまま使う。推測、正規化、修正をしない。
3. 形式が不正なら `processing_failed` とし、停止理由を `invalid input folder name` とする。
4. タイムゾーンを `Asia/Kuala_Lumpur` に固定する。
5. 本文中の時刻は秒までのISO 8601 `YYYY-MM-DDTHH:MM:SS+08:00` とする。
6. 同じ開始時刻から次を作る。
   - 一時出力時刻: `YYYYMMDDTHHMMSS`
   - ログ名時刻: `YYYY-MM-DD-HHMMSS`
7. 同一秒のログ名が既にある場合は上書きせず、`-02`、`-03`のような連番を付けて未使用名を選ぶ。

正式出力:

`lazyweb/output/lazyweb-reference-log-<slug>.md`

一時出力:

`lazyweb/output/.tmp-lazyweb-reference-log-<slug>-<YYYYMMDDTHHMMSS>.md`

実行ログ:

`lazyweb/logs/<入力フォルダ名>/<YYYY-MM-DD-HHMMSS>.md`

実行manifest:

`lazyweb/logs/<入力フォルダ名>/<YYYY-MM-DD-HHMMSS>.manifest.json`

## 事前検査

本文を生成する前にvalidatorの`prepare`で次の順に検査する。

1. 入力ファイル、テンプレート、`READY`、`PROCESSED`を再確認する。
2. 正式出力が既に存在する場合:
   - `blocked_output_exists` のログとmanifestだけを作る。
   - 一時出力と`PROCESSED`を作らない。
   - 正式出力を読んで再利用、比較、変更しない。
3. `lazyweb/output/.tmp-lazyweb-reference-log-<slug>-*.md` に一致する既存ファイルが1つでもある場合:
   - `stale_temp_exists` のログとmanifestだけを作る。
   - 既存一時出力を読まず、削除せず、変更しない。
   - 新しい一時出力と`PROCESSED`を作らない。
4. 出力ディレクトリとログディレクトリへ安全に書けることを確認する。既存ファイルは変更しない。

正式出力の存在確認を既存一時出力の確認より先に行い、両方ある場合は `blocked_output_exists` とする。

## 入力URL集合

1. 選択した `article.md` と `lazyweb-research.md` に文字列として存在するURLだけを抽出する。
2. URLは出現した文字列を正確に保持する。推測、補完、正規化、リダイレクト解決、クエリ削除、末尾スラッシュ変更、URLデコードをしない。
3. 画像URL、署名付きURL、認証情報を含むURL、tokenを含むURL、MCP URLは採用しない。判別できなければ採用しない。
4. `Research Items` へ採用するURLは、入力URL集合に完全一致する通常の参照ページURLだけにする。
5. テンプレート内の例示URLは入力URL集合に完全一致しない限り出力へコピーしない。
6. URL値そのものを実行ログへ書かない。

## Reference Logを作る

1. validatorの`prepare`が `ready` を返したことを確認する。ここから一時出力のdraft作成だけをLLMが担当する。
2. テンプレートをスキーマとして読み、validatorが指定した一時出力へ直接生成する。
3. テンプレートの次の構造を同じ順序で維持する。
   - ATX見出しのレベル、見出し文言、並び順
   - セクション内の項目名と並び順
   - `Research Items` 表の列名、列順、配置
   - テンプレートにある表のデータ行数と `No` の順序
4. テンプレートの例示データ、URL、記事固有の記述を自動的に引き継がない。構造と項目を維持し、今回の入力で根拠づけられる内容へ置き換える。
5. 表のURL欄には採用した入力URLを出現順で置く。同じURLの不要な重複を避ける。行が余る場合はURL欄を空欄にし、根拠のない内容を埋めない。
6. 入力にURLがない場合はURL欄を空欄にし、関連内容を `要確認` とする。URLを作らない。
7. 各行で次を分離する。
   - `観察メモ`: 入力から確認できる観察事実だけを書く。必要なら `観察:` と明示する。
   - `抽出した抽象パターン`: 特定の表現をコピーせず、一般化したパターンだけを書く。
   - `使わない要素`: コピーを避ける対象を書く。
   - `最終案への反映メモ`: デザイン提案だけを書き、`提案:` と明示する。
8. 共通パターンでも観察事実と提案を混ぜない。根拠不足や不明事項は `要確認` とする。
9. 参照元の文章、画像、UI、ロゴ、固有レイアウト、ブランド色、固有文言をコピーしない。
10. 記事内容に合わせて、相互に異なるオリジナルのヘッダー画像方向性をちょうど3案作る。
11. 各案で次を明記する。
    - 実在ブランド、媒体、店舗、人物、アプリ、UIを再現しない。
    - 読める文字や数字を画像内へ含めない。
    - タイトル等は画像外で重ねられる余白として設計する。
12. スクリーンショット、参照画像、画像ファイル、画像URL、署名付きURLを保存または埋め込まない。
13. token、認証情報、MCP URL、個人設定値を含めない。

## Safety Review

一時出力の完成後、正式化前にvalidatorの`finalize`が独立して全項目を検証する。LLMが検証結果を代替しない。

1. テンプレート構造が維持されている。
2. 出力内の全URLが入力URL集合のいずれかと完全一致し、入力にないURLがない。
3. 採用URLの文字列が変更されていない。
4. 観察事実とデザイン提案が区別されている。
5. 根拠不足や不明事項が `要確認` になっている。
6. ロゴ、実在UI、固有レイアウト、実在ブランド・媒体・店舗等のコピーを提案していない。
7. スクリーンショット、参照画像、画像ファイル、画像URLを保存または埋め込んでいない。
8. 署名付きURLを保存していない。
9. token、認証情報、MCP URL、個人設定値を含めていない。
10. 読める文字や数字を生成画像へ入れる提案がない。
11. 正式出力が依然として存在せず、既存出力を上書きしない。
12. 3案すべてが記事内容に結びつき、互いに異なり、抽象パターンだけを使っている。

テンプレート自身にあるURLや例示内容も例外扱いしない。1項目でも不合格、または判定不能なら正式化しない。`safety_review_failed` のログを残し、`READY`と一時出力を残し、`PROCESSED`を作らない。

## 原子的に確定する

次の処理はvalidatorだけが行う。

1. Safety Review合格後、正式出力が存在しないことを直前に再確認する。
2. 同じ `lazyweb/output/` 内で、上書きを禁止する原子的なpublishを行う。
   - no-replaceの原子的renameを利用できる場合はそれを使う。
   - 利用できない場合は、同一ファイルシステム上で一時出力から正式名へのハードリンクを原子的に作る。正式名が既にあればリンク作成を失敗させる。リンク成功後だけ一時名を削除する。
   - 通常の上書き可能なrenameや `mv -f` を使わない。
3. 競合で正式出力が先に作られた場合は、既存正式出力へ触れず、現在の一時出力を残して `blocked_output_exists` とする。`PROCESSED`を作らない。
4. 正式化後に完了ログまたは`PROCESSED`作成が失敗した場合:
   - この実行が作った正式出力と同一であることをinodeまたは事前計算したハッシュで確認する。
   - 安全に確認でき、元の一時名が未使用なら、正式出力を元の一時名へ原子的に戻して正式名を残さない。
   - 確認できなければ既存物を削除せず、`processing_failed` として手動対応が必要だと報告する。
   - `READY`を残し、`PROCESSED`を作らない。

## 実行ログ

validatorは停止または完了ごとに、選択した入力専用の新規ログを1つ作る。ログには次のキーだけをこの順で記録する。

```markdown
status: <status>
started_at: <ISO 8601 +08:00>
finished_at: <ISO 8601 +08:00>
input_folder: lazyweb/inbox/<入力フォルダ名>
template: lazyweb/template/reference-log-template.md
temporary_output: <相対パス、未作成なら not_created>
final_output: lazyweb/output/<正式出力名>
url_count: <Research Itemsへ採用したURL件数。未生成なら0>
safety_review: <pass、fail、または not_run>
missing_or_stop_reason: <不足項目または停止理由。なければ none>
```

次をログへ書かない。

- `article.md` または `lazyweb-research.md` の本文や長い抜粋
- URL値、画像URL、署名付きURL、MCP URL
- スクリーンショット、参照画像、画像データ
- 認証情報、token、個人設定値

使用可能なstatus:

- `success`
- `missing_article`
- `missing_research`
- `missing_template`
- `blocked_output_exists`
- `stale_temp_exists`
- `safety_review_failed`
- `processing_failed`
- `already_processed`

ログ作成自体が失敗した場合は成功扱いにしない。

## 実行manifest

- 各実行ログと同じstemの`.manifest.json`を新規作成し、既存manifestを上書きしない。
- `schema_version: 1`、status、開始・終了時刻、相対パス、URL件数、12項目のSafety Review結果、ログとの対応を記録する。
- 次のSHA-256を記録する。存在しない成果物は `sha256: null` とする。
  - `article.md`
  - `lazyweb-research.md`
  - `lazyweb/template/reference-log-template.md`
  - `.agents/skills/lazyweb-reference-log/SKILL.md`
  - 正式出力
- 既存正式出力との衝突時は既存ファイルを読まず、outputを `state: existing_not_read`、`sha256: null` とする。
- URL値、本文、画像、認証情報、token、MCP URL、個人設定値をmanifestへ書かない。
- `prepare`の `context_sha256` は入力2ファイル、template、skillの各SHA-256から決定的に作る。`finalize`で再計算して完全一致を強制する。

## PROCESSEDを最後に作る

validatorは正式出力の安全な確定、成功manifest、`success`ログの作成がすべて成功した後だけ、入力フォルダ内へ `PROCESSED` を新規作成する。既存ファイルは上書きしない。

内容を次の3行だけにする。

```markdown
processed_at: <ISO 8601 +08:00>
output: lazyweb/output/<正式出力名>
run_log: lazyweb/logs/<入力フォルダ名>/<ログ名>
```

最後に、正式出力、成功ログ、`PROCESSED`の存在と相互参照を確認する。成功時も `READY` は残す。

## Quarantineと手動再実行

stale一時ファイルの隔離、最低90日の保存、削除条件、失敗修正後の手動再実行は [references/quarantine-and-retry.md](references/quarantine-and-retry.md) を最初から最後まで読んで従う。通常処理ではquarantineを自動実行しない。

## Fixture検証

skillまたはvalidatorを更新した場合は、本番入力を使わず次を実行する。

```bash
PYTHONPYCACHEPREFIX=/tmp/lazyweb-reference-log-pycache \
python3 .agents/skills/lazyweb-reference-log/tests/test_fixtures.py
```

成功、入力不足、不正URL、出力衝突、安全性違反の5件すべてが通らなければ変更を完了扱いにしない。

## 失敗時の共通規則

- 正式化前の失敗では正式出力を作らない。
- `PROCESSED`を作らない。
- `READY`を残す。
- 失敗ログと対応manifestだけを新規作成する。
- 残った一時出力を自動削除しない。
- 既存ファイルを修復、整理、削除しない。
