from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import build_malaysia_news_index as builder
import malaysia_news_disaster_display as display


CASES = [
    ("他地域の洪水で避難", "ケダ州で住宅が浸水しました。", "damage", "other", "ケダ州"),
    ("シャーアラムの道路が冠水", "シャーアラムの道路が通行止めになりました。", "disruption", "klang_valley", "シャーアラム"),
    ("KLに警報", "クアラルンプールに大雨警報が発表されました。", "warning", "klang_valley", "クアラルンプール"),
    ("洪水避難者が増加", "ペラ州で避難が続いています。", "disruption", "other", "ペラ州"),
    ("治水に予算を配分", "長期的な治水政策を発表しました。", "none", "unclear", ""),
    ("救助艇を点検", "防災機関が装備の点検を行いました。", "none", "unclear", ""),
]


def markdown():
    return "更新時点：2026-11-16T07:31:00+08:00\n\n【暮らしに関わる更新】\n\n" + "\n\n".join(
        f"- 見出し：{headline}\n- 概要：{summary}\n- 出典：Example\n- 出典元URL：https://example.test/{i}"
        for i, (headline, summary, *_) in enumerate(CASES, 1)
    )


def response():
    return {"articles": [dict(id=i, kind=kind, area=area, area_evidence=evidence)
                         for i, (_, _, kind, area, evidence) in enumerate(CASES, 1)]}


class DisasterDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "2026-11-16.md"
        self.path.write_text(markdown(), encoding="utf-8")
        self.articles = [dict(id=i, headline=headline, summary=summary, url=f"https://example.test/{i}")
                         for i, (headline, summary, *_) in enumerate(CASES, 1)]

    def label_day(self):
        tags = display.bind_labels(response(), self.articles)
        report = dict(schema_version=1, status="applied", labels=tags,
                      markdown_sha256=display.document_hash(markdown()))
        self.path.with_suffix(".display.json").write_text(json.dumps(report), encoding="utf-8")
        return builder.parse_markdown(self.path)

    def test_strict_schema_and_exhaustive_binding(self):
        self.assertEqual(display.schema_error(response()), "")
        for mutation in ("extra", "missing", "duplicate", "unknown", "unfounded"):
            with self.subTest(mutation=mutation):
                result = response()
                if mutation == "extra": result["articles"][0]["extra"] = True
                if mutation == "missing": result["articles"].pop()
                if mutation == "duplicate": result["articles"][0]["id"] = 2
                if mutation == "unknown": result["articles"][0]["kind"] = "flood_budget"
                if mutation == "unfounded": result["articles"][1]["area_evidence"] = "Putrajaya"
                with self.assertRaises(ValueError): display.bind_labels(result, self.articles)

    def test_no_klang_priority_without_explicit_area_evidence(self):
        result = response()
        result["articles"][1]["area_evidence"] = ""
        self.assertEqual(display.schema_error(result), "display_missing_area_evidence")

    def test_group_preserves_all_articles_and_original_ids(self):
        day = self.label_day()
        self.assertEqual([i for i, _ in builder.disaster_items(day)], [2, 3, 4, 1])
        for home in (True, False):
            page = builder.render_daily_page(day, is_home=home)
            self.assertIn("自然災害関連", page)
            self.assertIn("関連ニュースをさらに読む 1件", page)
            self.assertEqual(page.count('class="disaster-story"'), 4)
            self.assertEqual(page.count('class="daily-item"'), 6)
            for i in range(1, 7):
                self.assertEqual(page.count(f'id="article-{i}"'), 1)
                self.assertEqual(page.count(f'href="https://example.test/{i}"'), 1)
            regular = builder.render_daily_sections(day).split('class="daily-category"', 1)[1]
            self.assertIn("治水に予算を配分", regular)
            self.assertIn("救助艇を点検", regular)
            self.assertNotIn("シャーアラムの道路が冠水", regular)
            self.assertIn("暮らしに関わる更新 2件", page)
            self.assertIn('href="#article-3"', page)  # Map links retain original positions.

    def test_missing_corrupt_and_stale_metadata_use_regular_layout(self):
        self.assertNotIn('class="disaster-group"', builder.render_daily_sections(builder.parse_markdown(self.path)))
        self.label_day()
        self.path.write_text(markdown().replace("道路が通行止め", "道路が一時通行止め"), encoding="utf-8")
        self.assertEqual(builder.parse_markdown(self.path).display_labels, {})
        self.path.with_suffix(".display.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(builder.parse_markdown(self.path).display_labels, {})

    def test_small_group_and_no_disasters(self):
        day = self.label_day()
        for key, label in day.display_labels.items():
            if label["id"] != 2:
                label.update(kind="none", area="unclear", area_evidence="")
        page = builder.render_daily_sections(day)
        self.assertNotIn('class="disaster-more"', page)
        self.assertEqual(page.count('class="daily-item"'), 6)
        day.display_labels = {}
        self.assertNotIn("自然災害関連", builder.render_daily_sections(day))

    def test_single_api_call_and_safe_diagnostics(self):
        completion = SimpleNamespace(parsed=response(), diagnostic={"usage": {"total_tokens": 300},
                                    "content": "DO NOT LOG", "error": {"message": "secret"}})
        with patch.object(display, "bind_labels", wraps=display.bind_labels):
            from unittest.mock import Mock
            request = Mock(return_value=completion)
            result = display.classify(self.path, api_key="not-a-real-key", request=request)
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["profile"].provider, "openai")
        self.assertEqual(request.call_args.kwargs["profile"].model_id, "gpt-6-luna")
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["diagnostic"]["usage"]["total_tokens"], 300)
        self.assertNotIn("DO NOT LOG", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))
        self.assertIn("budgets", request.call_args.kwargs["messages"][0]["content"])
        self.assertIn("NOT issued warnings", request.call_args.kwargs["messages"][0]["content"])

    def test_failures_and_missing_key_keep_every_article(self):
        from unittest.mock import Mock
        for error in (TimeoutError(), ValueError("secret")):
            request = Mock(side_effect=error)
            result = display.classify(self.path, api_key="test", request=request)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["labels"], {})
            request.assert_called_once()
            self.assertNotIn("secret", json.dumps(result))
        request = Mock()
        result = display.classify(self.path, api_key="", request=request)
        self.assertEqual(result["status"], "skipped")
        request.assert_not_called()

    def test_workflow_keeps_manual_classification_artifact_only(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/malaysia-rss-summary.yml").read_text()
        step = workflow.split("- name: Classify natural disaster display groups", 1)[1].split("- name: Build Malaysia news index", 1)[0]
        self.assertIn('"${EVENT_NAME}" = "workflow_dispatch"', step)
        self.assertIn('display_input="${run_dir}/groq_json_render_candidate.md"', step)
        self.assertIn('--output "${display_input%.md}.display.json"', step)
        self.assertIn('secrets.OPENAI_API_KEY', step)
        self.assertNotIn('git push', step)

    def test_successful_transport_does_not_mask_local_validation_failure(self):
        result = response()
        result["articles"].pop()
        from unittest.mock import Mock
        request = Mock(return_value=SimpleNamespace(parsed=result, diagnostic={"failure_class": "none"}))
        report = display.classify(self.path, api_key="test", request=request)
        self.assertEqual(report["failure_class"], "display_validation")
        self.assertEqual(report["validation_reason"], "display_id_mismatch")


if __name__ == "__main__":
    unittest.main()
