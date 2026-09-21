# Meta Ads Personal Feed — Jevテスト結果

更新日: 2026-09-21

この文書の15件・50件テスト結果は、2026-09-20に実行したartifact-only shadowの記録である。後続変更により、Jevは現在、明示的なkill switchの下でPersonal Feedの関連度routingにも利用できる。過去artifactの`routingEffect: false`は、その時点のshadow実行についての値であり、現在の本番routing設定を示すものではない。

## 結論

Jevをまずartifact-onlyのshadow workflowで検証し、その結果を踏まえて、後続の明示的なoverrideにより本番collectorの関連度routingへ接続した。

最終的に、公開feedの50件を対象にした実行で次を確認した。

- 50件分類、失敗0件
- `direct_impact`: 22件（44%）
- `strategic_signal`: 20件（40%）
- `unrelated`: 5件（10%）
- `unclear`: 3件（6%）
- shadow実行では`routingEffect: false`
- 後続の本番routingでは、`META_ADS_JEV_ROUTING_ENABLED=true` の場合にJevのchoiceを掲載判定へ反映する
- 本番routingは承認登録を行わず、Jevの分類結果を掲載対象判定にだけ使用する

人間確認では、`unrelated`と`unclear`の判定も概ね妥当と判断した。`direct_impact`と`strategic_signal`は掲載対象、`unclear`も掲載して後からartifactを確認し、`unrelated`だけを非公開の除外判定として扱う現行仕様になっている。

## 検証対象と制約

- 対象: `meta-ads-updates/personal-feed.json`の公開済み記事
- モデル: `jev-1.13.0`
- question set: `meta-ads-relevance-v1`
- 最大件数: shadow workflow入力の`limit`で指定（1〜50件）
- 成果物: shadowではJevの判定結果を含むartifact JSON、本番routingでは同一runのrouting artifact
- shadowの非対象: 公開feedの書換え、state更新、承認登録、DROP自動化、routing変更
- APIキー: GitHub Actions secret `TYPESAFE_API_KEY`
- shadow kill switch: `META_ADS_JEV_SHADOW_ENABLED=true`
- production routing kill switch: `META_ADS_JEV_ROUTING_ENABLED=true`

Jevには公開タイトルと英語source context（最大4,000文字）だけを一時的に渡す。artifactとstateには本文・見出し・要約・URL・raw provider response・secretを保存せず、`itemId`、source ID、分類、confidence、model ID、処理時間、安全なerror codeなどを記録する。見出し一覧を確認するときは、artifactの`itemId`を同時点の公開feedへ照合した。

## 実行履歴

### API接続前の失敗

初期のローカル実行では、次の状態だった。

- TypeSafe APIアクセス未開通
- `/v1/models`の初回リクエストはHTTP 400
- SDKが想定する追加ヘッダーを付けた後、HTTP 200を確認

APIキーをGitHub Actions secretへ登録後、production shadow workflowを実行した。その後、同じsecretを使う本番collectorのrouting経路を、リポジトリ変数で明示的に有効化できる状態にした。

### 15件テスト

- Run: [35489950484](https://github.com/ysmsnsmr/ysmsnsmr.github.io/actions/runs/35489950484)
- 実行コミット: `18a9552536511abbbb8760e19612de729f03f2f4`
- 結果: success
- 分類: 15件
- 失敗: 0件
- `routingEffect`: `false`
- 分類結果:
  - `direct_impact`: 5件
  - `strategic_signal`: 7件
  - `unrelated`: 3件
- source内訳:
  - Jon Loomer: 5件
  - Business SDK: 1件
  - Meta Product News: 3件
  - Social Media Today: 6件

費用画面では、約7.9K input tokens、spend `$0.0003`だった。

### 50件テスト

15件制限を外し、workflowの現在の上限である50件を指定した。

- Run: [35492820554](https://github.com/ysmsnsmr/ysmsnsmr.github.io/actions/runs/35492820554)
- 実行コミット: `504ee9aa7cd130ffbadec7d7fc70e59a48f0cc0b`
- 結果: success
- 分類: 50件
- 失敗: 0件
- `routingEffect`: `false`
- artifact: `meta-ads-jev-production-shadow-35492820554`
- source feed:
  - generatedAt: `2026-09-20T04:55:38Z`
  - availableItems: 56件
  - selectedItems: 50件
  - feed SHA-256: `c73f98920cb96c4564e4e07c082b3fb5f348c14fea7ac881c4b461076a9dbb85`

費用画面では、約16K input tokens、spend `$0.0006`だった。出力料金は無料表示だった。

## 50件テストの分類傾向

| 分類 | 件数 | 割合 |
|---|---:|---:|
| `direct_impact` | 22 | 44% |
| `strategic_signal` | 20 | 40% |
| `unrelated` | 5 | 10% |
| `unclear` | 3 | 6% |

### source別件数

| source | 件数 |
|---|---:|
| Jon Loomer | 28 |
| Meta Business News（discovered） | 4 |
| Business SDK | 4 |
| Meta Product News | 7 |
| Social Media Today | 7 |

## 人間確認

15件のartifact-only比較では、人間ラベルとの比較を行った。

- classified: 15件
- failed: 0件
- 一致: 8件
- 不一致: 7件
- 重大な`ACTION → DROP`相当の問題: なし

ただし、人間ラベルは15件の小規模な基準であり、Jevの正確性を証明するものではない。後続の50件テストでは、`unrelated`と`unclear`の見出しを人間が確認し、今回の分類は概ね妥当と判断した。

## 分類別の見出し

### `direct_impact`（22件）

1. [How to Approach Meta Advertising Control](https://www.jonloomer.com/meta-advertising-control/) — Jon Loomer（confidence 0.89）
2. [Meta Introduces a New Automatic Events Feature](https://www.jonloomer.com/meta-automatic-events-feature/) — Jon Loomer（0.99）
3. [Reply to Keywords Meta Ads Feature](https://www.jonloomer.com/reply-to-keywords-meta-ads-feature/) — Jon Loomer（1.00）
4. [Meta removes option to exclude ad placements](https://www.socialmediatoday.com/news/meta-removes-option-to-exclude-ad-placements/828461/) — Social Media Today（1.00）
5. [Meta Is Removing Placement Controls From Ad Sets](https://www.jonloomer.com/meta-removing-placement-controls-ad-sets/) — Jon Loomer（1.00）
6. [Meta Ads AI Connectors Get More Security Controls](https://www.jonloomer.com/meta-ads-ai-connectors-security-controls/) — Jon Loomer（0.98）
7. [Meta Tests Sequenced Events and Preferred Lead Answers for Lead Quality](https://www.jonloomer.com/meta-tests-sequenced-events-preferred-lead-answers/) — Jon Loomer（0.62）
8. [Exclusion-Only Custom Audiences](https://www.jonloomer.com/exclusion-only-custom-audiences/) — Jon Loomer（1.00）
9. [Meta Can Now Rewrite the Text on Your Ad Images](https://www.jonloomer.com/meta-rewrite-text-ad-images/) — Jon Loomer（1.00）
10. [Meta Redesigns Audiences Around Labels](https://www.jonloomer.com/meta-redesigns-audiences-around-labels/) — Jon Loomer（1.00）
11. [8M+ Advertisers Use Meta's AI Creative Tools. They Just Got a Major Upgrade.](https://www.facebook.com/business/news/muse-image-for-businesses) — Meta Business News（0.98）
12. [v25.0.2](https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v25.0.2) — Business SDK（0.96）
13. [Cannes Lions 2026: New Creative and Creator Tools for Every Marketer to Cross the AI Threshold](https://www.facebook.com/business/news/cannes-2026-cross-ai-threshold) — Meta Business News（0.71）
14. [Book appointments directly from your Lead Ads](https://www.facebook.com/business/news/book-appointments-directly-from-your-lead-ads) — Meta Business News（1.00）
15. [Hands-On With Push Delivery to This Ad](https://www.jonloomer.com/hands-on-push-delivery-to-this-ad/) — Jon Loomer（0.32）
16. [Customer Lifecycle Strategy Is Not What Advertisers Thought](https://www.jonloomer.com/customer-lifecycle-strategy-not-what-advertisers-thought/) — Jon Loomer（1.00）
17. [Meta Ads Attribution Reporting: What Your Results Really Mean](https://www.jonloomer.com/meta-ads-attribution-reporting/) — Jon Loomer（0.61）
18. [Meta Ads Grouping Reports, ChatGPT Conversions, and More](https://www.jonloomer.com/meta-ads-grouping-reports-chatgpt-conversions/) — Jon Loomer（0.50）
19. [One-Click CAPI Activated, New Meta Ads Features, and More](https://www.jonloomer.com/one-click-capi-activated-new-meta-ads-features/) — Jon Loomer（0.98）
20. [The Future of the Meta Advertiser](https://www.jonloomer.com/future-of-meta-advertiser/) — Jon Loomer（0.81）
21. [Meta Ads AI Connectors and Claude: Setup, Uses, and Risks](https://www.jonloomer.com/meta-ads-ai-connectors-claude/) — Jon Loomer（0.37）
22. [Removing Technical Barriers to Help Businesses of All Sizes Get More From Their Ads](https://www.facebook.com/business/news/pixel-conversionsapi-updates) — Meta Business News（1.00）

### `strategic_signal`（20件）

1. [Meta shares holiday 2026 planning guides](https://www.socialmediatoday.com/news/meta-shares-holiday-2026-planning-guides/830741/) — Social Media Today（0.93）
2. [Meta adds more creator partnership tools](https://www.socialmediatoday.com/news/meta-adds-more-creator-partnership-tools/830480/) — Social Media Today（0.60）
3. [What I Built With Muse, Meta’s New AI Agent](https://www.jonloomer.com/muse-meta-ai-agent/) — Jon Loomer（0.35）
4. [Instagram chief warns against eliminating algorithms](https://www.socialmediatoday.com/news/instagram-chief-warns-against-eliminating-algorithms/830130/) — Social Media Today（0.73）
5. [v26.0.1](https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v26.0.1) — Business SDK（0.69）
6. [Meta adds AI-powered assistant for SMB owners](https://www.socialmediatoday.com/news/meta-adds-ai-powered-assistant-for-smb-owners/828344/) — Social Media Today（0.56）
7. [Meta AI launches for Mac](https://www.socialmediatoday.com/news/meta-ai-launches-for-mac/828347/) — Social Media Today（0.40）
8. [Meta publishes holiday marketing guides](https://www.socialmediatoday.com/news/meta-publishes-holiday-marketing-guides/827856/) — Social Media Today（0.93）
9. [Meta Business SDK v26.0.0](https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v26.0.0) — Business SDK（0.29）
10. [15 Years of Facebook and Meta Advertising](https://www.jonloomer.com/15-years-facebook-meta-advertising/) — Jon Loomer（0.78）
11. [Meta AI Doesn’t Just Think, It Acts](https://about.fb.com/news/2026/07/meta-ai-muse-spark-doesnt-just-think-it-acts/) — Meta Product News（0.38）
12. [How to Use Meta Ads for Lead Generation](https://www.jonloomer.com/meta-ads-lead-generation/) — Jon Loomer（0.39）
13. [v25.0.3](https://github.com/facebook/facebook-nodejs-business-sdk/releases/tag/v25.0.3) — Business SDK（0.63）
14. [The Principles Behind My Meta Ads Strategy](https://www.jonloomer.com/meta-ads-strategy-principles/) — Jon Loomer（0.91）
15. [Introducing Muse Image: Image Generation Built for Your World](https://about.fb.com/news/2026/07/introducing-muse-image-meta-ai/) — Meta Product News（0.26）
16. [The Master Brief: My Complete Approach to Meta Ads](https://www.jonloomer.com/meta-ads-master-brief/) — Jon Loomer（0.76）
17. [What to Check When Meta Ads Aren’t Converting](https://www.jonloomer.com/meta-ads-arent-converting/) — Jon Loomer（0.36）
18. [How Many Active Ad Sets Should You Have in a Meta Ads Campaign?](https://www.jonloomer.com/active-ad-sets-meta-ads-campaign/) — Jon Loomer（0.35）
19. [How Many Meta Ads Campaigns Should You Have at Once?](https://www.jonloomer.com/how-many-meta-ads-campaigns/) — Jon Loomer（0.30）
20. [7 Common Meta Ads Mistakes Agencies Make](https://www.jonloomer.com/meta-ads-mistakes/) — Jon Loomer（0.66）

### `unrelated`（5件）

1. [Threads Expands Podcast Toolkit for Creators and Listeners](https://about.fb.com/news/2026/09/threads-expands-podcast-toolkit-for-creators-and-listeners/) — Meta Product News（0.50）
2. [Introducing Meta One: A Subscription Service With More Features and AI to Create, Connect, and Stand Out](https://about.fb.com/news/2026/09/introducing-meta-one-subscription-service-more-features-ai/) — Meta Product News（0.26）
3. [Introducing Muse: The World’s First Personal AI Agent Built for Everyone](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) — Meta Product News（0.48）
4. [Introducing Seller, an App for Facebook Marketplace Sellers](https://about.fb.com/news/2026/07/introducing-seller-app-facebook-marketplace/) — Meta Product News（0.82）
5. [AI Disclosure Checkbox, ChatGPT Attribution, and More](https://www.jonloomer.com/ai-disclosure-checkbox-chatgpt-attribution/) — Jon Loomer（0.36）

### `unclear`（3件）

1. [Connecting Real People on Facebook](https://about.fb.com/news/2026/07/connecting-real-people-on-facebook/) — Meta Product News（0.46）
2. [Lead Capture AI Agent for Instant Forms and More](https://www.jonloomer.com/lead-capture-ai-agent-instant-forms/) — Jon Loomer（0.38）
3. [Book Appointments from Instant Forms, ChatGPT Conversion Optimization, and More](https://www.jonloomer.com/instant-form-appointments-chatgpt-conversion-optimization/) — Jon Loomer（0.30）

## 人間の所見

人間確認では、次のように判断した。

- `unrelated`: Meta一般ニュースやMarketplaceなど、Meta Adsから距離のある記事は概ね妥当
- `unclear`: Instant Formsや広告関連機能を含む記事があり、保留判定として妥当
- `direct_impact`と`strategic_signal`: 両方とも掲載対象とする前提なら、両ラベル間の境界誤差は現時点で重大ではない

運用上は、分類間の細かな入れ替わりより、`unrelated`による見逃し・誤除外と、`unclear`の扱いを優先して観察する。

## 現行の本番routing仕様

本番collectorでは、source取得・形式検査・freshness・source固有のrelevance判定を通過した候補だけをJevへ渡す。Jevのchoiceは次のように扱う。

| Jev choice | 公開状態 | 扱い |
|---|---|---|
| `direct_impact` | `included` | 掲載 |
| `strategic_signal` | `included` | 掲載 |
| `unclear` | `included` | 掲載し、artifactで観察 |
| `unrelated` | `drop` | 公開せず内部stateにのみ残す |

Jevのprovider error、timeout、契約違反は`drop`へ変換しない。本番routingではcollectorを失敗させ、同runのfeed・stateの書込みとcommitを行わないため、直前の公開内容が維持される。これは独立shadow workflowのfail-openではなく、公開更新に対するfail-closed契約である。

通常のPersonal Feed collectは、火曜・金曜の週2回（08:15 MYT）にscheduled実行する。`workflow_dispatch`では`reseed_source_id`を指定して、relevance revision変更後のsource-local reseedを行える。reseed未実施のsourceは、通常collect前に検査で止まる。

本番routing artifactは、記事本文やURLを含めず、item/source ID、Jev choice、confidence、provider model、latency、error code、集計値を保持する。Jev結果を承認登録やUI上のACTION/WATCH表示に使わない。

## 残っている制約と未実装項目

- 2026-09-20の50件テストは、公開済み記事に対する分類傾向を示すもので、除外前候補全体の再現率を証明しない。
- 本番routing artifactはJevの実行結果を記録するが、現行deterministic laneとの完全なbefore/after比較、入力hash、候補laneの差分表までは持たない。
- MDで提案された「重要な不一致最大5件・一致最大2件の自動抽出」は実装していない。
- 人間ラベル15件との比較は小規模で、Jevの正答率や信頼度の保証ではない。
- `confidence`を自動閾値や自動承認の根拠には使わない。

## 費用と運用判断

- 15件実行: 約7.9K input tokens、`$0.0003`
- 50件実行: 約16K input tokens、`$0.0006`
- いずれもoutputは無料表示

費用は小さい。shadow実験の費用観測を踏まえ、個人運用の範囲で週2回の本番collectorに接続している。引き続き、artifactの分類分布、失敗、遅延、`unrelated`除外の妥当性を週末に確認する。費用または失敗率が許容できない場合は、`META_ADS_JEV_ROUTING_ENABLED=false`でdeterministic経路へ戻せる。

## 現時点の結論

1. Jev API接続、secret、kill switch、artifact生成は確認済み
2. 50件まで拡張しても分類失敗は0件
3. 人間確認では分類傾向が概ね妥当
4. 後続のoverrideにより、本番collectorの掲載routingへ接続済み
5. `direct_impact`・`strategic_signal`・`unclear`は掲載し、`unrelated`だけを除外する
6. 通常collectは火曜・金曜にscheduled実行し、Jev失敗時は公開更新を止めて直前のfeedを維持する
7. shadow結果の比較artifact拡張や自動不一致抽出は、必要性が確認できた場合の別変更とする
