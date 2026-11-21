"""Keep selection, generation and scheduled configuration budgets aligned."""

from datetime import datetime
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from malaysia_groq_force_all_policy import force_all_request_cap
from malaysia_jev_editorial_routing import TARGET_CARD_COUNT
from malaysia_rss_summary import build_editorial_candidate_pool_json
import malaysia_news_disaster_display as display


class NewsBudgetTests(unittest.TestCase):
    def test_production_budget_sources_all_agree_on_fifty(self):
        pool = build_editorial_candidate_pool_json(0, [], datetime.fromisoformat("2026-11-20T08:00:00+08:00"))
        with patch.dict(os.environ, {"MALAYSIA_NEWS_EDITORIAL_REQUEST_CAP": "", "MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP": ""}):
            self.assertEqual(force_all_request_cap(), 50)
        self.assertEqual(TARGET_CARD_COUNT, 50)
        self.assertEqual(pool["post_relevance_policy"]["target_card_count"], 50)
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/malaysia-rss-summary.yml").read_text()
        self.assertIn('export MALAYSIA_NEWS_EDITORIAL_REQUEST_CAP="50"', workflow)

    def test_invalid_request_cap_defaults_to_fifty(self):
        for value in ("bad", "0", "-1"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "MALAYSIA_NEWS_EDITORIAL_REQUEST_CAP": value,
                "MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP": "",
            }):
                self.assertEqual(force_all_request_cap(), 50)

    def test_fifty_articles_still_use_one_shared_display_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "2026-11-20.md"
            rows = []
            parts = ["更新時点：2026-11-20T08:00:00+08:00", "【暮らしに関わる更新】"]
            for i in range(1, 51):
                parts.append(f"- 見出し：生活情報{i}\n- 概要：地域のサービスが更新されました。\n- 出典：Fixture\n- 出典元URL：https://example.test/{i}")
                rows.append(dict(id=i, kind="none", area="unclear", area_evidence=""))
            path.write_text("\n\n".join(parts), encoding="utf-8")
            request = Mock(return_value=SimpleNamespace(parsed={"articles": rows}, diagnostic={}))
            report = display.classify(path, api_key="fixture-key", request=request)
            self.assertEqual(report["status"], "applied")
            self.assertEqual(len(report["labels"]), 50)
            request.assert_called_once()
            self.assertEqual(request.call_args.kwargs["max_completion_tokens"], 6000)


if __name__ == "__main__":
    unittest.main()
