# Idea Gate Ledger

Append-only decisions produced by the `idea-gate` skill. A later evaluation must
use `supersedes` instead of editing an earlier entry.

<!-- idea-gate:20260903-business-today-news-feed -->
## BusinessTodayの公式News RSSを本番入力候補として導入する

- Record ID: `20260903-business-today-news-feed`
- Evaluated: 2026-09-03T15:38:04+08:00
- Project: Malaysia News RSS summary
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 60/100
- Confidence: medium - 7日140件の測定と同時点比較はあるが、manual_relevanceの注釈は未完了で、News feedの継続観測はDay1に留まる

### Problem Card

- Who: Malaysia News summaryを読む利用者と、そのRSS運用を保守する担当者
- When: 毎日のニュース収集で、総合BusinessToday feedの企業・市場記事が生活情報と競合するとき
- Problem: 総合feedでは企業決算・市場記事が混在し、生活に直結する燃料、ヘイズ、MyKadなどの候補を見つけるレビュー負荷が増える
- Current behavior: 既存4系統をproductionで使い、BusinessToday総合feedとNews feedはproduction外でraw shadow収集し、現行generic selectorの結果を比較している

### Evidence

- Tier: 2
- 2026-08-26から2026-09-01までのBusinessToday総合feed shadowは7日・140件を収集し、各runのrawとvalidator結果を保存した
- 7日分のRSSカテゴリを照合すると、例示した燃料2件、ヘイズ3件、MyKad遅延1件はすべてNewsカテゴリに属した
- Newsカテゴリは7日140件中121件を保持し、企業決算39件と企業人事3件も保持した一方、市場系9件のうち4件を保持した
- 2026-09-01 20:09 MYTの同時点shadowでは、総合feedはselector通過1件（日次為替レート）、News feedは0件だった
- News RSS endpointはHTTP 200・20件・validator PASSで取得できた

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 11/20 |
| `current_workaround_gap` | 8/20 |
| `evidence_strength` | 13/20 |
| `behavior_outcome_impact` | 8/15 |
| `strategic_fit_reuse` | 8/10 |
| `ui_operational_lightness` | 12/15 |
| **Total** | **60/100** |

### Alternatives

- **SHRINK - News RSSを7日間の継続shadowだけに限定する:** EXPERIMENT_ONLY (61/100). 本番feedには接続せず、同じraw保存・validator・generic selectorでNewsと総合feedを比較する
- **INTEGRATE - News RSSをproductionのBusinessToday入力として追加する:** STOP (57/100). 既存production workflowのfeed設定をNews RSSへ変更し、generic selectorと併用する
- **NO_FEATURE - BusinessToday feedを追加せず、現行4系統とgeneric selectorを維持する:** STOP (54/100). 新しいRSS依存と運用を増やさず、現行のsource setとselector改善だけで運用する

### Next Step

- Allowed action: News RSSをproductionへ接続せず、同じbaselineとgeneric selectorで残り6日を収集し、manual_relevance・event_groupを注釈して再評価する
- Revisit when: News feedのshadowが合計7日分そろい、7日中少なくとも5日でHTTP 200かつparse/validator PASSになる; 例示した生活情報のmanual_relevanceがusefulまたはunclearとして確認され、保持率が90%以上になる; 企業決算・市場予測・人事のfalse positiveがselector後に0件、または現在より明確に減少する; News feed切替で既存baselineの選択件数・日次出力・失敗時のrollbackに悪影響がない
- Override: not applied

<!-- idea-gate:20260904-business-today-news-day3 -->
## BusinessToday公式News RSSを本番source候補として継続評価し、条件達成後に導入する

- Record ID: `20260904-business-today-news-day3`
- Evaluated: 2026-09-04T21:28:05+08:00
- Project: Malaysia News RSS summary
- Rubric: 1.0.0
- Decision: **EXPERIMENT_ONLY**
- Score: 68/100
- Confidence: medium - 3日連続相当の技術成功とselector結果は再現したが、7日窓は未完了で、manual relevanceと同日総合feed比較が不足している

### Problem Card

- Who: Malaysia News summaryを読む利用者と、そのRSS運用を保守する担当者
- When: 毎日のニュース収集で、総合BusinessToday feedの企業・市場記事が生活情報と競合するとき
- Problem: 企業決算・市場・人事記事がレビュー対象や選択枠を消費し、燃料、交通、天候、行政手続きなど生活に直結する情報の発見効率を下げる
- Current behavior: 既存4系統をproductionで使い、BusinessToday News feedはproduction外で3日分のraw shadowを収集し、同一baselineとgeneric selectorで影響を確認している

### Evidence

- Tier: 2
- News feed shadowは2026-09-01、09-03、09-04の3観測日すべてでHTTP取得、parse、validatorが成功し、raw 60件を保存した
- 3日合計でselector eligibleは5件、cap後の選択は4件だった
- 選択4件はRapid KL障害、BNM OPR据え置き、Sarawak・Kedah・Perlisの人工降雨、Penang Mutiara Line工事の車線閉鎖だった
- generic noise判定に該当した企業決算9件と企業人事1件は、selector後の選択に1件も残らなかった
- Day2でNews候補追加によりbaseline記事1件がcapで押し出され、Day3ではNews候補1件がcandidate capで落ちた
- manual_relevanceとevent_groupの注釈は3日60件すべて未入力である
- 前回2026-09-03評価は60点EXPERIMENT_ONLYで、残りshadowとmanual reviewを次の許可行動とした

### Assessment

| Axis | Score |
|---|---:|
| `problem_severity_frequency` | 12/20 |
| `current_workaround_gap` | 10/20 |
| `evidence_strength` | 15/20 |
| `behavior_outcome_impact` | 10/15 |
| `strategic_fit_reuse` | 9/10 |
| `ui_operational_lightness` | 12/15 |
| **Total** | **68/100** |

### Alternatives

- **SHRINK - 残り4日のNews RSS shadowとmanual reviewだけを完了する:** EXPERIMENT_ONLY (72/100). productionには接続せず、7日で終了する同日比較と注釈だけを行って再評価する
- **INTEGRATE - News RSSを今すぐ既存production workflowへ追加する:** EXPERIMENT_ONLY (65/100). 既存source設定にNews feedを追加し、generic selectorとcapに委ねる
- **NO_FEATURE - BusinessTodayを追加せず現行4系統を維持する:** STOP (58/100). News feedの継続収集を止め、既存sourceとgeneric selectorだけで運用する

### Next Step

- Allowed action: News RSSをproductionへ接続せず、残り4観測日を同じbaselineとselectorで収集し、同日総合feed比較とmanual_relevance・event_group注釈を完了して再評価する
- Revisit when: News feed shadowが合計7観測日そろい、少なくとも6日でHTTP 200かつparse・validator PASSになる; selector eligible全件と、除外された企業決算・市場予測・人事の代表サンプルにmanual_relevanceとevent_groupが入力される; 7日で少なくとも3件のNews固有useful eventが確認され、生活情報の保持率が90%以上になる; 企業決算・市場予測・人事のselector後false positiveが0件を維持する; baseline押し出しが0件になるか、押し出された記事が重複または低価値であるとmanual reviewで確認される
- Supersedes: `20260903-business-today-news-feed`
- Override: not applied
