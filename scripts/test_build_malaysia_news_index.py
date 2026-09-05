from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import build_malaysia_news_index as builder


SAMPLE_MARKDOWN = """【速報】

- 短見出し：雷雨・大雨に注意
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


SHIFT_MARKDOWN = """【速報】

- 短見出し：速報記事
- 概要：速報の概要です。
- 出典：速報紙（2026年8月27日）
- 出典元URL：https://example.test/速報

【生活インパクト】

- 短見出し：生活記事
- 概要：生活への影響がある概要です。
- 出典：生活紙（2026年8月27日）
- 出典元URL：https://example.test/生活

【知っておくと得】

- 短見出し：記事詳細は出典へ
- 概要：この記事の詳細は出典リンクで確認できます。
- 出典：自動車紙（2026年8月27日）
- 出典元URL：https://example.test/fallback

- 短見出し：市場記事
- 概要：市場の概要です。
- 出典：市場紙（2026年8月27日）
- 出典元URL：https://example.test/market

処理対象件数：4件
要約対象件数：4件
失敗したソース一覧：なし
"""


V3_MARKDOWN = """【速報】

- 見出し：気象局、複数地域に雷雨と大雨を警戒
- 短見出し：複数地域で雷雨に警戒
- 概要：気象局は複数地域で雷雨と大雨が予想されるとして警戒を呼びかけました。
- 出典：Example News（2026年9月3日）
- 出典元URL：https://example.test/weather

【生活インパクト】

- 見出し：当局、MyKad印刷を一時中断へ
- 短見出し：MyKad印刷を一時中断
- 概要：カード移行作業のため、印刷サービスが一時的に中断されます。
- 出典：Example News（2026年9月3日）
- 出典元URL：https://example.test/mykad
"""


SOURCE_ONLY_MARKDOWN = V3_MARKDOWN + """
【原文のみ】

- 原題：Bursa Malaysia ends higher after BNM holds OPR
- 出典：Malay Mail（2026年9月4日）
- 出典元URL：https://example.test/bursa
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
        self.assertIn("recent-headline-list", page)
        self.assertIn("font-size: clamp(1.75rem, 3vw, 2.625rem)", page)
        self.assertIn("font-size: clamp(1.4rem, 2.4vw, 1.875rem)", page)
        self.assertIn(".focus-card h3", page)
        self.assertIn("white-space: normal", page)
        self.assertIn(".focus-dek", page)
        self.assertIn("-webkit-line-clamp: 1", page)

    def test_daily_page_has_short_headline_and_summary_body(self) -> None:
        page = builder.render_daily_page(self.parse_sample())

        self.assertIn("2026年8月20日のニュースまとめ", page)
        self.assertIn('href="./index.html">← マレーシア生活ニュース</a>', page)
        self.assertIn('href="./2026-08-20.md">Markdown版</a>', page)
        self.assertIn("午後は雷雨に注意が必要です。", page)
        self.assertIn("雷雨・大雨に注意", page)
        self.assertIn("運行時間と乗り換え案内が更新されています。", page)
        self.assertIn("出典: Example News", page)
        self.assertNotIn("daily-details", page)

    def test_editorial_short_headline_is_used_without_heuristic_rewrite(self) -> None:
        day = self.parse_sample()
        self.assertEqual(day.items[0].short_headline, "雷雨・大雨に注意")
        self.assertEqual(builder.display_short_headline(day.items[0]), "雷雨・大雨に注意")

    def test_recent_day_lists_at_most_three_short_headlines(self) -> None:
        items = [
            builder.NewsItem(
                category="【速報】",
                conclusion=f"長い要約本文 {index}",
                short_headline=f"短見出し{index}",
            )
            for index in range(1, 7)
        ]
        day = builder.NewsDay(
            date="2026-08-28",
            path=Path("2026-08-28.md"),
            conclusions=[item.conclusion for item in items],
            items=items,
            category_counts={"【速報】": 6, "【生活インパクト】": 0, "【知っておくと得】": 0},
            processed_count="6",
            summarized_count="6",
            failed_sources="なし",
        )

        html = builder.render_recent_day(day)

        self.assertIn('class="recent-day-row"', html)
        self.assertIn('<ol class="recent-headline-list">', html)
        for index in range(1, 4):
            self.assertIn(f"<li>短見出し{index}</li>", html)
        for index in range(4, 7):
            self.assertNotIn(f"短見出し{index}", html)
        self.assertNotIn("長い要約本文", html)
        self.assertIn('aria-label="カテゴリ別件数"', html)
        self.assertIn('class="recent-status"', html)
        self.assertIn('href="./2026-08-28.html">その日のまとめ</a>', html)

    def test_daily_html_keeps_fallback_heading_and_source_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-08-27.md"
            path.write_text(SHIFT_MARKDOWN, encoding="utf-8")
            day = builder.parse_markdown(path)

        self.assertEqual(
            [item.short_headline for item in day.items],
            ["速報記事", "生活記事", "記事詳細は出典へ", "市場記事"],
        )
        html = builder.render_daily_page(day)
        fallback = html.index("<h3>記事詳細は出典へ</h3>")
        market = html.index("<h3>市場記事</h3>")
        self.assertLess(fallback, market)
        self.assertIn("https://example.test/fallback", html[fallback:market])
        self.assertNotIn("https://example.test/market", html[fallback:market])

    def test_v3_routes_full_headline_to_pickup_and_daily_but_short_to_recent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-09-03.md"
            path.write_text(V3_MARKDOWN, encoding="utf-8")
            day = builder.parse_markdown(path)

        first = day.items[0]
        self.assertEqual(first.headline, "気象局、複数地域に雷雨と大雨を警戒")
        self.assertEqual(first.short_headline, "複数地域で雷雨に警戒")
        self.assertEqual(builder.display_full_headline(first), first.headline)
        self.assertEqual(builder.display_short_headline(first), first.short_headline)
        self.assertIn(first.headline, builder.render_item_card(first))
        self.assertIn(first.conclusion, builder.render_item_card(first))
        self.assertIn(first.short_headline, builder.render_recent_day(day))
        self.assertIn(first.headline, builder.render_daily_page(day))

    def test_top_page_uses_compact_recent_day_rows(self) -> None:
        page = builder.render_html([self.parse_sample(), self.parse_sample()])

        self.assertIn('class="recent-day-row"', page)
        self.assertNotIn('class="recent-card"', page)
        self.assertIn("grid-template-columns: minmax(11rem, 0.8fr)", page)

    def test_source_only_entries_are_not_cards_but_remain_on_daily_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-09-04.md"
            path.write_text(SOURCE_ONLY_MARKDOWN, encoding="utf-8")
            day = builder.parse_markdown(path)

        self.assertEqual(len(day.items), 2)
        self.assertEqual(len(day.source_only_items), 1)
        self.assertEqual(day.source_only_items[0].title, "Bursa Malaysia ends higher after BNM holds OPR")
        daily = builder.render_daily_page(day)
        index = builder.render_html([day])
        self.assertIn("原文のみ", daily)
        self.assertIn("Bursa Malaysia ends higher after BNM holds OPR", daily)
        self.assertIn("https://example.test/bursa", daily)
        self.assertNotIn("Bursa Malaysia ends higher after BNM holds OPR", index)


if __name__ == "__main__":
    unittest.main()
