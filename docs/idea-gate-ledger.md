# Idea Gate Ledger

Append-only decisions produced by the `idea-gate` skill. A later evaluation
must use `supersedes` instead of editing an earlier entry.

<!-- idea-gate:20260903t103138-malaysia-news-headline-roles -->
## 短見出し・通常見出し・補足の3層分離

- Record ID: `20260903t103138-malaysia-news-headline-roles`
- Evaluated: 2026-09-03T10:31:38+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 80/100
- Confidence: high - 実画面、複数日のartifact、validator診断、現行コードが一致して問題を示している

### Problem Card

- Who: Malaysia Newsを日常的に確認する個人読者
- When: 一覧から記事を選ぶときと日別詳細ページを読むとき
- Problem: 15文字以内の見出しで主体・対象・方向が欠落し、本文と意味が食い違う
- Current behavior: 短見出しと概要を見比べ、曖昧な場合は出典を確認している

### Evidence

- Tier: 3
- 2026-08-26の画面で短見出しと記事内容のずれを確認
- 複数のscheduled artifactで見出し契約失敗とfallbackを観測
- 直近artifactでリンギット下落記事が米ドル安と読める見出しになった
- origin/mainでは同じheadline_jaを一覧と詳細ページで使用している

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 16/20 |
| `current_workaround_gap` | 15/20 |
| `evidence_strength` | 18/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 8/10 |
| `ui_operational_lightness` | 10/15 |
| **Total** | **80/100** |

### Alternatives

- **SHRINK - 詳細用見出しだけを追加:** EXPERIMENT_ONLY (74/100). 一覧の15文字見出しを維持し、日別詳細ページ用の見出しだけを追加する
- **INTEGRATE - 2見出しと既存概要を統合:** GO (83/100). 通常見出しと短見出しを生成し、既存entry_jaを補足表示として再利用する
- **NO_FEATURE - 単一見出しの上限だけを緩和:** EXPERIMENT_ONLY (67/100). JSON構造は変えず、文字数上限とpromptだけを調整する

### Next Step

- Allowed action: INTEGRATE案を既存のEditorial Entry経路とsingle renderer内で実装する
- Revisit when: v3導入後にJSON契約失敗率が増加する; 通常見出しと短見出しの意味不一致が再発する; トップの概要表示が一覧性を悪化させる
- Override: not applied

<!-- idea-gate:20260904t194217-malaysia-hide-fallback -->
## fallback記事をサイトから完全に非表示にする

- Record ID: `20260904t194217-malaysia-hide-fallback`
- Evaluated: 2026-09-04T19:42:17+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 71/100
- Confidence: medium - fallback表示の問題は反復観測されているが、完全非表示後のニュース欠落の影響は未検証

### Problem Card

- Who: Malaysia Newsを日常的に読む個人読者
- When: 日別ページや一覧から読む記事を選ぶとき
- Problem: 汎用fallbackカードが記事内容の判断に役立たず一覧を薄める
- Current behavior: 原題の手掛かりなしにリンクを開くか記事を読み飛ばす

### Evidence

- Tier: 2
- 2026-09-04 artifactで10件中1件がhard safety fallback
- 当該Bursa記事は通信成功かつJSON契約validで、数値安全検査によりfallback
- 過去のartifactでも「記事詳細は出典へ」の表示を複数回観察
- 利用者本人が出典確認だけの表示では次の行動に進みにくいと報告

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 13/20 |
| `current_workaround_gap` | 14/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 8/15 |
| `strategic_fit_reuse` | 8/10 |
| `ui_operational_lightness` | 13/15 |
| **Total** | **71/100** |

### Alternatives

- **SHRINK - 主要一覧だけから除外:** EXPERIMENT_ONLY (72/100). fallbackをトップと最近一覧から除外し、日別ページには残す
- **INTEGRATE - 原文のみ一覧へ降格:** GO (80/100). fallbackを通常カードから外し、日別ページ末尾に原題・出典・URLだけ表示する
- **NO_FEATURE - 観察を継続:** EXPERIMENT_ONLY (61/100). 現行表示を維持しfallbackの頻度と内容を記録する

### Next Step

- Allowed action: 原文のみ一覧へ降格するINTEGRATE案を既存のsingle renderer内で実装する
- Revisit when: 14回程度のscheduled runでfallback内容を観察できた; fallback記事に重要ニュースが含まれないことを確認できた; 原文のみ一覧自体が継続的なノイズになる
- Override: not applied

<!-- idea-gate:20260905-meta-ads-jon-loomer-relevance -->
## Jon Loomerの関連性判定を強化

- Record ID: `20260905-meta-ads-jon-loomer-relevance`
- Evaluated: 2026-09-05T10:25:00+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **GO**
- Score: 80/100
- Confidence: medium - カテゴリのみの契約と複数回のartifact観察は確認できているが、誤採用率と除外語の最適値はまだ測定されていない

### Problem Card

- Who: Meta Ads Personal Feedを読む個人運用者と保守する個人運用者
- When: Jon Loomer RSSのMeta Advertisingカテゴリ記事をdaily収集するとき
- Problem: カテゴリ一致だけではMeta Adsの実務更新と周辺記事を十分に区別できず、非公式ソースの件数と重要度が実際の価値以上に見える可能性がある
- Current behavior: Meta Advertisingカテゴリを機械的に採用し、公開後に利用者がタイトルと本文を個別判断する。必要なら別ソースや公式リンクを手動で確認する

### Evidence

- Tier: 2
- 現在のconfig/meta_ads_personal_feed_sources.jsonはJon Loomerにrss_category=Meta Advertisingだけを指定している
- artifact観察と利用者の報告で、更新が少ない週にJon Loomerの件数が相対的に多くなり、フィードがJon Loomerまとめサイトに偏る懸念が確認された
- 現行の関連性判定コードはカテゴリ以外のタイトル語、Meta Ads対象語、除外語の契約をJon Loomer向けには持っていない

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 15/20 |
| `current_workaround_gap` | 15/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 12/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 14/15 |
| **Total** | **80/100** |

### Alternatives

- **SHRINK - Jon Loomerのタイトル語と除外語だけを追加する:** EXPERIMENT_ONLY (78/100). 既存RSSと既存判定器を維持し、Meta Ads対象語と明らかな周辺語のfixture契約だけを追加する
- **INTEGRATE - 既存のsource relevance契約にJon Loomer専用の二群判定を統合する:** GO (81/100). RSSカテゴリ一致に加えて、タイトル・説明のMeta Ads語、対象プラットフォーム語、公式リンク発見を既存のsource-local relevanceRevisionで管理する
- **NO_FEATURE - カテゴリ判定を維持し、利用者が個別に判断する:** STOP (52/100). 取得経路と契約は変更せず、非公式ラベルと注意書きだけで誤採用リスクを利用者に委ねる

### Next Step

- Allowed action: 既存source-local契約に限定し、Jon Loomerのタイトル・説明・カテゴリを使う関連性fixture、除外fixture、relevanceRevision更新、source-local reseedを追加する実装
- Revisit when: 新契約でMeta Adsと無関係な記事が除外され、関連する記事が残ることをfixtureとartifactで確認する; Jon Loomerの件数がゼロ固定にならず、公式発見リンクの候補も失われないことを確認する; 変更後7日間のsource pipelineでmatched、relevance_excluded、retainedの推移を確認する
- Override: not applied

<!-- idea-gate:20260905t183947-malaysia-recent-compact-day-rows -->
## 直近7日を3見出し付きのコンパクトな日次行へ再設計する

- Record ID: `20260905t183947-malaysia-recent-compact-day-rows`
- Evaluated: 2026-09-05T18:39:47+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 80/100
- Confidence: medium - 複数日の本番データと実利用の観察がある一方、コンパクト行でのクリック行動はまだ未検証

### Problem Card

- Who: Malaysia Newsを日常的に確認する個人読者
- When: トップページで直近の日付と記事を短時間で見比べるとき
- Problem: 長くなった短見出しを最大5件ずつ3列カードへ詰めるため、横幅が狭く情報密度も高い
- Current behavior: 各日カードの見出しを縦に読み、関心のある日を日別ページで開く

### Evidence

- Tier: 3
- 最新生成ページでは直近6日中5日が最大5見出しまで埋まっている
- PCでは3日カードが横並びになり、最大15見出しが同じ行に入る
- Editorial Entry v3で短見出しを18〜22文字目安、最大26文字へ拡張した
- 利用者本人がv3反映後の実画面で密度上昇を観察した
- 既存の月別アーカイブには1日1行で日付を比較する表示パターンがある

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 14/20 |
| `current_workaround_gap` | 12/20 |
| `evidence_strength` | 18/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 13/15 |
| **Total** | **80/100** |

### Alternatives

- **SHRINK - 現行カードを3見出しへ縮小:** EXPERIMENT_ONLY (78/100). 3列カードは維持し、各日の表示だけを最大3見出しへ減らす
- **INTEGRATE - アーカイブ型の日次行へ統合:** GO (82/100). 1日を1本の横長行にし、日付・カテゴリ件数・短見出し3件・日別リンクを同じ行へ収める
- **NO_FEATURE - 表示を変えず観察を続ける:** EXPERIMENT_ONLY (66/100). 5見出し・3列カードを維持し、v3反映後の閲覧をさらに観察する

### Next Step

- Allowed action: INTEGRATE案について、既存データだけを使うPC・モバイルの静的比較を作り、行高と読みやすさを確認する
- Revisit when: コンパクト行で6日分が現在より短い縦幅に収まる; 26文字の短見出し3件が主体・方向を読み取れる状態で折り返す; 日付から日別ページを開く操作が現行カードより分かりにくくならない
- Supersedes: `20260905t183134-malaysia-recent-summary-density`
- Override: not applied

<!-- idea-gate:20260916t105009-meta-ads-category-simplification -->
## Replace ACTION/WATCH reader-facing lanes with official news, unofficial media, and SDK releases; keep binary relevance exclusion internally.

- Record ID: `20260916t105009-meta-ads-category-simplification`
- Evaluated: 2026-09-16T10:50:09+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 63/100
- Confidence: medium - The owner has observed the live workflow across several days, but no reader study or measured abandonment has been recorded.

### Problem Card

- Who: The owner and colleagues reading the Meta Ads Personal Feed.
- When: When scanning newly collected feed items after several days of real operation.
- Problem: The ACTION/WATCH labels are subjective and make the feed harder to interpret, while their rule maintenance creates avoidable operational work.
- Current behavior: Readers must infer the meaning of the two lanes and source provenance separately; the owner maintains lane rules, golden cases, and reseed checks.

### Evidence

- Tier: 1
- 2026-09-16 owner observation after several days of operating the Personal Feed: ACTION/WATCH appears subjective to readers and adds ongoing classification work.
- 2026-09-15 production artifact: 50 public items are already separated by source provenance and lane, showing the current feed has both concepts.

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 11/20 |
| `current_workaround_gap` | 10/20 |
| `evidence_strength` | 10/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 13/15 |
| **Total** | **63/100** |

### Alternatives

- **SHRINK - Hide ACTION/WATCH, retain their current internal values:** EXPERIMENT_ONLY (60/100). Remove lane labels and grouping from the public UI while preserving the existing lane model and keeping DROP non-public.
- **INTEGRATE - Map existing provenance and SDK type into three existing-page sections:** EXPERIMENT_ONLY (65/100). Use official/unofficial source classification plus sdk_release type to render the three requested groups without adding a page or control.
- **NO_FEATURE - Keep ACTION/WATCH and only document their meaning:** STOP (30/100). Retain lane labels and rule maintenance, adding explanatory text for readers.

### Next Step

- Allowed action: Run a bounded evidence probe or obtain an explicit owner override before changing production UI or classification behavior.
- Revisit when: At least one documented reader observation or a measured comparison shows that the three groups improve scanning or reduce confusion.; The owner explicitly overrides the Experiment Only decision with a reason and constraints.
- Override: not applied

<!-- idea-gate:20260916t113900-meta-ads-category-simplification-override -->
## Replace ACTION/WATCH reader-facing lanes with official news, unofficial media, and SDK releases; keep binary relevance exclusion internally.

- Record ID: `20260916t113900-meta-ads-category-simplification-override`
- Evaluated: 2026-09-16T11:39:00+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 63/100
- Confidence: medium - The owner has observed the live workflow across several days, but no reader study or measured abandonment has been recorded.

### Problem Card

- Who: The owner and colleagues reading the Meta Ads Personal Feed.
- When: When scanning newly collected feed items after several days of real operation.
- Problem: The ACTION/WATCH labels are subjective and make the feed harder to interpret, while their rule maintenance creates avoidable operational work.
- Current behavior: Readers must infer the meaning of the two lanes and source provenance separately; the owner maintains lane rules, golden cases, and reseed checks.

### Evidence

- Tier: 1
- 2026-09-16 owner observation after several days of operating the Personal Feed: ACTION/WATCH appears subjective to readers and adds ongoing classification work.
- 2026-09-15 production artifact: 50 public items are already separated by source provenance and lane, showing the current feed has both concepts.

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 11/20 |
| `current_workaround_gap` | 10/20 |
| `evidence_strength` | 10/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 13/15 |
| **Total** | **63/100** |

### Alternatives

- **SHRINK - Hide ACTION/WATCH, retain their current internal values:** EXPERIMENT_ONLY (60/100). Remove lane labels and grouping from the public UI while preserving the existing lane model and keeping DROP non-public.
- **INTEGRATE - Map existing provenance and SDK type into three existing-page sections:** EXPERIMENT_ONLY (65/100). Use official/unofficial source classification plus sdk_release type to render the three requested groups without adding a page or control.
- **NO_FEATURE - Keep ACTION/WATCH and only document their meaning:** STOP (30/100). Retain lane labels and rule maintenance, adding explanatory text for readers.

### Next Step

- Allowed action: Implement the existing-page integration under the recorded override, then verify source filters, classification mapping, sorting, detail views, and accessibility.
- Revisit when: A reader reports that the three groups still obscure source provenance or scanning order.; A new source type cannot be represented by the separate classification and content-type fields.
- Supersedes: `20260916t105009-meta-ads-category-simplification`
- Override: applied by yas at 2026-09-16T11:39:00+08:00
- Override reason: 個人・同僚向けで、主観的分類と維持負担を今すぐ減らすことを優先する
- Override constraints: No new screen, external source, or recurring workflow.; Keep source provenance, existing source/classification/keyword filters, and detailed-page unofficial-information notice.; Keep binary relevance exclusion so DROP items remain non-public.

<!-- idea-gate:20260916t192716-meta-ads-sdk-update-log -->
## Meta Business SDK Releasesを通常ニュースカードから独立した更新ログへ移す

- Record ID: `20260916t192716-meta-ads-sdk-update-log`
- Evaluated: 2026-09-16T19:27:16+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **STOP**
- Score: 43/100
- Confidence: low - 個人運用者の具体的な観察はあるが、SDKカードが閲覧を妨げた回数、SDK利用者の需要、代替表示の行動変化は未測定

### Problem Card

- Who: Meta Ads Personal Feedを利用する個人運用者と職場の同僚
- When: TOPページで公式・非公式の広告運用ニュースを確認するとき
- Problem: SDK releaseが通常ニュースカードに混在し、広告運用ニュースを素早く読む画面でSDK更新を同じ重みで読む必要があるように見える
- Current behavior: SDK releaseも通常ニュースと同じカードとして表示し、利用者がカードを見てSDK情報かどうかを判断する

### Evidence

- Tier: 1
- 2026-09-16に個人運用者がMeta Business SDK ReleasesはTOPページのカード形式でなくてもよいと観察した
- 現行Personal FeedはSDK Releasesを通常ニュースとは別カテゴリとして収集しているが、TOP表示での閲覧・クリック・混乱の件数は未計測

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 6/20 |
| `current_workaround_gap` | 5/20 |
| `evidence_strength` | 10/20 |
| `behavior_outcome_impact` | 5/15 |
| `strategic_fit_reuse` | 7/10 |
| `ui_operational_lightness` | 10/15 |
| **Total** | **43/100** |

### Alternatives

- **SHRINK - SDKを通常カードから除外し、既存のsource filterでのみ見つけられるようにする:** STOP (45/100). 新しい更新ログを作らず、SDK itemは保持するが通常のカード一覧には表示しない。
- **INTEGRATE - 既存TOPの末尾にSDKのコンパクトな更新ログを置く:** STOP (43/100). カードではなく、バージョン・日付・原典リンクだけの小さな一覧にする。
- **NO_FEATURE - 現行カード表示を維持する:** STOP (46/100). SDKカードの閲覧・クリック・不要感を短期間記録してから表示変更を判断する。

### Next Step

- Allowed action: SDK itemのcard表示回数、SDK原典リンクの利用、通常ニュースの閲覧阻害を7日間読み取り専用で記録する。
- Revisit when: SDKカードが通常ニュースの閲覧を妨げた具体例を3件以上確認する; SDK利用者がSDK原典リンクまたはcompact logを必要とした事例を確認する; SDKを通常カードから除外しても見逃しがないことを短期観察で確認する
- Override: not applied

<!-- idea-gate:20260916t194914-meta-ads-sdk-update-log-override -->
## Meta Business SDK Releasesを通常ニュースカードから独立した更新ログへ移す（個人運用override）

- Record ID: `20260916t194914-meta-ads-sdk-update-log-override`
- Evaluated: 2026-09-16T19:49:14+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **STOP**
- Score: 43/100
- Confidence: low - 継続した個人観察と明確なトレードオフ選択はあるが、他利用者の需要と効果測定は未実施

### Problem Card

- Who: Meta Ads Personal Feedを利用する個人運用者と職場の同僚
- When: TOPページで公式・非公式の広告運用ニュースを確認するとき
- Problem: SDK releaseが通常ニュースカードに混在し、広告運用ニュースを素早く読む画面でSDK更新を同じ重みで読む必要があるように見える
- Current behavior: SDK releaseも通常ニュースと同じカードとして表示し、利用者がカードを見てSDK情報かどうかを判断する

### Evidence

- Tier: 1
- 2026-09-16に個人運用者が、カード形式へ変更してからSDKカードへの不要感を継続して持っていると明示した
- SDKを既存filterだけに隠すと更新を見逃すリスクがあるため、TOP末尾のコンパクトな更新ログを選択した
- TOP表示での閲覧・クリック・混乱の件数は未計測

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 6/20 |
| `current_workaround_gap` | 5/20 |
| `evidence_strength` | 10/20 |
| `behavior_outcome_impact` | 5/15 |
| `strategic_fit_reuse` | 7/10 |
| `ui_operational_lightness` | 10/15 |
| **Total** | **43/100** |

### Alternatives

- **SHRINK - SDKを通常カードから除外し、既存のsource filterでのみ見つけられるようにする:** STOP (45/100). 新しい更新ログを作らず、SDK itemは保持するが通常のカード一覧には表示しない。
- **INTEGRATE - 既存TOPの末尾にSDKのコンパクトな更新ログを置く:** STOP (43/100). カードではなく、バージョン・日付・原典リンクだけの小さな一覧にする。
- **NO_FEATURE - 現行カード表示を維持する:** STOP (46/100). SDKカードの閲覧・クリック・不要感を短期間記録してから表示変更を判断する。

### Next Step

- Allowed action: overrideの制約内で、SDK itemを通常カードから除外し、既存TOP末尾に版・日付・原典リンクだけのコンパクトな更新ログを実装する。
- Revisit when: SDK原典リンクの利用またはSDK更新の見逃しを7日間観察する; SDK利用者が追加の詳細表示を要望する; 通常ニュースの閲覧性が改善しない
- Supersedes: `20260916t192716-meta-ads-sdk-update-log`
- Override: applied by yas at 2026-09-16T19:49:14+08:00
- Override reason: カード形式へ変更してからSDKカードへの不要感が継続しており、SDKをfilterだけに隠すと更新を見逃すリスクがあるため、個人・同僚向けの認知負荷を下げつつ更新を残す。
- Override constraints: SDKの取得、state、公開JSON、source filter、原典URLは維持する。; 通常ニュースカードからのみ除外し、既存TOP末尾のコンパクトな更新ログに限定する。; ログは版、日付、原典リンクのみとし、Groq生成・新規詳細ページ・新規workflowは追加しない。

<!-- idea-gate:20260916t205514-meta-ads-official-discovery-multi-origin -->
## Social Media Todayを含む複数の非公式sourceからMeta公式Business Newsを発見・昇格する

- Record ID: `20260916t205514-meta-ads-official-discovery-multi-origin`
- Evaluated: 2026-09-16T20:55:14+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 62/100
- Confidence: medium - 既存のJon Loomer昇格経路は検証済みだが、Social Media Todayでの有効リンク件数と利用効果は未測定

### Problem Card

- Who: Meta Ads Personal Feedを使う個人運用者と同僚
- When: 非公式RSS記事の中でMeta公式Business Newsへのリンクが示されたとき
- Problem: 現在はJon Loomer Digitalだけが公式リンクの抽出・検証・昇格対象であり、Social Media Today経由で見つかる同種の公式発表は公式として独立表示されない
- Current behavior: 利用者は非公式記事を読み、公式リンクがあれば手動で開く。Jon Loomer由来だけは既存の昇格機能により公式記事として表示される

### Evidence

- Tier: 1
- 既存mainにはJon Loomer DigitalをfromSourceIdとしてMeta for Business Newsを検証・公式昇格する実装と固定テストがある
- 2026-08の運用で、非公式記事から見つかるMeta for Business News原本は価値が高いと利用者が確認した
- Social Media TodayのRSS本文に同じ形式の有効リンクが含まれる頻度は未観測

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 10/20 |
| `current_workaround_gap` | 8/20 |
| `evidence_strength` | 10/20 |
| `behavior_outcome_impact` | 9/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 15/15 |
| **Total** | **62/100** |

### Alternatives

- **SHRINK - Social Media TodayだけをJon Loomerと同じ単一発見元として追加する:** STOP (56/100). 複数sourceの汎用契約にはせず、Social Media Today向けの専用発見元を追加する。
- **INTEGRATE - 複数originを宣言できる既存の公式発見経路へ統合する:** EXPERIMENT_ONLY (62/100). 発見元を配列で宣言し、同一公式URLを一度だけ取得・表示し、すべての発見元を証跡として保持する。
- **NO_FEATURE - Social Media Todayの公式リンクを手動確認する:** STOP (49/100). RSS記事からの公式リンク昇格は増やさず、利用者が非公式記事を開いて必要時だけ原本を確認する。

### Next Step

- Allowed action: Social Media Todayの固定RSS fixtureを用い、公式Business Newsリンクを安全に抽出でき、重複URLが一度だけ検証・表示されることを確認する読み取り専用の実証を1回行う。
- Revisit when: Social Media Today RSSから有効な公式Business Newsリンクを少なくとも1件確認する; 同一公式URLがJon LoomerとSocial Media Todayの両方から検出されるfixtureで、重複なし・証跡保持を確認する; 公式原本を独立表示したことが利用者の確認手順を短縮した事例を確認する
- Override: not applied

<!-- idea-gate:20260916t205709-meta-ads-official-discovery-multi-origin-probe -->
## Social Media Todayを含む複数の非公式sourceからMeta公式Business Newsを発見・昇格する

- Record ID: `20260916t205709-meta-ads-official-discovery-multi-origin-probe`
- Evaluated: 2026-09-16T20:57:09+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 72/100
- Confidence: medium - Social Media Today RSSで有効な公式リンク5件を確認できたが、継続的な検出頻度と利用者の確認手順短縮は未測定

### Problem Card

- Who: Meta Ads Personal Feedを使う個人運用者と同僚
- When: 非公式RSS記事の中でMeta公式Business Newsへのリンクが示されたとき
- Problem: 現在はJon Loomer Digitalだけが公式リンクの抽出・検証・昇格対象であり、Social Media Today経由で見つかる同種の公式発表は公式として独立表示されない
- Current behavior: 利用者は非公式記事を読み、公式リンクがあれば手動で開く。Jon Loomer由来だけは既存の昇格機能により公式記事として表示される

### Evidence

- Tier: 2
- 既存mainにはJon Loomer DigitalをfromSourceIdとしてMeta for Business Newsを検証・公式昇格する実装と固定テストがある
- 2026-08の運用で、非公式記事から見つかるMeta for Business News原本は価値が高いと利用者が確認した
- 2026-09-16の読み取り専用probeで、Social Media TodayのRSSは20記事を解析し、許可host・HTTPS・/business/news/の制約を満たす重複なしのMeta公式Business Newsリンクを5件検出した
- このprobeはstate、公開feed、artifactを更新していない

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 12/20 |
| `current_workaround_gap` | 10/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 15/15 |
| **Total** | **72/100** |

### Alternatives

- **SHRINK - Social Media Todayだけを個別の公式発見元として追加する:** EXPERIMENT_ONLY (66/100). 複数origin契約にせず、Social Media Today用の個別経路を追加する。
- **INTEGRATE - 複数originを宣言できる既存の公式発見経路へ統合する:** EXPERIMENT_ONLY (72/100). 発見元を配列で宣言し、同一公式URLを一度だけ取得・表示し、発見元を証跡として保持する。
- **NO_FEATURE - Social Media Todayの公式リンクを手動確認する:** STOP (56/100). RSS記事からの公式リンク昇格は増やさず、利用者が非公式記事を開いて必要時だけ原本を確認する。

### Next Step

- Allowed action: 明示overrideがある場合に限り、複数origin宣言・URL単位の重複排除・発見元証跡の保持を実装し、固定fixtureとsource-local reseedで検証する。
- Revisit when: 公式原本を独立表示したことで利用者の確認手順が短縮した事例を確認する; Social Media Todayの有効リンク検出が複数回継続する; 同一公式URLを複数originが示した際に発見元証跡が有用だと確認する
- Supersedes: `20260916t205514-meta-ads-official-discovery-multi-origin`
- Override: not applied

<!-- idea-gate:20260916t210000-meta-ads-official-discovery-multi-origin-override -->
## Social Media Todayを含む複数の非公式sourceからMeta公式Business Newsを発見・昇格する

- Record ID: `20260916t210000-meta-ads-official-discovery-multi-origin-override`
- Evaluated: 2026-09-16T21:00:00+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 72/100
- Confidence: medium - Social Media Today RSSで有効な公式リンクを繰り返し確認できたが、公式原本の独立表示による確認手順短縮は未測定

### Problem Card

- Who: Meta Ads Personal Feedを使う個人運用者と同僚
- When: 非公式RSS記事の中でMeta公式Business Newsへのリンクが示されたとき
- Problem: 現在はJon Loomer Digitalだけが公式リンクの抽出・検証・昇格対象であり、Social Media Today経由で見つかる同種の公式発表は公式として独立表示されない
- Current behavior: 利用者は非公式記事を読み、公式リンクがあれば手動で開く。Jon Loomer由来だけは既存の昇格機能により公式記事として表示される

### Evidence

- Tier: 2
- 既存mainにはJon Loomer DigitalをfromSourceIdとしてMeta for Business Newsを検証・公式昇格する実装と固定テストがある
- 2026-08の運用で、非公式記事から見つかるMeta for Business News原本は価値が高いと利用者が確認した
- 2026-09-16の読み取り専用probeで、Social Media TodayのRSSは20記事を解析し、許可host・HTTPS・/business/news/の制約を満たす重複なしのMeta公式Business Newsリンクを5件検出した
- 指定されたCreator partnership記事に含まれる公式URLは、Social Media TodayのRSS本文でも1件から検出できた

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 12/20 |
| `current_workaround_gap` | 10/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 15/15 |
| **Total** | **72/100** |

### Alternatives

- **SHRINK - Social Media Todayだけを個別の公式発見元として追加する:** EXPERIMENT_ONLY (66/100). 複数origin契約にせず、Social Media Today用の個別経路を追加する。
- **INTEGRATE - 複数originを宣言できる既存の公式発見経路へ統合する:** EXPERIMENT_ONLY (72/100). 発見元を配列で宣言し、同一公式URLを一度だけ取得・表示し、発見元を証跡として保持する。
- **NO_FEATURE - Social Media Todayの公式リンクを手動確認する:** STOP (56/100). RSS記事からの公式リンク昇格は増やさず、利用者が非公式記事を開いて必要時だけ原本を確認する。

### Next Step

- Allowed action: overrideの制約内で、複数origin宣言・URL単位の重複排除・発見元証跡の保持を実装し、固定fixtureとsource-local reseedで検証する。
- Revisit when: 公式原本の独立表示による確認手順の短縮を観察する; Social Media Todayの有効リンク検出を複数回観察する
- Supersedes: `20260916t205709-meta-ads-official-discovery-multi-origin-probe`
- Override: applied by yas at 2026-09-16T21:00:00+08:00
- Override reason: 個人・同僚向けの実用性を優先して実装する
- Override constraints: 既存のHTTPS・許可host・/business/news/・canonical metadata・日付検証を弱めない。; 新しいUI、source、外部API、定期workflowを追加しない。; 同一の公式URLは1回だけ取得・state・feedへ保存し、発見元はmatchEvidenceへすべて残す。; Social Media TodayとJon Loomerの固定fixture、重複URL、片方の公式ページ取得失敗を検証する。

<!-- idea-gate:20260919t111534-meta-ads-jev-relevance-shadow -->
## 既存の人間ラベルを使うJev Ads Relevance artifact-only shadow probe

- Record ID: `20260919t111534-meta-ads-jev-relevance-shadow`
- Evaluated: 2026-09-19T11:15:34+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 76/100
- Confidence: medium - 既存ラベルとURLは再現できたが、Jevの実測結果、provider保持条件、credential境界はまだ未検証

### Problem Card

- Who: Meta Ads Personal Feedを保守する個人運用者
- When: 記事のMeta広告関連度をACTION・WATCH・DROP候補へ振り分ける前に意味的な補助信号を得たいとき
- Problem: 14日間の手動レビューは1件約15分、手戻り率ほぼ100%で中断され、意味的な関連度確認を継続できなかった
- Current behavior: keywordとsource固有ruleでincludedまたはdropを決め、曖昧な意味判断は人間が記事ごとに確認する

### Evidence

- Tier: 2
- 過去の人間レビューは1件約15分、手戻り率ほぼ100%となり途中で断念した
- main履歴の15件golden caseにはACTION・WATCH・DROPの人間分類が残っている
- MuseはWATCH、Jon LoomerのChatGPT Adsは訂正後DROPという既知edge caseがある
- 現行stateで15件すべてをsource ID、URL、fingerprintへ機械的に再結合できた

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 15/20 |
| `current_workaround_gap` | 16/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 8/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 13/15 |
| **Total** | **76/100** |

### Alternatives

- **SHRINK - 同じ15件で既存rule-based baselineだけを再計測する:** EXPERIMENT_ONLY (71/100). 外部semantic modelを使わず、現行keyword・source ruleの誤分類だけを固定fixtureで可視化する
- **INTEGRATE - Jevをproduction routingへ直接統合する:** DISQUALIFIED (not scored). 収集時にJev判定を実行し、公開対象またはDROPを自動決定する
- **NO_FEATURE - 現行ruleと人間確認だけを維持する:** STOP (56/100). semantic sensorを追加せず、必要な記事だけを都度人間が確認する

### Next Step

- Allowed action: API接続とproduction変更を行わず、既存15件のhuman laneをsource ID、URL、fingerprint由来のstable item IDへ結合した固定fixtureと、その完全性を検証するテストだけを追加する
- Revisit when: fixtureの15件すべてが元artifactのURLと既存human laneへ推測なしで結合できる; Jevの公式provider保持条件、学習利用、credential境界を確認できる; 固定model IDとversioned question setを使うartifact-only runnerの契約を別Checkpointで確定する
- Override: not applied

<!-- idea-gate:20260919t120104-meta-ads-jev-artifact-runner -->
## 固定15件を使うJev Ads Relevance artifact-only runner

- Record ID: `20260919t120104-meta-ads-jev-artifact-runner`
- Evaluated: 2026-09-19T12:01:04+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 74/100
- Confidence: medium - 比較対象と入力境界は確定したが、Jevの実測精度・障害率・providerの具体的な保持期間は未観測である

### Problem Card

- Who: Meta Ads Personal Feedを保守する個人運用者
- When: 既存の15件人間分類とsemantic modelの一致・不一致を一度だけ確認したいとき
- Problem: keywordとsource固有ruleだけでは曖昧な関連度判断の妥当性を測れず、productionへ接続する前の比較証跡もない
- Current behavior: 固定fixtureに人間分類を保持し、semantic判定は実行せずに手動確認だけを行う

### Evidence

- Tier: 2
- main上のhuman_labels.jsonはACTION/WATCH/DROP各5件の人間確認済み15件を固定している
- 前CheckpointではAPI接続を行わないfixture-only実装に限定され、runner契約の確定が再評価条件だった
- Jevの公開API資料は固定model IDとchoice questionを用いる回答形式を示し、providerのprivacy policyは入力を学習・fine-tuneに使わない一方、保持期間を合理的に必要な期間としか定めていない
- fixtureに入るのは公開URL、公開タイトル、短いsourceContextと人間分類であり、credential・production state・response本文は入力に含めない

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 15/20 |
| `current_workaround_gap` | 15/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 8/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 12/15 |
| **Total** | **74/100** |

### Alternatives

- **SHRINK - 既存rule-based分類だけを15件fixtureで再計測する:** EXPERIMENT_ONLY (70/100). 外部semantic providerを使わず、既存分類とhuman laneの差だけを可視化する
- **INTEGRATE - Jevをdaily collectorの自動lane判定へ直接統合する:** DISQUALIFIED (not scored). Jevの出力をACTION/WATCH/DROPまたは公開判定に直接用いる
- **NO_FEATURE - Jev比較を実行せず、既存の人間確認を続ける:** EXPERIMENT_ONLY (62/100). 外部providerへの送信を避け、必要な記事だけを人間が判断する

### Next Step

- Allowed action: 固定15件のみを読み、--live明示時だけJev APIを呼び、public入力の最小化・credential非保存・raw response非保存・production非接続を機械的に検証するartifact-only runnerを1本だけ実装する
- Revisit when: 15件のartifactを人間laneと比較し、ACTIONからDROPへの不一致を個別に確認する; transport/validation失敗がartifactに安全な分類だけで残り、raw response・credential・fixture本文が出力されないことを確認する; production統合の検討は比較結果、provider保持条件、明示的な人間レビューを別途揃えてから再評価する
- Supersedes: `20260919t111534-meta-ads-jev-relevance-shadow`
- Override: not applied

<!-- idea-gate:20260920t110645-meta-ads-jev-production-shadow -->
## Jevを本番候補へ接続し、判定をartifact-onlyで継続観察する

- Record ID: `20260920t110645-meta-ads-jev-production-shadow`
- Evaluated: 2026-09-20T11:06:45+08:00
- Project: Meta Ads Personal Feed
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 73/100
- Confidence: medium - API実行と15件の分類は直接確認したが、実際の本番候補に対する安定性、費用、遅延、判定分布はまだ観測していない

### Problem Card

- Who: Meta Ads Personal Feedを個人・同僚向けに運用する本人
- When: 本番collectorが新しい公式・非公式候補を収集し、関連性判定の挙動を確認するとき
- Problem: 固定fixtureの手動実行だけでは実際の候補分布に対するJevの判定、失敗、遅延を継続観測できず、追加の人間ラベル検証は主観性と運用負担が大きい
- Current behavior: deterministicなfreshness・source relevanceルールで掲載対象を決め、Jevは固定15件をローカルで一度だけartifact-only実行し、本番routingには使用していない

### Evidence

- Tier: 2
- 2026-09-20に固定15件をjev-1.13.0で実行し、15/15分類成功、API失敗0件を確認した
- 人間ラベルとの一致は8/15、不一致は7/15で、ACTIONからDROPへの重大な不一致は0件だった
- 利用者は人間ラベル自体も小規模かつ主観的で、追加の正解判定プロセスは時間に見合わないと判断した
- 既存Personal Feedは複数日のartifact観察を運用しており、source別relevance ruleの修正を繰り返してきた
- Jev runnerはtitleと最大4000文字のsourceContextだけを送信し、credential・raw provider response・顧客情報をartifactへ保存しない
- TypeSafe APIアクセスとjev-1.13.0の実行成功を確認済みである

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 14/20 |
| `current_workaround_gap` | 15/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 10/15 |
| **Total** | **73/100** |

### Alternatives

- **SHRINK - 本番候補を明示指定する手動artifact-only workflow:** EXPERIMENT_ONLY (71/100). scheduleを追加せず、workflow_dispatchで本番候補を最大15件だけJevへ送り、比較なしの観測artifactを生成する
- **INTEGRATE - 本番collectorと独立した期間限定Jev shadow workflow:** EXPERIMENT_ONLY (73/100). 既存stateまたはfeedの公開情報だけを読み、Jev結果を非公開artifactへ保存する。失敗しても収集・公開・stateを変更しない
- **NO_FEATURE - deterministic relevance ruleと手動artifact観察を維持:** STOP (59/100). Jevを本番へ接続せず、現在のsource別ルールと必要時のローカルfixture実行だけを続ける

### Next Step

- Allowed action: ユーザーoverrideにより、本番routingから独立した期間限定Jev shadowを実装できる。最初はworkflow_dispatchで1回成功させ、その後もartifact-only、fail-open、件数上限、固定model/question version、kill switch、費用・遅延統計を維持する
- Revisit when: 本番候補で少なくとも5回のartifactを生成し、API成功率、判定分布、latency、実行件数を確認する; Jev障害時もcollector、state、公開feed、Pages更新が停止しないことを確認する; 送信項目がtitleとbounded sourceContextだけで、raw provider responseとsecretが保存されないことを確認する; 自動DROP・自動掲載・Hard validator置換を検討する場合は別Idea Gateで再評価する; API費用または失敗率が個人運用で許容できない場合はkill switchで停止する
- Supersedes: `20260919t120104-meta-ads-jev-artifact-runner`
- Override: applied by yas at 2026-09-20T11:06:45+08:00
- Override reason: 人間ラベルも15件の主観的基準であり、どちらが正しいかを追加検証する時間とプロセスの負担が価値に見合わないため、既存artifact観察を根拠に本番候補でshadow観測を続けたい
- Override constraints: Jev結果を掲載、DROP、承認、公開停止へ使用しない; Jev失敗をcollectorと公開workflowへ伝播させない; titleとbounded sourceContext以外を送信しない; raw provider response、secret、顧客情報を保存しない; 固定model IDとquestion version、件数上限、kill switchを維持する; 自動routingは別評価なしに追加しない

<!-- idea-gate:20260916t101916-malaysia-selection-observation -->
## 選定前から最終決定までのselection observation artifact

- Record ID: `20260916t101916-malaysia-selection-observation`
- Evaluated: 2026-09-16T10:19:16+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 89/100
- Confidence: high - 直近3日分の本番artifactと選定コードを突き合わせ、情報が失われる位置と既存artifact経路を確認した

### Problem Card

- Who: Malaysia Newsの品質を日常的に確認する運用者
- When: scheduled run後に特定テーマの記事が選定されなかった理由を確認するとき
- Problem: artifactには最終選定記事しか残らず、選定前候補の有無と除外段階を後から検証できない
- Current behavior: selected_itemsと生成結果だけを確認し、未選定の記事は当時のRSSを再現できないため調査を断念する

### Evidence

- Tier: 3
- 2026-09-14から16日の3件のscheduled artifactで、選定済みヘイズ記事は確認できたが未選定ヘイズ記事の有無は復元できなかった
- 現行select_itemsはscore、重複、除外、noise gate、各capをメモリ上で処理し、selected_items.jsonには最終selectedだけを書き出している
- artifact uploadはrun directory全体を保存するため、追加JSONは既存のartifact経路へ自然に統合できる

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 16/20 |
| `current_workaround_gap` | 17/20 |
| `evidence_strength` | 18/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 15/15 |
| **Total** | **89/100** |

### Alternatives

- **SHRINK - 除外記事だけを観察するJSON:** GO (81/100). 最終selected以外の記事と最初の除外理由だけを保存する
- **INTEGRATE - 既存run directoryへ全選定段階の観察JSONを統合:** GO (89/100). RSS記事ごとに最終結果と決定段階を保存し、既存artifact uploadへ含める
- **NO_FEATURE - 必要時にRSSを再取得して手動比較:** STOP (56/100). artifactは増やさず、後日RSSを再取得して候補を推定する

### Next Step

- Allowed action: 既存select_itemsの決定を観察専用で記録し、selection_observation.jsonをrun directoryへ出力する
- Revisit when: artifactサイズまたはGitHub Actionsの実行時間が実用上問題になる; 候補数が増えても除外理由が運用判断に使われない; 選定ロジック変更なしに観察JSONが選定結果を変える
- Override: not applied

<!-- idea-gate:20260920t100000-malaysia-jev-selector-shadow -->
## JevによるMalaysia News selector shadow評価

- Record ID: `20260920t100000-malaysia-jev-selector-shadow`
- Evaluated: 2026-09-20T10:00:00+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 85/100
- Confidence: medium - 選定観察の欠落とJevの同一repository内の通信実績は確認できるが、Malaysia Newsの記事分類への適合性は未検証である

### Problem Card

- Who: Malaysia Newsの選定品質を確認・改善する運用者
- When: scheduled run後に、記事が選定・除外された理由と意味上の妥当性を確認するとき
- Problem: 現行selectorとvalidatorは決定的な規則中心で、記事の意味を要する不一致を比較・分類する仕組みがない
- Current behavior: selected_itemsとartifactを手動で読み、未選定記事は選定時点の候補や意味判断を十分に比較できない

### Evidence

- Tier: 3
- 2026-09-14から16日の3件のMalaysia News artifactで、未選定記事の有無と除外理由を後から復元できなかった
- 2026-09-16にselection_observation.jsonを追加する実装を専用ブランチへ記録し、候補と決定段階を追跡する土台を作った
- 同一repositoryのMeta Ads TrackerではJevをartifact-only shadowとして50件実行し、失敗0件・production effectなしを確認している

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 16/20 |
| `current_workaround_gap` | 16/20 |
| `evidence_strength` | 17/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 14/15 |
| **Total** | **85/100** |

### Alternatives

- **SHRINK - 選定観察JSONだけを追加して人手で候補を確認する:** GO (81/100). Jevを使わず、選定前候補と決定段階だけをartifactへ残す
- **INTEGRATE - 既存Malaysia workflowにJev artifact-only shadowを統合する:** GO (85/100). 同一の選定候補をJevへ送り、現行selector・hard validatorとの不一致をartifactにのみ保存する
- **NO_FEATURE - 不一致が疑われる日だけ手動でRSSと公開結果を比較する:** STOP (59/100). 新しい通信やartifactを追加せず、必要時だけ候補を再調査する

### Next Step

- Allowed action: 公開経路に接続しないJev selector shadowを実装し、現行selector・hard validator・Jevの決定を同一artifactへ記録する
- Revisit when: Jev APIのMalaysia News向け通信またはJSON契約が安定しない; shadow artifactの不一致が運用判断に使われない; Jevの判定がselectorやvalidatorの改善候補を示せない; artifactのコストまたは実行時間がscheduled運用に不釣り合いになる
- Override: not applied

<!-- idea-gate:20260920t160000-malaysia-haze-practical-value -->
## 空気質・ヘイズ記事をfinal_noise_gateの一律除外から保護する

- Record ID: `20260920t160000-malaysia-haze-practical-value`
- Evaluated: 2026-09-20T16:00:00+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 86/100
- Confidence: high - 同一runのselector段階、Jev判定、除外理由をartifactで照合でき、原因箇所もコードで特定できる

### Problem Card

- Who: Malaysia Newsを日常的に確認する個人読者
- When: 日次選定後に生活影響のある空気質記事を読むとき
- Problem: 実データで生活影響ありと判断できるヘイズ記事5件がfinal_noise_gateで一律除外された
- Current behavior: selection_observationとJev shadowの不一致を確認し、必要なら出典を個別に調べている

### Evidence

- Tier: 3
- 2026-09-20のJev shadow artifactでヘイズ・空気質記事5件がfinal_noise_gateから除外され、direct_life_impactと判定された
- 同artifactで通信失敗0、selected記事のunrelated_noiseなしを確認した
- 既存has_practical_life_valueはweather、flood、transport等を扱うがhaze・air qualityを扱っていない
- selection_observationで5件すべてが候補段階まで到達した後にfinal_noise_gateで除外されている

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 16/20 |
| `current_workaround_gap` | 15/20 |
| `evidence_strength` | 18/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 14/15 |
| **Total** | **86/100** |

### Alternatives

- **SHRINK - 今回観測した5件だけを追加候補として扱う:** EXPERIMENT_ONLY (79/100). 今回のヘイズ記事だけを個別fixtureとして保護し、一般化した生活影響判定は変更しない
- **INTEGRATE - 空気質・健康リスクを既存の生活影響判定へ統合する:** GO (87/100). 既存has_practical_life_valueに空気質・ヘイズの汎用シグナルを加え、final_noise_gateの一般判定を再利用する
- **NO_FEATURE - Jev shadowだけ継続し、selectorは変更しない:** EXPERIMENT_ONLY (73/100). 次のartifactを待ってから判断し、現行final_noise_gateの除外を維持する

### Next Step

- Allowed action: 既存has_practical_life_valueへ空気質・ヘイズの汎用シグナルを追加し、golden fixtureとself-testで検証する
- Revisit when: 空気質記事が誤って大量掲載される; 同一ヘイズ事象のcanonical deduplicationが機能しない; 非生活影響の大気・環境記事まで実質的に保護される
- Override: not applied

<!-- idea-gate:20260920t170519-malaysia-jev-editorial-budget -->
## 固定カテゴリ枠を廃止し、Jev判定後の編集予算へ置き換える

- Record ID: `20260920t170519-malaysia-jev-editorial-budget`
- Evaluated: 2026-09-20T17:05:19+08:00
- Project: ysmsnsmr.github.io / Malaysia News
- Rubric: 1.0.0
- Decision: **GO**
- Score: 87/100
- Confidence: high - 同一日のbefore/after artifact、selectorの決定段階、Jevの成功した実測が揃っており、固定枠が意味判定より先に効く原因を再現できている

### Problem Card

- Who: Malaysia Newsを日常的に確認する個人読者と運用者
- When: 日次選定で、生活影響のある記事がカテゴリ上限や合計上限で押し出されるとき
- Problem: 固定カテゴリ枠がJevの意味判定より先に働くため、生活影響記事が選定対象から外れ、記事の意味に基づく優先順位を公開結果へ反映できない
- Current behavior: selection_observationとJev shadow artifactを手動照合し、押し出された記事を個別のdeterministic rule修正で救済している

### Evidence

- Tier: 3
- 2026-09-20の初回Jev shadow artifactで、生活影響のあるヘイズ・空気質記事5件がfinal_noise_gateで除外された
- 同日、空気質を既存生活影響判定へ統合した再実行で5件はfinal_noise_gateを通過したが、2件が知っておくと得カテゴリ上限8件でcategory_capとなった
- 再実行ではヘイズ関連4件が選定され、残る2件はsemantic relevanceではなく固定カテゴリ枠により未選定だった
- Phase 1 Jev shadowは30件を分類し、通信失敗0件、productionEffect=falseで記事ごとのbaseline不一致を記録できている
- 既存selectorはcategory_limitsとoverall selector cap 15をJev実行より前に適用している

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 17/20 |
| `current_workaround_gap` | 16/20 |
| `evidence_strength` | 19/20 |
| `behavior_outcome_impact` | 13/15 |
| `strategic_fit_reuse` | 10/10 |
| `ui_operational_lightness` | 12/15 |
| **Total** | **87/100** |

### Alternatives

- **SHRINK - カテゴリ上限だけを撤廃する:** GO (83/100). 知っておくと得などの固定カテゴリ枠だけを外し、合計15件上限と既存selector順序は維持する
- **INTEGRATE - cap前候補をJev判定後の編集予算で選定する:** GO (87/100). 既存のhard safety、鮮度、重複排除を通過した候補をJevで優先順位化し、固定カテゴリ枠ではなく後段の編集予算で公開候補を決める。Jev障害時は旧selectorへfail-openする
- **NO_FEATURE - 現行capを維持し、個別ルール修正を続ける:** EXPERIMENT_ONLY (65/100). Jevは観察だけに留め、固定枠による除外は記事種別ごとのdeterministic rule追加で対応する

### Next Step

- Allowed action: 既存selectorのcap前候補をartifactへ出力し、Jev成功時だけ後段の編集予算でrouted selected JSONを生成する。Jev routing kill switchがfalseまたは通信・契約失敗なら既存selector JSONをそのまま使う
- Revisit when: Jev routingによるselected記事数またはsource-only記事数が日次ページの可読性を明確に損なう; Jev障害時に旧selector-only JSONへfail-openできない; direct_life_impactの保護と重複排除が両立しない; Jevのunrelated_noise判定が人間確認で繰り返し誤りと分かる
- Supersedes: `20260920t100000-malaysia-jev-selector-shadow`
- Override: not applied
