# Lazyweb MCP Reference Log Template

このテンプレートは、Lazyweb MCPで集めた参考情報から抽象パターンだけを記録するためのものです。参照元をコピーせず、UI/LP改善または記事ヘッダー画像方向性づくりに使います。運用手順は `docs/lazyweb-mcp-research-workflow.md` と `docs/lazyweb-reference-policy.md` に従います。

## Research Setup

- 調査日:
- 調査目的:
- 対象:
- 成功条件:
- 使うルート: UI/LP改善 / 記事ヘッダー画像
- フォールバック有無:

## Lazyweb MCP Input Summary

- category:
- productまたはtarget context:
- conversion goal:
- constraints:
- visual inspection budget:
- high design bar指定:
- Lazyweb MCPが使えなかった場合の理由:

## Evidence Summary

ログには要約だけを残します。スクショ原本、参照画像、画像URL、署名付きURL、認証情報、個人用設定値、MCP接続設定の実体は保存しません。

| No | 取得日 | evidence概要 | 抽出した抽象パターン | 使わない要素 | 最終案への反映メモ |
| --- | --- | --- | --- | --- | --- |
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |
| 4 |  |  |  |  |  |
| 5 |  |  |  |  |  |

## UI/LP Improvement Route

UI/LP改善に使う場合だけ埋めます。画面を直接真似せず、A/B差分から改善仮説だけを抽出します。

- 対象画面:
- conversion goal:
- 参考になったA/B差分:
- 抽出した抽象パターン:
- 実装に反映する仮説:
- 採用しない要素:

## Header Image Route

記事ヘッダー画像に使う場合だけ埋めます。ビジュアルを直接真似せず、構図、余白、色、情報密度だけを抽出します。

- 対象記事:
- 主題:
- ヘッダーで出したい感情:
- 構図:
- 色:
- モチーフ:
- 情報密度:
- 余白:
- 参照元から離すための注意:

## Common Pattern Summary

- 情報階層:
- 構図:
- 色:
- タイポグラフィ:
- モチーフ:
- 情報密度:
- 余白:
- 使わない要素:

## Output Direction

### 案1

- 狙い:
- 反映する抽象パターン:
- UI/LP改善の場合の仮説:
- 記事ヘッダー画像の場合の方向性:
- 参照元から離すための注意:

### 案2

- 狙い:
- 反映する抽象パターン:
- UI/LP改善の場合の仮説:
- 記事ヘッダー画像の場合の方向性:
- 参照元から離すための注意:

### 案3

- 狙い:
- 反映する抽象パターン:
- UI/LP改善の場合の仮説:
- 記事ヘッダー画像の場合の方向性:
- 参照元から離すための注意:

## Safety Review

- 参照元をコピーしていない:
- 抽象パターンのみ利用している:
- スクショ原本や参照画像をGit管理していない:
- 画像URL、署名付きURL、認証情報、個人用設定値、MCP接続設定の実体を保存していない:
- ロゴ、人物写真、独自UI、独自イラストを真似していない:
- 最終成果物が参照元と混同されない:

## Header Image Operation Patterns

この欄は、Lazyweb調査から抽象パターンだけを残し、次回以降のヘッダー画像ブリーフに転用するための運用メモです。参照元の画像、スクショ原本、画像URL、署名付きURL、ロゴ、固有UI、固有文言は保存・使用しません。

### 雑誌風の抽象パターン

最小参照記録:

- `https://www.theepochtimes.com/bright/radiant-life` / Magazines & Newspapers / desktop
- `https://www.forbes.com/forbeslife/` / News / desktop
- `https://www.latimes.com/lifestyle/image` / Magazines & Newspapers / desktop

抽象パターン:

- Hero構図: 大きな写真または静物イメージを最上段に置き、強い見出しを載せられる余白を残す。主役モチーフは片側に寄せ、反対側をタイトル安全領域にする。
- 記事グリッド: heroの下に2〜4列の画像主導カードを置く発想。ヘッダー画像単体では、複数の小さな紙片、写真片、生活道具を控えめに並べて「記事が続く」気配だけを出す。
- カテゴリタブ: lifestyle, food, travel, home, wellnessのような分類感を、読める文字ではなく色面、紙片、棚、ノートの区切りで抽象化する。
- 余白の使い方: 広めの余白、浅い奥行き、控えめな境界線。情報を詰めず、誌面の呼吸を作る。
- 向く記事: 生活エッセイ、観察メモ、暮らしの仕組みを静かに読み解く記事。

使わない要素:

- 実在メディアのロゴ、記事タイトル、カテゴリ名、購読導線、広告バナー
- 参照元に近いグリッド、ナビ、配色、記事サムネイル構成
- 読める文字、実在人物写真、実在ブランド、ニュースサイト固有のUI

### UGC風の抽象パターン

最小参照記録:

- Product/community story feed系 / Social Networking / mobile
- Story reading feed系 / Books / mobile
- Publishing profile/feed系 / News / mobile

抽象パターン:

- トップカード: 最初に「おすすめ」「続き」「注目メモ」風の大きめカードを置く。ヘッダー画像では、1枚だけ少し大きい生活メモカードとして扱う。
- 横並びカテゴリ: chipsや短いタブの気配は、読める文字ではなく小さな色付きラベル、付箋、丸いマーカーで表現する。
- 投稿カードの並び: 小さなカードを縦または斜めに重ね、アバターや実SNS UIではなく、メモ片、写真片、短い罫線、日付を消した記録カードとして抽象化する。
- 下部ナビ的構成: 実UIとして再現せず、画面下のアイコン列ではなく、余白の下端に小さな点やカード端を置いて「生活記録が続く」程度に留める。
- 向く記事: 生活記録、買い物メモ、近所の気づき、使ってみた感、コミュニティの空気を軽く含む記事。

使わない要素:

- 実SNSのUI、反応アイコン列、プロフィール画面、下部ナビの直接再現
- 実在ユーザー名、ランキング、レビュー促進モーダル、投稿文のコピー
- サービス固有のタブ名、ブランド色、通知バッジ、実在アプリ画面

### マレーシア暮らし記事向けの新方向性

#### Magazine Life Opening

- 狙い: マレーシア暮らしの観察記事を、生活誌の冒頭ページのように見せる。
- 構図: 横長ヘッダー。片側に窓光、机、買い物品、紙、日用品などの静物。もう片側に日本語タイトル用の大きな余白。
- 質感: 熱帯の室内光、タイル、木の机、柔らかい影、控えめな緑の反射。
- 向くテーマ: 制度を日常から見つける記事、生活の意味が変わる記事、統計を暮らしに引き寄せる記事。
- 注意: 雑誌風でも、実在誌面、記事カード、ロゴ、読める見出しは作らない。

#### Life Memo Card Collage

- 狙い: マレーシア生活の小さな観察を、日記カードや投稿メモが集まったように見せる。
- 構図: 数枚の小さな無地カード、写真片風の抽象矩形、付箋風ラベルを重ねる。1枚だけ大きめのカードをトップカードにする。
- 質感: 生活スナップの気配、軽いレビュー感、手元のメモ感。ただし人物、実SNS画面、読める投稿文は使わない。
- 向くテーマ: 買い物、移動、近所の発見、日用品、生活の比較、コミュニティの雰囲気。
- 注意: UGC風でも、SNS UIやアプリ画面の模写にしない。

### 次回画像ブリーフに入れる文言

共通:

```text
Use only abstract layout patterns from reference research. Do not copy any real website, magazine, social feed, logo, UI, article title, brand color, or wording. No text, no readable labels, no screenshots, no image URLs, no signed URLs, no real app interface.
```

Magazine Life Opening向け:

```text
Create a wide editorial magazine-style life-note header for an article about everyday Malaysia. Use a calm still-life composition with generous negative space for a Japanese title overlay, warm tropical indoor light, subtle domestic textures, and a feature-article opening mood. Suggest a magazine homepage structure only abstractly through balance, spacing, and quiet visual hierarchy. No logos, no readable text, no real publication layout, no copied navigation, no article grid reproduction.
```

Life Memo Card Collage向け:

```text
Create a wide header background inspired by abstract life-log and community memo patterns, using layered blank cards, small photo-like rectangles, soft labels without text, and a gentle everyday Malaysia atmosphere. Make it feel like personal notes and small lived observations, not a real social media app. Leave clean space for a Japanese title overlay. No real SNS UI, no profile screen, no reaction icons, no usernames, no readable posts, no brand elements.
```
