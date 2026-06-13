# Lazyweb Reference Log: マレーシア暮らしで、スーパーの使い分けが少しずつ定まってきた話

この記事用のヘッダー画像方向性づくりのため、既存のLazyweb運用メモと記事本文から抽象パターンだけを利用する。参照元の画像、UI、ロゴ、構図、文言はコピーせず、生活エッセイとしてのオリジナル表現に落とす。

対象記事:

- `マレーシア暮らしで、スーパーの使い分けが少しずつ定まってきた話`
- 主題: 移住当初は買い物先や買うものの判断に疲れていたが、徒歩圏の複数店舗を役割ごとに使い分けられるようになり、暮らしが少し楽になった話。
- ヘッダーで出したい感情: 店を攻略した達成感ではなく、迷いが減って暮らしが回り始めた静かな安心感。

## 共通パターンまとめ

- 構図: 横長ヘッダー。左側に買い物帰りの静物、右側に日本語タイトルを載せやすい広い余白。
- 色: 熱帯の室内光、葉物野菜の緑、木のテーブル、淡いタイル、無地の日用品、紙片のオフホワイト。
- タイポグラフィ: 画像内に読める文字は入れない。メモ、レシート、ラベルは無地または抽象的な短い線にする。
- モチーフ: 買い物袋、野菜、無地の包み、無地の日用品ボトル、3枚の小さなカードや付箋。
- 情報密度: 生活エッセイなので詰め込みすぎない。複数店舗の使い分けは、ロゴや店名ではなく、買い物カテゴリごとの小さなまとまりで示す。
- 余白: 右側をタイトル安全領域として残す。余白は白抜きではなく、光の当たったテーブルやタイル面として自然に作る。
- 使わない要素: 実在店舗、店名、ロゴ、価格、商品パッケージ、人物、場所が特定される外観、WebサイトUI、読める文字。

## 採用したヘッダー画像方向性

### 買い物帰りの静かな台所

- 狙い: 「今日はどこへ行けばよいか」が分かるようになった安心感を、買い物帰りの静物で表す。
- 構図: 左側に買い物袋、葉物野菜、無地の日用品、包み、3枚の小さな無地カード。右側は木のテーブルとタイルの余白。
- 色: 温かい木目、淡いタイル、野菜の緑、オフホワイト、淡い水色・黄色・ピンクのカード。
- モチーフ: 生活用品と食品が同じ台にまとまっていることで、買い物先の役割が定まった感覚を出す。
- 文字の扱い: 画像内には文字なし。タイトルは後から日本語で重ねる想定。
- 参照元から離すための注意: 店舗名やブランドの手掛かりを出さず、特定のスーパーや地域を想起させない。

## Final Prompt

```text
Use case: photorealistic-natural
Asset type: wide blog header image, 1200x630 aspect ratio, suitable for a quiet Japanese lifestyle essay
Primary request: Create a calm editorial still-life header for an essay about gradually learning how to use different supermarkets in everyday Malaysia.
Scene/backdrop: A modest indoor tabletop near a window in warm tropical light, with subtle tile, wood, and soft shadow textures. The mood should feel lived-in, practical, and gently settled.
Subject: On the left side, arrange a reusable grocery bag edge, fresh vegetables, a small wrapped grocery item with completely plain unbranded wrapping, a few plain household goods in unbranded containers, and three small blank memo cards or color tabs suggesting different shopping roles. Keep the objects ordinary and domestic, not staged like advertising.
Composition: Wide landscape composition. Main objects clustered on the left third and lower-left area. Leave the entire right side clean and calm as negative space for a Japanese title overlay. Avoid visual clutter. The right half should be mostly warm tabletop, wall, or tile surface with soft light and no detailed objects.
Color and light: Warm tropical daylight, soft greens from vegetables, off-white paper, muted household-product colors, pale tile gray, small hints of red or yellow for Malaysia warmth. Balanced natural color, not a single-hue palette.
Mood: Quiet relief, fewer decisions, daily life starting to run smoothly. Not touristy, not dramatic, not a supermarket promotion.
Constraints: No readable text anywhere. No store names, no logos, no price tags, no brand packaging, no real supermarket storefront, no identifiable people, no copied website or magazine layout, no UI, no screenshots, no watermark. Receipts, notes, labels, and tabs must be blank or abstract unreadable marks only.
```

## Generated Asset

- Final image: `assets/headers/malaysia-supermarket-routine.png`
- Final dimensions: `1200x630`
- Generation mode: built-in image generation tool, then local resize with `sips`.

## Safety Review

- 参照元をコピーしていない: はい。既存ログの抽象パターンと記事本文の主題だけを利用した。
- 抽象パターンのみ利用している: はい。余白、静物構図、生活モチーフ、色の傾向だけを利用した。
- スクショ原本をGit管理していない: はい。スクショや参照画像は保存していない。
- ロゴ、人物写真、独自UI、独自イラストを真似していない: はい。
- 認証情報、個人用設定値、MCP接続設定の実体を書いていない: はい。
