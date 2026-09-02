# Meta Ads Personal Feed runbook

`meta-ads-updates/` の通常画面は、承認済み週次indexではなく `personal-feed.json` を表示する個人・同僚向け情報フィードです。収集・表示は毎日自動で行い、人間レビューは公開条件ではありません。

## 自動収集するソース

- Meta Newsroom Product News RSS — Meta公式
- Meta Business SDK Releases（Node.js）— Meta公式GitHub公開API
- Social Media Today RSS（Meta／Facebook／Instagramかつ広告関連の見出しのみ）— 非公式・未確認
- Jon Loomer Digital RSS — 非公式・未確認
- Meta for Business News — Jon Loomer RSS本文から見つかったMeta公式記事だけを追加取得

Search Engine Land Meta RSSは、2026-08-30にGitHub ActionsでHTTP 403が繰り返し再現したため一時停止しています。安定した自動取得を確認できるまで再導入しません。

Social Media Todayは一般ニュースRSSのため、Meta／Facebook／Instagramの語と広告関連語の両方を含む見出しだけを掲載候補にします。これは記事の正確性を保証するものではなく、フィードの対象範囲を絞るための機械的な条件です。

Jon Loomerの `Meta Advertising` カテゴリ記事に `https://www.facebook.com/business/news/<slug>` 形式のリンクがある場合は、リンク先をMeta公式記事の候補として扱います。完全一致するHTTPSホストとパスだけを許可し、Meta公式ページ自身からcanonical URL、記事種別、タイトル、説明、発表日を検証できた候補だけを「Meta公式」として掲載します。Jon Loomer側の見出しや説明をMeta公式情報として転用しません。

Meta公式ページはRSSや公開APIではなくHTMLから限定的なmetadataを読むため、アクセス制限や構造変更の影響を受けます。この追加取得だけが失敗した場合は該当候補を掲載せず、他のPersonal Feed収集は継続します。本文・失敗URL・例外本文は保存またはログ出力せず、許可ホスト、最大3回のredirect、1 MiBの応答上限、1 run最大20件を維持します。

各収集runはソースごとに `SOURCE_PIPELINE` を出力します。`mode=direct` は通常のRSS/API、`mode=discovered_official` は別ソース内の公式リンクから追加取得する経路です。`parsed` はRSS item、API releaseまたは公式HTML候補として読めた件数、`valid` は安全なURLと必要情報を持つ候補数、`matched` は掲載条件を満たした件数、`excluded` は直接ソースの有効候補のうち掲載条件で除外した件数、`retained` は保存期間内に残った件数です。発見経路では `discovered_links`、`attempted_links`、`rejected_links`、`deferred_links` も件数だけ出力します。`all_groups` 条件のソースには `SOURCE_MATCH_GROUP` も出力し、各キーワード群を満たした候補数を確認できます。たとえば直接ソースの `valid > 0` かつ `matched = 0` は、取得失敗ではなく現在の掲載条件に合う記事がなかったことを示します。

これらは件数・ソースID・パーサー版・レスポンスサイズだけの安全な運用ログです。タイトル、記事本文、RSS説明文、URL、認証情報、Cookieは出力しません。

非公式の文字付きラベルと画面上部の注意表示は削除しません。非公式ソースは早期検知の参考情報であり、Meta公式の見解を示すものではありません。公式情報で確認できない内容もあるため、重要な対応や判断には、複数の情報源や実環境で追加確認してください。

この一覧にない通常ソースは、HTTPSで公開され、RSSまたは安定した公開APIがあり、タイトル・URL・日付を安全に抽出できる場合だけ追加します。ログインが必要なページ、429やアクセス制限が確認されているページは通常ソースへ追加しません。HTML取得は上記のMeta for Business News発見経路だけの限定例外であり、失敗時にフィード全体を止めない境界を維持します。Python/PHP/Java版SDK Releases APIは取得可能ですが、同じversionを重複表示するため、横断dedupeを実装するまで追加しません。

## 通常運用

`Meta Ads Personal Feed daily collect` は毎日 `00:15 UTC`（通常08:15 MYT）に実行されます。すべてのソースの取得・形式検査・解析・契約検証が成功した場合にだけ、次の順序で2ファイルを更新します。

```text
安全な取得 → 形式検査・解析 → 鮮度判定 → 関連性判定
→ state構築 → 英日表示データ生成 → feed検証 → 原子的公開
```

- `data/meta_ads_personal_feed_state.json` — URL、タイトル、日付、fingerprint、取得日時と、英語正本・日本語overlayの表示データキャッシュを保持する状態
- `meta-ads-updates/personal-feed.json` — GitHub Pagesで表示する公開フィード

生HTML、記事本文、画像、認証情報、Cookieは保存しません。いずれかのソースで失敗したrunは既存の公開フィードを更新しません。

## 鮮度・関連性

発表日または最終更新日の新しい方が365日より前の記事は、表示データ生成の前に除外します。どちらの日付もない記事だけは初回観測日を使います。再観測日時で期限を延長することはありません。期限切れの記事はstate、公開feed、artifactに残しません。

Meta Newsroom Product News RSSは、広告関連語がタイトル、RSS説明、カテゴリのいずれかにある記事だけを採用します。Business SDKは全release、Jon Loomerは`Meta Advertising`カテゴリ、Social Media Todayは既存のMeta系語と広告系語の二群条件を維持します。ソースごとに`relevanceRevision`を持ち、意味のある条件変更時には当該ソースだけをreseedします。

`workflow_dispatch`で`reseed_source_id`に設定済みのソースIDを指定すると、そのソースだけを現行の鮮度・関連性条件で再構築します。初回のProduct News移行では`meta-product-news-rss`を指定します。同じURLが引き続き採用される場合、`firstObservedAt`は維持されます。未登録IDはcollectorが失敗して既存公開物を保持します。

## 英語・日本語の短見出し・要約

収集時には、RSSの説明文またはSDK release notesを**そのrunの一時入力だけ**として、英語の短見出し・要約と、その日本語訳を**1記事につきGroqへ1回だけ**要求します。元の本文・説明文・release notes、Groq応答はstate、公開JSON、artifact、ログへ保存しません。

生成済みの表示データは記事内容のfingerprintに結び付けて再利用します。同じ内容には再課金しません。内容が変わった記事、または未生成の記事だけを新しい順に1 runあたり最大12件処理します。

GroqのAPIキーがない、生成に失敗する、または4項目の出力契約に合わない場合でも、収集と公開は継続します。その記事は英語・日本語をともに`missing`として記録し、原文タイトルのまま表示できます。一方の言語だけを公開することはありません。表示データは事実確認や運用判断を代替しません。

各runは本文を出さずに `PRESENTATION` と `PRESENTATION_SOURCE` の行を出力します。ここでは生成候補数、試行数、成功数、失敗数、次回以降へ繰り越した数だけを確認します。失敗がある場合は、全体の `PRESENTATION_FAILURE` とソース別の `PRESENTATION_SOURCE_FAILURE` に安全な理由コードと件数を出します。

- `api_key_unavailable` — APIキーが未設定
- `http_client_error` / `http_server_error` — Groq側のHTTP 4xx / 5xx 応答
- `network_error` — 接続・タイムアウトなどの通信失敗
- `response_decode_error` / `response_invalid_json` — 応答を文字列またはJSONとして読めない
- `response_missing_content` / `response_invalid_shape` — 応答に必要な生成データがない、または契約外
- `short_headline_invalid` / `summary_invalid` — 生成文が空、文字列でない、または長さ上限を超過
- `unknown` — 上記に安全に分類できない失敗

理由コードは調査の入口であり、記事本文やGroqの応答内容を出すものではありません。タイトル、RSS説明文、release notes、Groqの応答や例外本文はログに出しません。

既存の`missing`を確認する場合は、手動workflow `Meta Ads Personal Feed Japanese presentation backfill` を使います。最初は `presentation_limit=1` で実行し、`generated=1` と `failed=0` を確認してから、必要に応じて最大12件まで増やします。このworkflowも現在のRSS/APIを取得して一時文脈を作るため、すでにRSS/APIから消えた古い記事の要約は生成しません。stateには本文を保存しない設計のため、そのような記事を要約するには個別取得の別設計が必要です。

## 画面の使い方

一覧は短見出し、ソース区分、発表日・最終更新日を表示します。`詳細を見る`を選ぶと、同じ公開feedから該当記事を読み込み、短見出し、日本語要約、原文タイトル、対象プラットフォーム、元記事リンクを表示します。

日本語要約が未生成の間も詳細画面は利用でき、原文タイトルと元記事リンクを表示します。一覧のソース・区分・キーワード条件は、詳細画面から一覧へ戻ったときに維持されます。保存期間の終了などで記事が消えたURLは、安全な「記事が見つかりません」画面になります。

初回成功runは、各RSS/APIの現在の項目をbaselineとして表示します。これは「その日に発表された」という意味ではなく、初回収集時点でソースに掲載されていたことを示します。

## 操作と停止

リポジトリ変数 `META_ADS_TRACKER_COLLECT_ENABLED` を `false` にすると、checkout・依存関係インストール・外部アクセス・commit・artifact uploadの前に正常終了します。`true` または未設定で有効です。それ以外の値は設定ミスとして失敗します。

手動で初回取得または再確認する場合は、Actionsの `Meta Ads Personal Feed daily collect` を `main` に対して実行します。成功後はartifact `meta-ads-personal-feed-<run id>` と公開画面を確認してください。

日本語表示の呼び出しは、リポジトリ変数 `META_ADS_PERSONAL_FEED_JA_ENABLED` で制御します。未設定または `true` で有効、`false` で停止します。`META_ADS_PERSONAL_FEED_GROQ_MODEL` は使用モデルを上書きできます。未設定時は `openai/gpt-oss-120b` を使います。値が `true` / `false` 以外の場合は、設定ミスとしてcollectorを失敗させます。

## 旧Trackerの扱い

weekly assemble、Friday preflight、secondary shadow、official canaryの定期実行は停止しています。既存の候補、週次artifact、recovery artifact、承認記録、過去の `latest.json` は履歴として残しますが、Personal Feedの表示や更新には使いません。必要な場合だけ手動実行してください。
