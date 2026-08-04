# ざっくり出費

iPhoneから支払い直後に、金額・分類・必要度・任意メモを記録する静的PWAです。データはブラウザのlocalStorageにだけ保存され、外部へ送信されません。

公式版はポートフォリオとは別オリジンの [https://zakkuri-spend.countryball.chatgpt.site/](https://zakkuri-spend.countryball.chatgpt.site/) で配信します。オリジンが変わるとlocalStorageは自動では移らないため、旧URLでJSONを書き出し、公式版で読み込んで移行します。

## Local preview

リポジトリのルートでローカルHTTPサーバーを起動します。

```sh
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000/daily-spend/` を開きます。Service Workerは `file://` では確認できないため、必ずHTTPまたはHTTPSで開いてください。

## Automated tests

```sh
cd daily-spend
npm test
```

テストはlocalStorageの代わりにメモリ内の保存領域を使い、実データを書き換えません。

## iPhone installation and offline check

1. HTTPSで公開された `/daily-spend/` をSafariで開く。
2. 共有メニューから「ホーム画面に追加」を選ぶ。
3. ホーム画面のアイコンから起動し、1件保存してアプリを終了する。
4. 機内モードにしてホーム画面から再起動する。
5. 画面が表示され、保存した記録と集計が残っていることを確認する。

## Data safety

- 保存キーは `daily-spend-state`、schema versionは `2` です。
- v1を検出すると、元のraw文字列を `daily-spend-state-v1-pre-migration` に一度だけ保護してからv2へ移行します。
- version付きJSON export/import、raw export、項目単位の破損診断を利用できます。
- import前の状態は `daily-spend-state-before-import` にコピーしてから更新します。
- 不正JSON、壊れたschema、将来versionを検出した場合、元データを守るため追加・編集・削除を停止します。raw exportと診断は停止中も利用できます。
- 端末やブラウザのデータを消去すると記録も失われます。同期機能はありません。定期的にJSONを書き出してください。
- 月末の正確な支出額は銀行明細ツールを正とし、このアプリは購入判断の振り返りに使います。

詳しい移行順序とrollback方法は [MIGRATION.md](./MIGRATION.md) を参照してください。

## Category IDs

v2は表示名ではなく `daily-spend:*` の安定した内部IDを保存します。銀行明細ツールの分類定義は参照・共有しません。将来連携する場合も、双方の外側に明示的な変換テーブルを置きます。

## 7-day trial

| Day | 入力できなかった場面・理由 | 購入判断が変わった例 | 気づき |
| --- | --- | --- | --- |
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |

試用後は機能追加より先に、入力できなかった理由と各入力項目の負担を確認します。
