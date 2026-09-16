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
