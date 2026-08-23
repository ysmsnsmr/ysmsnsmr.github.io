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

    def test_top_page_has_separate_summary_and_markdown_routes(self) -> None:
        page = builder.render_html([self.parse_sample()])

        self.assertIn("<h1>マレーシア生活ニュース</h1>", page)
        self.assertIn('href="./2026-08-20.html">今日のまとめを読む</a>', page)
        self.assertIn('href="./2026-08-20.html">10件すべて読む</a>', page)
        self.assertIn('href="./2026-08-20.md">Markdown版</a>', page)
        self.assertIn("今日のピックアップ3件", page)
        self.assertIn("直近7日のまとめ", page)

    def test_daily_page_has_expected_heading_and_full_item_details(self) -> None:
        page = builder.render_daily_page(self.parse_sample())

        self.assertIn("2026年8月20日のニュースまとめ", page)
        self.assertIn('href="./index.html">← マレーシア生活ニュース</a>', page)
        self.assertIn('href="./2026-08-20.md">Markdown版</a>', page)
        self.assertIn("何が起きた", page)
        self.assertIn("生活への影響", page)
        self.assertIn("次アクション", page)


if __name__ == "__main__":
    unittest.main()
