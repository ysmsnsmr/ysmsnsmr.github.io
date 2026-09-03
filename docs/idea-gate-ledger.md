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
