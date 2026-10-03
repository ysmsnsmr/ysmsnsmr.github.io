# Meta Ads Personal Feed runbook

`meta-ads-updates/` の通常画面は、承認済み週次indexではなく `personal-feed.json` を表示する個人・同僚向け情報フィードです。収集・表示は火曜・金曜に自動で行い、人間レビューは公開条件ではありません。

## 自動収集するソース

- Meta Newsroom Product News RSS — Meta公式
- Meta Business SDK Releases（Node.js）— Meta公式GitHub公開API
- Social Media Today Facebook RSS（タイトルにMeta／Facebook／Instagram、かつタイトルまたは説明文に広告関連語）— 非公式・未確認
- Jon Loomer Digital RSS — 非公式・未確認
- Ads Uploader Blogの公開記事一覧 — 非公式。新着の見出し・日付・短い説明を収集し、運用解説も候補に含める
- Meta for Business News — Jon Loomer DigitalまたはSocial Media TodayのRSS本文から見つかったMeta公式記事だけを追加取得

Search Engine Land Meta RSSは、2026-08-30にGitHub ActionsでHTTP 403が繰り返し再現したため一時停止しています。安定した自動取得を確認できるまで再導入しません。

Social Media TodayはFacebook専用RSSを使います。タイトルにMeta／Facebook／Instagramの語があり、さらにタイトルまたはRSS説明に広告・キャンペーン・Advertiser・Advantage+などの語がある記事だけを掲載候補にします。Creator Studioのようなクリエイター運用の記事は除外します。これは記事の正確性を保証するものではなく、フィードの対象範囲を絞るための機械的な条件です。

Jon Loomerは `Meta Advertising` カテゴリだけでなく、タイトルまたはRSS説明に広告運用を示す具体的な語（Ads Manager、campaign、pixel、Conversions API、audienceなど）がある記事だけを掲載候補にします。カテゴリだけの周辺記事は除外します。この判定はsource-localの`relevanceRevision`で管理します。Jon LoomerまたはSocial Media Todayの掲載候補に `https://www.facebook.com/business/news/<slug>` 形式のリンクがある場合は、リンク先をMeta公式記事の候補として扱います。完全一致するHTTPSホストとパスだけを許可し、Meta公式ページ自身からcanonical URL、記事種別、タイトル、説明、発表日を検証できた候補だけを「Meta公式」として掲載します。非公式側の見出しや説明をMeta公式情報として転用しません。同じMeta公式URLを複数の非公式RSSが見つけた場合も、公式ページは1回だけ取得・掲載し、state内の`matchEvidence`に発見元のsource IDだけを併記します。

Meta公式ページはRSSや公開APIではなくHTMLから限定的なmetadataを読むため、アクセス制限や構造変更の影響を受けます。この追加取得だけが失敗した場合は該当候補を掲載せず、他のPersonal Feed収集は継続します。本文・失敗URL・例外本文は保存またはログ出力せず、許可ホスト、最大3回のredirect、1 MiBの応答上限、1 run最大20件を維持します。

各収集runはソースごとに `SOURCE_PIPELINE` を出力します。`mode=direct` は通常のRSS/API、`mode=discovered_official` は別ソース内の公式リンクから追加取得する経路です。`parsed` はRSS item、API releaseまたは公式HTML候補として読めた件数、`valid` は安全なURLと必要情報を持つ候補数、`matched` は今回の取得結果で掲載条件を満たした件数、`excluded` は直接ソースの有効候補のうち掲載条件で除外した件数です。`carried_forward` は今回の取得結果には現れなかったものの保存期間内のため前回stateから維持した件数、`retained` はそのcarry-forward分を含む保存期間内のstate件数です。発見経路では `discovered_links`、`attempted_links`、`rejected_links`、`deferred_links` も件数だけ出力します。`all_groups` 条件のソースには `SOURCE_MATCH_GROUP` も出力し、各キーワード群を満たした候補数を確認できます。たとえば直接ソースの `valid > 0` かつ `matched = 0` は、取得失敗ではなく現在の掲載条件に合う記事がなかったことを示します。

これらは件数・ソースID・パーサー版・レスポンスサイズだけの安全な運用ログです。タイトル、記事本文、RSS説明文、URL、認証情報、Cookieは出力しません。

非公式の文字付きラベルと画面上部の注意表示は削除しません。非公式ソースは早期検知の参考情報であり、Meta公式の見解を示すものではありません。公式情報で確認できない内容もあるため、重要な対応や判断には、複数の情報源や実環境で追加確認してください。

この一覧にない通常ソースは、HTTPSで公開され、RSSまたは安定した公開APIがあり、タイトル・URL・日付を安全に抽出できる場合を原則とします。Ads UploaderはRSSを公開していないため、ブログ一覧HTMLの可視記事カードだけを読む限定例外です。記事本文やスクリプト埋め込みデータは取得・保存しません。ログインが必要なページ、429やアクセス制限が確認されているページは通常ソースへ追加しません。Python/PHP/Java版SDK Releases APIは取得可能ですが、同じversionを重複表示するため、横断dedupeを実装するまで追加しません。

Ads Uploaderだけは追加ソースのアクセス拒否・HTML構造変更を他ソースへ波及させない `failurePolicy=isolate` とします。失敗したrunではAds Uploaderの既存記事を保存期間内だけ維持し、`SOURCE_PIPELINE` に `isolated_failure=true` を出します。失敗本文やURLはログへ出しません。新規導入・ルール変更のsource-local reseedは例外扱いせず、取得に成功するまで失敗とします。他の直接ソースのfail-closed境界は維持します。

## 通常運用

`Meta Ads Personal Feed twice-weekly collect` は火曜・金曜の `00:15 UTC`（通常08:15 MYT）に実行されます。すべての直接ソースの取得・形式検査・解析・契約検証が成功した場合にだけ、次の順序で2ファイルを更新します。

```text
安全な取得 → 形式検査・解析 → 鮮度判定 → 関連性判定
→ 掲載対象 / DROP判定 → state構築 → 英日表示データ生成 → feed検証 → 原子的公開
```

- `data/meta_ads_personal_feed_state.json` — URL、タイトル、日付、fingerprint、取得日時、内部の掲載可否、英語正本・日本語overlayの表示データキャッシュを保持する状態。`DROP`も後日の再評価用にここへ残す
- `meta-ads-updates/personal-feed.json` — GitHub Pagesで表示する公開フィード。内部で掲載対象と判定した記事だけを含める

生HTML、記事本文、画像、認証情報、Cookieは保存しません。必須の直接ソースで失敗したrunは既存の公開フィードを更新しません。Ads Uploader単独の失敗は上記の隔離運用です。

## 鮮度・関連性

発表日または最終更新日の新しい方が365日より前の記事は、表示データ生成の前に除外します。どちらの日付もない記事だけは初回観測日を使います。再観測日時で期限を延長することはありません。期限切れの記事はstate、公開feed、artifactに残しません。

Meta Newsroom Product News RSSは候補を広く取得し、広告・計測・API・事業導線に関する具体的な関連語がある記事を掲載対象にします。Business SDK releaseは常に掲載対象です。Jon LoomerとSocial Media Todayは、既存のソース固有候補条件を通過した記事を掲載対象にします。セキュリティ、訴訟、年齢制限など広告利用と関係しない候補は`DROP`へ置きます。`DROP`は公開せず、本文を保存せずにstateだけへ残します。

この判定は記事の重要度や、読者が取るべき対応を示すものではありません。掲載対象は、ソースと日付で並べて表示します。

### 人間確認済みURLの除外

明らかな誤掲載は `config/meta_ads_personal_feed_manual_exclusions.json` に記事のcanonical URLと理由を1件ずつ追加します。現在の一覧には人間が指定した17件を登録しています。これはURL単位の公開除外であり、同じ媒体の他記事や似た見出しを一括で消しません。Jevの判定が後日変わっても、一覧にあるURLは公開feedへ戻りません。元の判定結果と表示データはstateに保持し、除外された記事には新たなGroq生成を行いません。

一覧の変更後は `python3 scripts/meta_ads_personal_feed.py --apply-manual-exclusions-only` で既存stateから公開feedを再生成します。この操作は外部ソースやJev/Groqを呼ばず、stateを変更しません。続けて `python3 scripts/validate_meta_ads_personal_feed.py` を実行し、対象URLが公開feedにないことを確認します。除外を取り消す場合は該当行を一覧から削除して同じ再生成を行います。収集workflowも毎回この一覧を読み、公開と表示データ生成に同じ除外を適用します。

`workflow_dispatch`で`reseed_source_id`に設定済みのソースIDを指定すると、そのソースだけを現行の鮮度・関連性条件で再構築します。同じURLが引き続き採用される場合、`firstObservedAt`は維持されます。未登録IDはcollectorが失敗して既存公開物を保持します。

### relevanceRevisionを変更するPRのmerge条件

関連性契約を変更するPRは、**対象sourceごとのsource-local reseed成功がmerge条件**です。設定だけをmergeしてから定例収集でreseedを待つ運用は禁止します。各変更sourceについて、次をPR branch上で完了します。

1. `Meta Ads Personal Feed twice-weekly collect`をPR branchに対して手動実行し、`reseed_source_id`へ対象source IDだけを入れる。複数sourceを変更した場合は1 sourceずつ実行する。
2. runが成功し、botがstateと`personal-feed.json`を同じPR branchへcommitしたことを確認する。
3. PR headを更新後、CIの`--require-current-relevance-revisions`をPASSさせる。これはconfigの`relevanceRevision`と全sourceのstate値が一致しない限り失敗する。
4. PR本文またはreview記録に、変更source ID、reseed run URL、runが確認したPR head SHAを残す。

これにより、関連性ルールと保存済みstateの不一致を`main`へ持ち込めません。掲載対象ルールを実際に変更したPRは、対象ソースのsource-local reseedを成功させてからマージします。v5移行は既存の`ACTION`と`WATCH`をどちらも掲載対象として機械的に移すだけなので、source-local reseedは不要です。次の通常収集がv4 stateをv5へ移行します。

## 英語・日本語の短見出し・要約

収集時には、RSSの説明文またはSDK release notesを**そのrunの一時入力だけ**として、欠けているlocaleごとにGroqへ独立して要求します。英語は英語の短見出し・要約の2項目、日本語は日本語の短見出し・要約の2項目です。英日4項目を同時に生成するリクエストは使いません。保存は`英語/日本語 × 短見出し/要約`の4項目が独立単位です。再生成時にすでに成功した同じlocaleの項目を上書きせず、英語のいずれかが更新された場合だけ、それを入力とする日本語の2項目を再生成対象へ戻します。通常はGroqにStrict JSON Schema形式を要求し、schemaは2つの必須文字列と追加field禁止だけに限定します。Groqが安全に分類した`json_validate_failed`を返した**場合だけ**、同じlocaleへ`response_format`なしの定型プレーンテキストを1回要求します。このfallbackは`SHORT_HEADLINE:`と`SUMMARY:`の2行以外を受け付けず、JSONも受け付けません。返答は保存前にPythonが対象localeの項目完全一致、文字列型、空文字、文字数上限を検証します。文字数などの製品契約をGroq schemaへ移さず、片方のlocaleや項目の失敗が他の成功済み値を巻き込まないようにします。元の本文・説明文・release notes、Groq応答はstate、公開JSON、artifact、ログへ保存しません。

生成済みの表示データは記事内容のfingerprintに結び付けて再利用します。同じ内容には再課金しません。英語と日本語はlocaleごとに`machine`または`missing`を保持し、片方の生成失敗で成功済みのもう片方を消しません。内容が変わった記事、または未生成localeのある記事だけを新しい順に1 runあたり最大50件処理します。英語を再生成した場合、日本語は新しい英語に基づくoverlayとして再生成対象になります。

GroqのAPIキーがない、生成に失敗する、または出力契約に合わない場合でも、収集と公開は継続します。失敗したlocaleだけを`missing`として記録し、原文タイトルのまま表示できます。両localeが失敗した場合も同様です。表示データは事実確認や運用判断を代替しません。

各runは本文を出さずに `PRESENTATION` と `PRESENTATION_SOURCE` の行を出力します。ここでは記事候補数、記事単位の試行数、locale単位の試行・成功・失敗数、次回以降へ繰り越した数を確認します。`PRESENTATION_PATH` と `PRESENTATION_SOURCE_PATH` は `strict_json_schema`、`plaintext_fallback`、`legacy` ごとの成功件数だけを示します。失敗がある場合は、全体の `PRESENTATION_FAILURE` / `PRESENTATION_FALLBACK_FAILURE` とソース別の同名ログに安全な理由コードと件数を出します。

表示生成の失敗は、公開feedとは分離したstate内の `presentationRetryQueue` にlocale単位で隔離します。各エントリはsource、item fingerprint、locale、`failureCount`、`lastFailureAt`、`nextRetryAt`、安全な失敗コード、Groqが安全に返したprovider error code、`quarantined`だけを持ち、本文やGroq応答は保存しません。再試行間隔は1時間、2時間、4時間…と指数バックオフし、5回目の失敗で隔離して自動再試行を止めます。再試行時刻前のrunは外部モデルを呼ばず、公開feedはそのまま更新できます。

`json_validate_failed` と記録された隔離だけを再試行する場合は、daily collectのworkflow_dispatchで `retry_json_validate_failed=true` を指定します。これはその分類の隔離だけを解除し、他の原因の隔離は維持します。以前のv1 stateはprovider error codeを記録していないため、この操作で対象と推測しません。ログを確認済みの旧HTTP 400隔離を今回に限り回復させる場合は、`retry_json_validate_failed=true` と `retry_legacy_http_400=true` を**両方**指定します。後者だけの実行は拒否されます。原因を限定できない場合は、従来どおり `retry_failed=true` で全キューを手動解除できますが、これは最後の手段です。

- `api_key_unavailable` — APIキーが未設定
- `http_client_error` / `http_server_error` — Groq側のHTTP 4xx / 5xx 応答
- `network_error` — 接続・タイムアウトなどの通信失敗
- `response_decode_error` / `response_invalid_json` — 応答を文字列またはJSONとして読めない
- `response_missing_content` / `response_invalid_shape` — 応答に必要な生成データがない、または契約外
- `short_headline_invalid` / `summary_invalid` — 生成文が空、文字列でない、または長さ上限を超過
- `unknown` — 上記に安全に分類できない失敗

理由コードは調査の入口であり、記事本文やGroqの応答内容を出すものではありません。タイトル、RSS説明文、release notes、Groqの応答や例外本文はログに出しません。

公開中の日本語`missing`を補完する場合は、手動workflow `Meta Ads Personal Feed Japanese presentation backfill` を使います。最初は `presentation_limit=1` で実行し、ログの `PUBLISHED_JA_BACKFILL` にある `completed` / `headlineOnly` / `failed` を確認してから、必要に応じて最大50件まで増やします。対象はその時点の公開feedに載る記事だけです。既存stateの英語要約がある記事は英語見出し・要約から日本語2項目を作り、英語要約がない記事は原文タイトルから日本語見出しだけを作ります。後者では要約を推測して埋めません。RSS/APIやJevは呼ばず、取得日時と掲載記事の並びを保持します。手動実行は公開中の日本語欠落だけに限定して隔離中の項目も再試行し、失敗回数は既存の隔離キューで記録します。記事がすでに公開feedから外れている場合は対象になりません。

## 画面の使い方

一覧は、Meta公式、Meta Business SDK Releases、非公式の3グループで表示します。記事の掲載順は発表日または最終更新日の新しい順です。内部では`included`と`DROP`だけを保持し、`DROP`は公開せず後日の再評価用に状態データへ残します。各カードは短見出し、ソース区分、発表日・最終更新日を表示します。`詳細を見る`を選ぶと、同じ公開feedから該当記事を読み込み、短見出し、日本語要約、原文タイトル、対象プラットフォーム、元記事リンクを表示します。

日本語要約が未生成の間も詳細画面は利用でき、原文タイトルと元記事リンクを表示します。一覧のソース・区分・キーワード条件は、詳細画面から一覧へ戻ったときに維持されます。保存期間の終了などで記事が消えたURLは、安全な「記事が見つかりません」画面になります。

初回成功runは、各RSS/APIの現在の項目をbaselineとして表示します。これは「その日に発表された」という意味ではなく、初回収集時点でソースに掲載されていたことを示します。

## 操作と停止

リポジトリ変数 `META_ADS_TRACKER_COLLECT_ENABLED` を `false` にすると、checkout・依存関係インストール・外部アクセス・commit・artifact uploadの前に正常終了します。`true` または未設定で有効です。それ以外の値は設定ミスとして失敗します。

手動で初回取得または再確認する場合は、Actionsの `Meta Ads Personal Feed daily collect` を `main` に対して実行します。成功後はartifact `meta-ads-personal-feed-<run id>` と公開画面を確認してください。

日本語表示の呼び出しは、リポジトリ変数 `META_ADS_PERSONAL_FEED_JA_ENABLED` で制御します。未設定または `true` で有効、`false` で停止します。`META_ADS_PERSONAL_FEED_GROQ_MODEL` は使用モデルを上書きできます。未設定時は `openai/gpt-oss-120b` を使います。値が `true` / `false` 以外の場合は、設定ミスとしてcollectorを失敗させます。

## 旧Trackerの扱い

weekly assemble、Friday preflight、secondary shadow、official canaryの定期実行は停止しています。既存の候補、週次artifact、recovery artifact、承認記録、過去の `latest.json` は履歴として残しますが、Personal Feedの表示や更新には使いません。必要な場合だけ手動実行してください。
