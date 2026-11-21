from __future__ import annotations

import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import build_malaysia_news_index as builder
import malaysia_jev_editorial_routing as routing
import malaysia_jev_selector_shadow as selector
import malaysia_news_disaster_display as display
from test_malaysia_jev_editorial_routing import item, payload, response


CASES = json.loads((Path(__file__).parent / "fixtures/malaysia_public_impact_fires.json").read_text())["cases"]


class PublicImpactFireTests(unittest.TestCase):
    """Contract tests with expected responses, not a semantic model evaluation."""

    def test_policy_explicitly_covers_public_effects_without_inferring_them(self):
        request = selector.build_request(CASES[0])
        criteria = request["questions"][selector.QUESTION_ID]["criteria"]
        for effect in ("evacuation", "road closures", "power", "harmful smoke"):
            self.assertIn(effect, criteria["direct_life_impact"])
            self.assertIn(effect, display.SYSTEM_PROMPT)
        self.assertIn("Do not infer", criteria["direct_life_impact"])
        self.assertIn("isolated fire", criteria["unrelated_noise"])
        self.assertIn("An isolated fire", display.SYSTEM_PROMPT)
        self.assertIn("If uncertain use none", display.SYSTEM_PROMPT)
        self.assertEqual(selector.QUESTION_SET_VERSION, "malaysia-news-selector-relevance-v3")

    def test_expected_jev_responses_route_public_impacts_not_isolated_fires(self):
        candidates = []
        for i, case in enumerate(CASES, 1):
            candidate = item(case["title"], f"https://example.test/fire-{i}")
            candidate["description"] = case["description"]
            candidates.append(candidate)
        expected = {case["title"]: case for case in CASES}

        def classify(request, *_):
            case = expected[request["state"]["title"]]
            self.assertEqual(request["state"]["sourceDescription"], case["description"])
            self.assertIn("Fires, whether natural or human-caused", request["questions"][selector.QUESTION_ID]["criteria"]["direct_life_impact"])
            return response(case["relevance"])

        transport = Mock(side_effect=classify)
        selected, report = routing.route_candidates(
            payload(candidates), payload([]), enabled=True, api_key="fixture-only",
            timeout_seconds=1, post_json=transport,
        )
        self.assertEqual(transport.call_count, len(CASES))
        self.assertEqual([row["title"] for row in selected["items"]], [case["title"] for case in CASES[:4]])
        self.assertTrue(all(row["publicationDecision"] == "excluded_unrelated_noise" for row in report["results"][4:]))

    def test_single_display_call_keeps_all_articles_and_prioritizes_klang_valley(self):
        text = "更新時点：2026-11-21T07:00:00+08:00\n\n【暮らしに関わる更新】\n\n" + "\n\n".join(
            f'- 見出し：{case["headline"]}\n- 概要：{case["summary"]}\n- 出典：Fixture\n- 出典元URL：https://example.test/fire-{i}'
            for i, case in enumerate(CASES, 1)
        )
        labels = {"articles": [dict(id=i, **{key: case[key] for key in ("kind", "area", "area_evidence")})
                                for i, case in enumerate(CASES, 1)]}
        transport = Mock(return_value=SimpleNamespace(parsed=labels, diagnostic={}))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "2026-11-21.md"
            path.write_text(text, encoding="utf-8")
            report = display.classify(path, api_key="fixture-only", request=transport)
            transport.assert_called_once()
            self.assertEqual(report["policy_version"], 3)
            self.assertEqual(report["status"], "applied")
            self.assertEqual(transport.call_args.kwargs["messages"][0]["content"], display.SYSTEM_PROMPT)
            path.with_suffix(".display.json").write_text(json.dumps(report), encoding="utf-8")
            day = builder.parse_markdown(path)
            self.assertEqual([i for i, _ in builder.disaster_items(day)], [1, 2, 3, 4])
            for home in (True, False):
                page = builder.render_daily_page(day, is_home=home)
                self.assertIn("災害・火災関連 4件", page)
                self.assertIn("関連ニュースをさらに読む 1件", page)
                self.assertEqual(page.count('class="daily-item"'), len(CASES))
                for i in range(1, len(CASES) + 1):
                    self.assertEqual(page.count(f'id="article-{i}"'), 1)
                    self.assertEqual(page.count(f'href="https://example.test/fire-{i}"'), 1)
                parts = []
                parser = HTMLParser()
                parser.handle_data = parts.append
                parser.feed(page.split('class="daily-category"', 1)[1])
                regular = "".join(parts)
                self.assertIn(CASES[4]["headline"], regular)
                self.assertIn(CASES[5]["headline"], regular)
                self.assertNotIn(CASES[0]["headline"], regular)


if __name__ == "__main__":
    unittest.main()
