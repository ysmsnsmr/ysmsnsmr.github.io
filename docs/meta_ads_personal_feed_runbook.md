# Meta Ads Personal Feed runbook

`meta-ads-updates/` の通常画面は、承認済み週次indexではなく `personal-feed.json` を表示する個人・同僚向け情報フィードです。収集・表示は毎日自動で行い、人間レビューは公開条件ではありません。

## 自動収集するソース

- Meta Newsroom Product News RSS — Meta公式
- Meta Business SDK Releases（Node.js）— Meta公式GitHub公開API
- Social Media Today RSS（Meta／Facebook／Instagramかつ広告関連の見出しのみ）— 非公式・未確認
- Jon Loomer Digital RSS — 非公式・未確認

Search Engine Land Meta RSSは、2026-08-30にGitHub ActionsでHTTP 403が繰り返し再現したため一時停止しています。安定した自動取得を確認できるまで再導入しません。

Social Media Todayは一般ニュースRSSのため、Meta／Facebook／Instagramの語と広告関連語の両方を含む見出しだけを掲載候補にします。これは記事の正確性を保証するものではなく、フィードの対象範囲を絞るための機械的な条件です。

非公式の文字付きラベルと画面上部の注意表示は削除しません。非公式ソースは早期検知の参考情報であり、Meta公式の見解を示すものではありません。公式情報で確認できない内容もあるため、重要な対応や判断には、複数の情報源や実環境で追加確認してください。

この一覧にない候補は、HTTPSで公開され、RSSまたは安定した公開APIがあり、タイトル・URL・日付を安全に抽出できる場合だけ追加します。HTMLスクレイピング、ログインが必要なページ、429やアクセス制限が確認されているページは自動収集へ追加しません。Python/PHP/Java版SDK Releases APIは取得可能ですが、同じversionを重複表示するため、横断dedupeを実装するまで追加しません。

## 通常運用

`Meta Ads Personal Feed daily collect` は毎日 `00:15 UTC`（通常08:15 MYT）に実行されます。すべてのソースの取得・形式検査・解析・契約検証が成功した場合にだけ、次の2ファイルを更新します。

- `data/meta_ads_personal_feed_state.json` — URL、タイトル、日付、fingerprint、取得日時と、日本語表示データのキャッシュを保持する状態
- `meta-ads-updates/personal-feed.json` — GitHub Pagesで表示する公開フィード

生HTML、記事本文、画像、認証情報、Cookieは保存しません。いずれかのソースで失敗したrunは既存の公開フィードを更新しません。

## 日本語短見出し・要約

収集時には、RSSの説明文またはSDK release notesを**そのrunの一時入力だけ**として、短見出しと要約の日本語表示データを生成します。元の本文・説明文・release notesはstate、公開JSON、artifact、ログへ保存しません。

生成済みの表示データは記事内容のfingerprintに結び付けて再利用します。同じ内容には再課金しません。内容が変わった記事、または未生成の記事だけを新しい順に1 runあたり最大12件処理します。

GroqのAPIキーがない、生成に失敗する、または出力契約に合わない場合でも、収集と公開は継続します。その記事は `pending` として記録され、原文タイトルのまま表示できます。日本語表示データは事実確認や運用判断を代替しません。

## 画面の使い方

一覧は短見出し、ソース区分、発表日・最終更新日、対象プラットフォームを表示します。`詳細を見る`を選ぶと、同じ公開feedから該当記事を読み込み、短見出し、日本語要約、原文タイトル、元記事リンクを表示します。

日本語要約が未生成の間も詳細画面は利用でき、原文タイトルと元記事リンクを表示します。一覧のソース・区分・キーワード条件は、詳細画面から一覧へ戻ったときに維持されます。保存期間の終了などで記事が消えたURLは、安全な「記事が見つかりません」画面になります。

初回成功runは、各RSS/APIの現在の項目をbaselineとして表示します。これは「その日に発表された」という意味ではなく、初回収集時点でソースに掲載されていたことを示します。

## 操作と停止

リポジトリ変数 `META_ADS_TRACKER_COLLECT_ENABLED` を `false` にすると、checkout・依存関係インストール・外部アクセス・commit・artifact uploadの前に正常終了します。`true` または未設定で有効です。それ以外の値は設定ミスとして失敗します。

手動で初回取得または再確認する場合は、Actionsの `Meta Ads Personal Feed daily collect` を `main` に対して実行します。成功後はartifact `meta-ads-personal-feed-<run id>` と公開画面を確認してください。

日本語表示の呼び出しは、リポジトリ変数 `META_ADS_PERSONAL_FEED_JA_ENABLED` で制御します。未設定または `true` で有効、`false` で停止します。`META_ADS_PERSONAL_FEED_GROQ_MODEL` は使用モデルを上書きできます。未設定時は `openai/gpt-oss-120b` を使います。値が `true` / `false` 以外の場合は、設定ミスとしてcollectorを失敗させます。

## 旧Trackerの扱い

weekly assemble、Friday preflight、secondary shadow、official canaryの定期実行は停止しています。既存の候補、週次artifact、recovery artifact、承認記録、過去の `latest.json` は履歴として残しますが、Personal Feedの表示や更新には使いません。必要な場合だけ手動実行してください。
