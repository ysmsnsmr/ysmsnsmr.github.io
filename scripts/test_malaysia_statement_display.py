from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import build_malaysia_news_index as builder
import malaysia_news_disaster_display as display


# Human expectations exercise display boundaries, not article-specific code rules.
CASES = [
    ("料金変更を発表", "大臣は12月1日から料金をRM2に変更すると発表しました。", "none"),
    ("給付を検討", "担当相は1人RM100、12月申請開始の給付案を検討すると説明しました。", "none"),
    ("洪水被害を州首相が説明", "ペラ州で洪水により100人が避難しました。", "damage"),
    ("州首相、行政改革への決意", "州首相は改革を引き続き進める決意を表明しました。", "political_statement"),
    ("担当相、連携強化を呼びかけ", "担当相は関係機関に連携の強化を求めました。", "political_statement"),
    ("議員、政党の方針を批判", "議員は政党の方針への反対を表明しました。", "political_statement"),
    ("首相、一般的な改革方針を表明", "首相はより良い行政を目指すと述べました。", "political_statement"),
    ("企業幹部が人材育成を提案", "企業幹部は人材育成の必要性を述べました。", "none"),
    ("当局が決定済みの手続きを説明", "担当者は既存の申請手順を説明しました。", "none"),
]


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article": self.ids.append(attrs.get("id"))
        if tag == "a" and attrs.get("class") == "source-link": self.sources.append(attrs["href"])


class StatementDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "2026-11-19.md"
        text = "更新時点：2026-11-19T07:00:00+08:00\n\n【暮らしに関わる更新】\n\n"
        text += "\n\n".join(f"- 見出し：{headline}\n- 概要：{summary}\n- 出典：Example\n- 出典元URL：https://example.test/{i}"
                              for i, (headline, summary, _) in enumerate(CASES, 1))
        self.path.write_text(text)
        self.response = {"articles": [dict(id=i, kind=kind, area="other" if kind == "damage" else "unclear",
                                          area_evidence="ペラ州" if kind == "damage" else "")
                                      for i, (_, _, kind) in enumerate(CASES, 1)]}
        self.articles = [dict(id=i, headline=headline, summary=summary, url=f"https://example.test/{i}")
                         for i, (headline, summary, _) in enumerate(CASES, 1)]

    def day(self):
        day = builder.parse_markdown(self.path)
        day.display_labels = display.bind_labels(self.response, self.articles)
        return day

    def test_both_groups_keep_each_article_and_source_exactly_once(self):
        day = self.day()
        self.assertEqual([i for i, _ in builder.statement_items(day)], [4, 5, 6, 7])
        self.assertEqual([i for i, _ in builder.disaster_items(day)], [3])
        for home in (True, False):
            page = builder.render_daily_page(day, is_home=home)
            parser = ArticleParser()
            parser.feed(page)
            self.assertEqual(sorted(parser.ids), [f"article-{i}" for i in range(1, 10)])
            self.assertEqual(sorted(parser.sources), [f"https://example.test/{i}" for i in range(1, 10)])
            self.assertEqual(page.count('class="statement-story"'), 4)
            self.assertIn('class="statement-more"', page)
            self.assertIn("政治・行政の発言 4件", page)
            self.assertIn("暮らしに関わる更新 4件", page)
            self.assertLess(page.index('id="category-1"'), page.index('id="statement-heading"'))
            statements = builder.render_headline_group(day, builder.statement_items(day), "statement", "政治・行政の発言")
            self.assertNotIn("料金変更を発表", statements)
            self.assertNotIn("給付を検討", statements)
            self.assertNotIn("洪水被害を州首相が説明", statements)
            self.assertNotIn("企業幹部が人材育成を提案", statements)
            self.assertLess(statements.index("州首相、行政改革"), statements.index("首相、一般的"))

    def test_one_shared_api_call_returns_both_kinds(self):
        request = Mock(return_value=SimpleNamespace(parsed=self.response, diagnostic={}))
        result = display.classify(self.path, api_key="not-a-key", request=request)
        request.assert_called_once()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["policy_version"], 2)
        self.assertEqual(len(result["labels"]), 9)
        self.assertEqual(request.call_args.kwargs["max_completion_tokens"], 6000)
        self.assertEqual(request.call_args.kwargs["timeout_seconds"], 90)
        prompt = request.call_args.kwargs["messages"][0]["content"]
        self.assertIn("not the speaker's title", prompt)
        self.assertIn("keep their disaster kind", prompt)

    def test_old_metadata_is_accepted_and_failure_keeps_regular_display(self):
        day = self.day()
        old_rows = {key: dict(row, kind="none", area="unclear", area_evidence="")
                    if row["kind"] == "political_statement" else row for key, row in day.display_labels.items()}
        self.path.with_suffix(".display.json").write_text(json.dumps(dict(
            schema_version=1, status="applied", markdown_sha256=display.document_hash(self.path.read_text()), labels=old_rows)))
        old_day = builder.parse_markdown(self.path)
        self.assertEqual(len(builder.disaster_items(old_day)), 1)
        self.assertEqual(builder.statement_items(old_day), [])
        self.path.with_suffix(".display.json").write_text('{"status":"failed"}')
        self.assertEqual(builder.parse_markdown(self.path).display_labels, {})

    def test_empty_and_small_statement_group(self):
        day = self.day()
        day.display_labels = {key: label for key, label in day.display_labels.items() if label["id"] == 7}
        page = builder.render_daily_page(day)
        self.assertEqual(page.count('class="statement-story"'), 1)
        self.assertNotIn('class="statement-more"', page)
        self.assertNotIn('class="disaster-group"', page)
        self.assertIn(".statement-story", page)  # Styles must exist without disaster labels.
        day.display_labels = {}
        self.assertNotIn('class="statement-group"', builder.render_daily_page(day))

    def test_unsafe_text_is_escaped_in_disclosure_heading(self):
        day = self.day()
        item = day.items[3]
        item.headline = '<img src=x onerror="alert(1)">'
        page = builder.render_group_story(day, item, 4, "statement")
        self.assertNotIn('<img src=x', page)
        self.assertIn('&lt;img', page)


if __name__ == "__main__":
    unittest.main()
