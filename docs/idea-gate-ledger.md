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
