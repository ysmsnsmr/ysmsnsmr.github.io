# Meta Ads Personal Feed runbook

`meta-ads-updates/` の通常画面は、承認済み週次indexではなく `personal-feed.json` を表示する個人・同僚向け情報フィードです。収集・表示は火曜・金曜に自動で行い、人間レビューは公開条件ではありません。

## 自動収集するソース

- Meta Newsroom Product News RSS — Meta公式
- Social Media Today Facebook RSS（タイトルにMeta／Facebook／Instagram、かつタイトルまたは説明文に広告関連語）— 非公式・未確認
- Jon Loomer Digital RSS — 非公式・未確認
- Ads Uploader Blogの公開記事一覧 — 非公式。新着の見出し・日付・短い説明を収集し、運用解説も候補に含める
- Meta for Business News — Jon Loomer DigitalまたはSocial Media TodayのRSS本文・記事ページから見つかったMeta公式記事だけを追加取得
- Meta Business Help Center — 同じ2媒体から見つかった `/business/help/数字` 形式の公式資料を追加取得
- Meta for Developers Blog — 同じ2媒体のRSS本文・記事ページから見つかった `developers.facebook.com/blog/post/YYYY/MM/DD/<slug>/` 形式だけを追加取得。Ads Uploader記事ページの巡回は行わない

Search Engine Land Meta RSSは、2026-08-30にGitHub ActionsでHTTP 403が繰り返し再現したため一時停止しています。安定した自動取得を確認できるまで再導入しません。

Meta Business SDK Releases（Node.js）の取得は利用頻度が低いため停止中です。設定の `fetchEnabled: false` により通常収集でAPIへアクセスせず、再seedも受け付けません。取得済み項目は従来の鮮度・保存期間に従って保持し、期限後は表示されなくなります。実行ログの `fetch_enabled=false` で停止状態を確認できます。

Social Media TodayはFacebook専用RSSを使います。タイトルにMeta／Facebook／Instagramの語があり、さらにタイトルまたはRSS説明に広告・キャンペーン・Advertiser・Advantage+などの語がある記事だけを掲載候補にします。Creator Studioのようなクリエイター運用の記事は除外します。これは記事の正確性を保証するものではなく、フィードの対象範囲を絞るための機械的な条件です。

Jon Loomerは `Meta Advertising` カテゴリだけでなく、タイトルまたはRSS説明に広告運用を示す具体的な語（Ads Manager、campaign、pixel、Conversions API、audienceなど）がある記事だけを掲載候補にします。カテゴリだけの周辺記事は除外します。この判定はsource-localの`relevanceRevision`で管理します。Jon LoomerまたはSocial Media Todayの新鮮なRSS記事について、RSS本文に加え、発見元URLが人間確認済みの除外一覧にない場合だけ記事ページの本文段落から公式リンクを探します。記事ページの取得は各媒体1 run最大10件、5秒・1 MiB・redirect禁止の上限付きです。取得・解析失敗はリンク発見だけを諦め、通常の収集を止めません。記事ページ本文は保存せず、ナビゲーションや関連記事カードのリンクは探索しません。Jevによる発見元記事の掲載判定は、このリンク発見を妨げません。完全一致するHTTPSホストとBusiness News／Developer Blog／数値IDのBusiness Helpだけを候補にします。Meta公式ページ自身のURL、タイトル、説明等を検証し、関連性判定を通過したものを「Meta公式」として掲載します。Helpはcanonicalとog:urlの両方の一致を要求します。非公式側の見出しや説明をMeta公式情報として転用しません。同じMeta公式URLを複数の非公式記事が見つけた場合も、公式ページを1回だけ取得・掲載し、state内の`matchEvidence`に発見元のsource IDだけを併記します。

Meta公式ページはRSSや公開APIではなくHTMLから限定的なmetadataを読むため、アクセス制限や構造変更の影響を受けます。この追加取得だけが失敗した場合は該当候補を掲載せず、他のPersonal Feed収集は継続します。本文・失敗URL・例外本文は保存またはログ出力せず、許可ホスト、最大3回のredirect、1 MiBの応答上限、1 run最大20件を維持します。

記事ページからのリンク発見を一時停止する場合は、repository variable `META_ADS_ARTICLE_PAGE_DISCOVERY_ENABLED=false` を設定します。RSS本文からの既存のリンク発見と公式ページ自身の検証は続きます。手動CLIでは `--disable-article-page-discovery` を使えます。最初の2回のscheduled runで記事ページ取得の成功・拒否・新規リンク数と収集時間を確認し、増分がなく失敗や遅延が目立つ場合はこの経路を停止します。

記事ページの探索は未試行を優先し、以降は最も以前に試行した記事を優先します。試行の成否にかかわらず順番を進め、stateには記事キーのハッシュと試行時刻だけを保存します。上限で見送った記事は、引き続きRSSに残り鮮度・人間除外の条件を満たす間、後続runで探索されます。RSSから消えた記事や収集run自体が失敗した場合の探索は保証されません。Business Newsの日付は `article:published_time`、本文領域、またはMetaの `FB4BResponsiveMainContent` 内で公式タイトルと一致する見出しの直前にあるカテゴリ・日付を使用します。不正・不一致の場合は昇格しません。日付がないBusiness NewsとBusiness Helpは発表日・更新日を空のまま保持し、初回発見日を表示・鮮度判定に用います。発見日は公開日や更新日を意味せず、古い資料を新発表と誤認しないよう注意します。

非公式記事の詳細では、記事本文段落で見つけたMeta公式URLを最大10件、参考リンクとして表示できます。対象は `www.facebook.com/business/help/<数字>`、既存のBusiness News記事、Developer Blog記事パスだけです。HelpはURLのホスト・パス形式だけを確認し、ページの内容・公開日・到達可能性を保証しません。ニュースとして昇格させず、元記事も非公式のままです。Business News／Developer Blogは既存の公式ページ検証に成功したURLだけを参考リンクへ含めます。リンク先の本文や非公式記事本文は保存しません。参考リンクのURLのみstateと公開feedに保存し、記事が再取得できないrunでは既存の参考リンクを保持します。`META_ADS_ARTICLE_PAGE_DISCOVERY_ENABLED=false` では新規参考リンクの探索も止まります。

Developer Blog発見経路も発見元URLの人間除外を先に適用します。完全一致の `developers.facebook.com` ホストと日付付き記事パスに限定し、取得したページ自身のcanonicalリンクと`og:url`、見出し、説明、可視の日付（URLの日付と一致）を検証します。`og:type=website`のページもあるため、Business News用の`og:type=article`条件を流用しません。記事のMeta広告との関連性は通常のJev掲載判定に委ねます。Developer Blogの追加取得は1 run最大10件・1記事から最大5リンク・最大2回のredirectとし、個別候補の取得・検証失敗は他ソースへ波及させません。`SOURCE_PIPELINE`でこのsource IDの`attempted_links`、`rejected_links`、`retained`を確認し、不要な昇格や取得不能が続く場合はこの独立source設定と処理を戻します。

各収集runはソースごとに `SOURCE_PIPELINE` を出力します。`mode=direct` は通常のRSS/API、`mode=discovered_official` は別ソース内の公式リンクから追加取得する経路です。`parsed` はRSS item、API releaseまたは公式HTML候補として読めた件数、`valid` は安全なURLと必要情報を持つ候補数、`matched` は今回の取得結果で掲載条件を満たした件数、`excluded` は直接ソースの有効候補のうち掲載条件で除外した件数です。`carried_forward` は今回の取得結果には現れなかったものの保存期間内のため前回stateから維持した件数、`retained` はそのcarry-forward分を含む保存期間内のstate件数です。記事ページ経路の `article_pages_attempted`、`article_pages_fetched`、`article_pages_rejected`、`article_pages_deferred`、`article_page_links` は件数のみです。発見経路では `discovered_links`、`attempted_links`、`rejected_links`、`deferred_links` も件数だけ出力します。`all_groups` 条件のソースには `SOURCE_MATCH_GROUP` も出力し、各キーワード群を満たした候補数を確認できます。たとえば直接ソースの `valid > 0` かつ `matched = 0` は、取得失敗ではなく現在の掲載条件に合う記事がなかったことを示します。

これらは件数・ソースID・パーサー版・レスポンスサイズだけの安全な運用ログです。タイトル、記事本文、RSS説明文、URL、認証情報、Cookieは出力しません。

非公式の文字付きラベルと画面上部の注意表示は削除しません。非公式ソースは早期検知の参考情報であり、Meta公式の見解を示すものではありません。公式情報で確認できない内容もあるため、重要な対応や判断には、複数の情報源や実環境で追加確認してください。

この一覧にない通常ソースは、HTTPSで公開され、RSSまたは安定した公開APIがあり、タイトル・URL・日付を安全に抽出できる場合を原則とします。Ads UploaderはRSSを公開していないため、ブログ一覧HTMLの可視記事カードだけを読む限定例外です。Ads Uploaderの記事本文やスクリプト埋め込みデータは取得・保存しません。Jon Loomer／Social Media Todayの記事ページは上記の公式リンク発見だけに使い、本文を保存・Groq/Jevへ送信しません。ログインが必要なページ、429やアクセス制限が確認されているページは通常ソースへ追加しません。Python/PHP/Java版SDK Releases APIは取得可能ですが、同じversionを重複表示するため、横断dedupeを実装するまで追加しません。

Ads Uploaderだけは追加ソースのアクセス拒否・HTML構造変更を他ソースへ波及させない `failurePolicy=isolate` とします。失敗したrunではAds Uploaderの既存記事を保存期間内だけ維持し、`SOURCE_PIPELINE` に `isolated_failure=true` を出します。失敗本文やURLはログへ出しません。新規導入・ルール変更のsource-local reseedは例外扱いせず、取得に成功するまで失敗とします。他の直接ソースのfail-closed境界は維持します。

## 通常運用

`Meta Ads Personal Feed twice-weekly collect` は月曜・木曜の `16:17 UTC`（火曜・金曜00:17 MYT）に起動するよう設定されています。GitHub Actionsの定期実行には遅延があり、サイトへの反映は収集とGitHub Pagesの公開処理が完了した後です。すべての直接ソースの取得・形式検査・解析・契約検証が成功した場合にだけ、次の順序で2ファイルを更新します。

```text
安全な取得 → 形式検査・解析 → 鮮度判定 → 関連性判定
→ 掲載対象 / DROP判定 → state構築 → 英日表示データ生成 → feed検証 → 原子的公開
```

- `data/meta_ads_personal_feed_state.json` — URL、タイトル、日付、fingerprint、取得日時、内部の掲載可否、英語正本・日本語overlayの表示データキャッシュを保持する状態。`DROP`も後日の再評価用にここへ残す
- `meta-ads-updates/personal-feed.json` — GitHub Pagesで表示する公開フィード。内部で掲載対象と判定した記事だけを含める

生HTML、記事本文、画像、認証情報、Cookieは保存しません。必須の直接ソースで失敗したrunは既存の公開フィードを更新しません。Ads Uploader単独の失敗は上記の隔離運用です。

## 鮮度・関連性

発表日または最終更新日の新しい方が365日より前の記事は、表示データ生成の前に除外します。どちらの日付もない記事だけは初回観測日を使います。再観測日時で期限を延長することはありません。期限切れの記事はstate、公開feed、artifactに残しません。

Meta Newsroom Product News RSSは候補を広く取得し、広告・計測・API・事業導線に関する具体的な関連語がある記事を掲載対象にします。過去に取得したBusiness SDK releaseは掲載対象として保持します。Jon LoomerとSocial Media Todayは、既存のソース固有候補条件を通過した記事を掲載対象にします。セキュリティ、訴訟、年齢制限など広告利用と関係しない候補は`DROP`へ置きます。`DROP`は公開せず、本文を保存せずにstateだけへ残します。

この判定は記事の重要度や、読者が取るべき対応を示すものではありません。掲載対象は、ソースと日付で並べて表示します。

### 人間確認済みURLの除外

明らかな誤掲載は `config/meta_ads_personal_feed_manual_exclusions.json` に記事のcanonical URLと理由を1件ずつ追加します。現在の一覧には人間が指定した26件を登録しています。これはURL単位の公開除外であり、同じ媒体の他記事や似た見出しを一括で消しません。Jevの判定が後日変わっても、一覧にあるURLは公開feedへ戻りません。次の収集runからは、除外された非公式記事を公式リンクの発見元にも使いません。同じ公式URLが別の非除外記事から見つかれば、そちらからの発見は維持します。元の判定結果と表示データはstateに保持し、除外された記事には新たなGroq生成を行いません。

一覧の変更後は `python3 scripts/meta_ads_personal_feed.py --apply-manual-exclusions-only` で既存stateから公開feedを再生成します。この操作は外部ソースやJev/Groqを呼ばず、stateを変更しません。続けて `python3 scripts/validate_meta_ads_personal_feed.py` を実行し、対象URLが公開feedにないことを確認します。除外を取り消す場合は該当行を一覧から削除して同じ再生成を行います。収集workflowも毎回この一覧を読み、公開と表示データ生成に同じ除外を適用します。発見元の除外は次の収集runに適用され、過去に検証済みでstateに残る公式記事を遡って削除するものではありません。

`workflow_dispatch`で`reseed_source_id`に設定済みのソースIDを指定すると、そのソースだけを現行の鮮度・関連性条件で再構築します。同じURLが引き続き採用される場合、`firstObservedAt`は維持されます。未登録IDはcollectorが失敗して既存公開物を保持します。

### relevanceRevisionを変更するPRのmerge条件

関連性契約を変更するPRは、**対象sourceごとのsource-local reseed成功がmerge条件**です。設定だけをmergeしてから定例収集でreseedを待つ運用は禁止します。各変更sourceについて、次をPR branch上で完了します。

1. `Meta Ads Personal Feed twice-weekly collect`をPR branchに対して手動実行し、`reseed_source_id`へ対象source IDだけを入れる。複数sourceを変更した場合は1 sourceずつ実行する。
2. runが成功し、botがstateと`personal-feed.json`を同じPR branchへcommitしたことを確認する。
3. PR headを更新後、CIの`--require-current-relevance-revisions`をPASSさせる。これはconfigの`relevanceRevision`と全sourceのstate値が一致しない限り失敗する。
4. PR本文またはreview記録に、変更source ID、reseed run URL、runが確認したPR head SHAを残す。

これにより、関連性ルールと保存済みstateの不一致を`main`へ持ち込めません。掲載対象ルールを実際に変更したPRは、対象ソースのsource-local reseedを成功させてからマージします。v5移行は既存の`ACTION`と`WATCH`をどちらも掲載対象として機械的に移すだけなので、source-local reseedは不要です。次の通常収集がv4 stateをv5へ移行します。

## 英語・日本語の短見出し・要約

収集時には、RSSの説明文またはSDK release notesを**そのrunの一時入力だけ**として、欠けているlocaleごとにOpenAIの`gpt-6-luna`へ独立して要求します。英語は英語の短見出し・要約の2項目、日本語は日本語の短見出し・要約の2項目です。英日4項目を同時に生成するリクエストは使いません。保存は`英語/日本語 × 短見出し/要約`の4項目が独立単位です。`machine`・`reviewed`の項目はモデル切替や兄弟localeの補完を理由に上書きせず、`missing`の項目だけ生成します。通常生成では最小のStrict JSON Schema形式を要求し、schemaは2つの必須文字列と追加field禁止だけに限定します。返答は保存前にPythonが対象localeの項目完全一致、文字列型、空文字、文字数上限を検証します。Groq特有の`json_validate_failed`を条件にしたプレーンテキストfallbackはGroq経路にだけ残し、OpenAIのHTTP 400へ流用しません。元の本文・説明文・release notes、モデル応答はstate、公開JSON、artifact、ログへ保存しません。

生成済みの表示データは記事内容のfingerprintに結び付けて再利用します。同じ内容には再課金しません。`generatorRevision`はモデル名ではなく入力ハッシュの契約バージョンです。Luna移行時にも既存値と生成済み項目の`inputHash`を保持し、モデル識別情報をstate/feedへ追加しません。既存の英日`machine`・`reviewed`は残し、新規記事か再試行時刻に達した`missing`だけを新しい順に1 runあたり最大50件処理します。英語を後から補完しても、以前の英語欠落を入力にした日本語生成文とそのハッシュは履歴として維持します。未生成の日本語項目のみ、新しい英語に対応する入力ハッシュへ更新します。内容のfingerprintが変わった場合は新しい記事入力として扱います。

通常収集ではOpenAIのAPIキーがない、生成に失敗する、または出力契約に合わない場合でも公開を継続します。失敗したlocaleだけを`missing`として記録し、原文タイトルのまま表示できます。両localeが失敗した場合も同様です。手動の日本語補完はキー未設定なら開始せず失敗します。表示データは事実確認や運用判断を代替しません。

各runは本文を出さずに `PRESENTATION` と `PRESENTATION_SOURCE` の行を出力します。ここでは記事候補数、記事単位の試行数、locale単位の試行・成功・失敗数、次回以降へ繰り越した数を確認します。`PRESENTATION_PATH` と `PRESENTATION_SOURCE_PATH` は `strict_json_schema`、`plaintext_fallback`、`legacy` ごとの成功件数だけを示します。失敗がある場合は、全体の `PRESENTATION_FAILURE` / `PRESENTATION_FALLBACK_FAILURE` とソース別の同名ログに安全な理由コードと件数を出します。

表示生成の失敗は、公開feedとは分離したstate内の `presentationRetryQueue` にlocale単位で隔離します。各エントリはsource、item fingerprint、locale、`failureCount`、`lastFailureAt`、`nextRetryAt`、安全な失敗コード、安全なprovider error code、`quarantined`だけを持ち、本文やモデル応答は保存しません。再試行間隔は1時間、2時間、4時間…と指数バックオフし、5回目の失敗で隔離して自動再試行を止めます。再試行時刻前・隔離中のrunは通常収集でも日本語補完でも外部モデルを呼ばず、公開feedはそのまま更新できます。Luna移行では隔離キューを一括解除しません。

`json_validate_failed` と記録された隔離だけを再試行する場合は、daily collectのworkflow_dispatchで `retry_json_validate_failed=true` を指定します。これはその分類の隔離だけを解除し、他の原因の隔離は維持します。以前のv1 stateはprovider error codeを記録していないため、この操作で対象と推測しません。ログを確認済みの旧HTTP 400隔離を今回に限り回復させる場合は、`retry_json_validate_failed=true` と `retry_legacy_http_400=true` を**両方**指定します。後者だけの実行は拒否されます。原因を限定できない場合は、従来どおり `retry_failed=true` で全キューを手動解除できますが、これは最後の手段です。

- `api_key_unavailable` — APIキーが未設定
- `auth_401` / `permission_403` — 認証・権限の失敗（自動再試行しない）
- `rate_limited_429` — 一時的なレート制限または課金・利用枠の制限。後者は同一run内で再試行しない
- `http_server_error` — HTTP 5xx。OpenAIでは一時的な500/502/503/504だけ最大2回の範囲で再試行する
- `network_error` — 接続・タイムアウトなどの通信失敗
- `response_decode_error` / `response_invalid_json` — 応答を文字列またはJSONとして読めない
- `response_missing_content` / `response_invalid_shape` — 応答に必要な生成データがない、または契約外
- `output_limit` / `response_refused` / `response_filtered` — 出力上限到達、拒否、コンテンツフィルタ
- `short_headline_invalid` / `summary_invalid` — 生成文が空、文字列でない、または長さ上限を超過
- `unknown` — 上記に安全に分類できない失敗

理由コードは調査の入口であり、記事本文やモデルの応答内容を出すものではありません。通常収集は安全なprovider `error.type` / `error.code`、試行回数、許可した`Retry-After`・トークン残量・リセット時間だけを集計ログに出します。日本語補完も失敗時に同じ項目だけを出します。タイトル、RSS説明文、release notes、モデル応答や例外本文はログに出しません。

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
