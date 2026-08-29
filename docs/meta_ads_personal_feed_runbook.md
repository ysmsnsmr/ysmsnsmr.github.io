# Meta Ads Personal Feed runbook

`meta-ads-updates/` の通常画面は、承認済み週次indexではなく `personal-feed.json` を表示する個人・同僚向け情報フィードです。収集・表示は毎日自動で行い、人間レビューは公開条件ではありません。

## 自動収集するソース

- Meta Newsroom Product News RSS — Meta公式
- Meta Business SDK Releases（Node.js）— Meta公式GitHub公開API
- Search Engine Land Meta RSS（PPCカテゴリのみ）— 非公式・未確認
- Jon Loomer Digital RSS — 非公式・未確認

非公式の文字付きラベルと画面上部の注意表示は削除しません。非公式情報は早期検知の参考であり、対応や正確性の判断には必ずMeta公式情報を確認してください。

この一覧にない候補は、HTTPSで公開され、RSSまたは安定した公開APIがあり、タイトル・URL・日付を安全に抽出できる場合だけ追加します。HTMLスクレイピング、ログインが必要なページ、429やアクセス制限が確認されているページは自動収集へ追加しません。Python/PHP/Java版SDK Releases APIは取得可能ですが、同じversionを重複表示するため、横断dedupeを実装するまで追加しません。

## 通常運用

`Meta Ads Personal Feed daily collect` は毎日 `00:15 UTC`（通常08:15 MYT）に実行されます。すべてのソースの取得・形式検査・解析・契約検証が成功した場合にだけ、次の2ファイルを更新します。

- `data/meta_ads_personal_feed_state.json` — URL、タイトル、日付、fingerprint、取得日時だけを保持する状態
- `meta-ads-updates/personal-feed.json` — GitHub Pagesで表示する公開フィード

生HTML、記事本文、画像、認証情報、Cookieは保存しません。いずれかのソースで失敗したrunは既存の公開フィードを更新しません。

初回成功runは、各RSS/APIの現在の項目をbaselineとして表示します。これは「その日に発表された」という意味ではなく、`最終確認` が初回取得日であることを意味します。

## 操作と停止

リポジトリ変数 `META_ADS_TRACKER_COLLECT_ENABLED` を `false` にすると、checkout・依存関係インストール・外部アクセス・commit・artifact uploadの前に正常終了します。`true` または未設定で有効です。それ以外の値は設定ミスとして失敗します。

手動で初回取得または再確認する場合は、Actionsの `Meta Ads Personal Feed daily collect` を `main` に対して実行します。成功後はartifact `meta-ads-personal-feed-<run id>` と公開画面を確認してください。

## 旧Trackerの扱い

weekly assemble、Friday preflight、secondary shadow、official canaryの定期実行は停止しています。既存の候補、週次artifact、recovery artifact、承認記録、過去の `latest.json` は履歴として残しますが、Personal Feedの表示や更新には使いません。必要な場合だけ手動実行してください。
