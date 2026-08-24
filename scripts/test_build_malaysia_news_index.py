from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import build_malaysia_news_index as builder


SAMPLE_MARKDOWN = """【速報】

- 結論：午後は雷雨に注意が必要です。
- 何が起きた：気象局が大雨警報を出しました。
- 何が起きた：対象地域では強風も予想されています。
- 生活への影響：移動時間に余裕が必要です。
- 次アクション：出発前に道路状況を確認。
- 出典：Example News
- 出典元URL：https://example.com/weather

【生活インパクト】

- 結論：公共交通の運行計画が更新されました。
- 補足：運行時間と乗り換え案内が更新されています。

【知っておくと得】

処理対象件数：12件
要約対象件数：2件
失敗したソース一覧：なし
"""


class MalaysiaNewsIndexTests(unittest.TestCase):
    def parse_sample(self) -> builder.NewsDay:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "2026-08-20.md"
            path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
            return builder.parse_markdown(path)

    def test_parser_keeps_repeated_detail_lines(self) -> None:
        day = self.parse_sample()

        self.assertEqual(day.items[0].what_happened, "気象局が大雨警報を出しました。 対象地域では強風も予想されています。")
        self.assertEqual(day.items[0].life_impact, "移動時間に余裕が必要です。")

    def test_pickup_headline_is_semantic_and_within_15_5_width(self) -> None:
        headline = "保健省は、霧による大気汚染が広がる中で、喘息と上気道感染の患者数が急増したと発表しました。健康大臣は注意を呼びかけています。"
        item = builder.NewsItem(category="【生活インパクト】", conclusion=headline)

        shortened = builder.shorten_pickup_headline(headline)
        card = builder.render_item_card(item)

        self.assertLessEqual(builder.headline_width(shortened), 15.5)
        self.assertEqual(shortened, "煙害で呼吸器疾患が急増")
        self.assertIn(f">{shortened}</h3>", card)
        self.assertNotIn("生活への影響", card)

    def test_top_page_has_separate_summary_and_markdown_routes(self) -> None:
        page = builder.render_html([self.parse_sample()])

        self.assertIn("<h1>マレーシア生活ニュース</h1>", page)
        self.assertIn('href="./2026-08-20.html">今日のまとめを読む</a>', page)
        self.assertIn('href="./2026-08-20.html">10件すべて読む</a>', page)
        self.assertIn('href="./2026-08-20.md">Markdown版</a>', page)
        self.assertIn("今日のピックアップ3件", page)
        self.assertIn("直近7日のまとめ", page)
        self.assertIn("font-size: clamp(1.75rem, 3vw, 2.625rem)", page)
        self.assertIn("font-size: clamp(1.4rem, 2.4vw, 1.875rem)", page)
        self.assertIn("-webkit-line-clamp: 3", page)

    def test_daily_page_has_short_headline_and_summary_body(self) -> None:
        page = builder.render_daily_page(self.parse_sample())

        self.assertIn("2026年8月20日のニュースまとめ", page)
        self.assertIn('href="./index.html">← マレーシア生活ニュース</a>', page)
        self.assertIn('href="./2026-08-20.md">Markdown版</a>', page)
        self.assertIn("午後は雷雨に注意が必要です。", page)
        self.assertIn("運行時間と乗り換え案内が更新されています。", page)
        self.assertIn("出典: Example News", page)
        self.assertNotIn("daily-details", page)


if __name__ == "__main__":
    unittest.main()
