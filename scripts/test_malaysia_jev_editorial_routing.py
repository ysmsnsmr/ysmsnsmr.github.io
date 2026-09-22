#!/usr/bin/env python3
import copy
import json
import unittest
from unittest.mock import patch

import malaysia_jev_editorial_routing as routing
from jev_shadow_transport import JevRequestError


def item(
    title: str,
    link: str,
    category: str = "【知っておくと得】",
    *,
    source: str = "Fixture Source",
    financial_bucket: str = "",
) -> dict[str, object]:
    value = {
        "category": category,
        "source": source,
        "published_at": "2026-09-20T10:00:00+08:00",
        "published_date": "2026年9月20日",
        "title": title,
        "description": f"Description for {title}",
        "link": link,
        "editorial_entry": {
            "headline_ja": "記事詳細は出典へ",
            "short_headline_ja": "記事詳細は出典へ",
            "entry_ja": title,
            "supporting_points_ja": [],
        },
    }
    if financial_bucket:
        value["routing_metadata"] = {"financial_bucket": financial_bucket}
    return value


def payload(
    items: list[dict[str, object]],
    *,
    post_relevance_policy: dict[str, object] | None = None,
) -> dict[str, object]:
    value = {
        "schema_version": "2b0_selected_items_v1",
        "counts": {"processed": len(items), "selected": len(items), "failed_sources": 0},
        "failed_sources": [],
        "items": items,
    }
    if post_relevance_policy is not None:
        value["post_relevance_policy"] = post_relevance_policy
    return value


def response(choice: str) -> dict[str, object]:
    probabilities = {name: 0.0 for name in ("direct_life_impact", "public_information", "unrelated_noise", "unclear")}
    probabilities[choice] = 1.0
    return {
        "model": "jev-1.13.0",
        "answers": {
            "malaysiaNewsRelevance": {
                "type": "choice",
                "choice": choice,
                "confidence": 0.9,
                "probabilities": probabilities,
            }
        },
    }


class MalaysiaJevEditorialRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.direct = item("Haze affects Putrajaya", "https://example.test/haze")
        self.public = item("Public policy update", "https://example.test/policy")
        self.unclear = item("Unclear item", "https://example.test/unclear")
        self.noise = item("Corporate ceremony", "https://example.test/noise")
        self.pool = payload([self.direct, self.public, self.unclear, self.noise])
        self.baseline = payload([self.public, self.unclear])

    def test_direct_impact_is_promoted_before_the_editorial_budget(self) -> None:
        choices = {
            "Haze affects Putrajaya": "direct_life_impact",
            "Public policy update": "public_information",
            "Unclear item": "unclear",
            "Corporate ceremony": "unrelated_noise",
        }

        def post_json(request: dict[str, object], _: str, __: float) -> dict[str, object]:
            state = request["state"]
            return response(choices[state["title"]])

        with patch.object(routing, "TARGET_CARD_COUNT", 2):
            output, report = routing.route_candidates(
                self.pool,
                self.baseline,
                enabled=True,
                api_key="fixture-key",
                timeout_seconds=1,
                post_json=post_json,
            )

        self.assertEqual(report["status"], "applied")
        self.assertTrue(report["routingEffect"])
        self.assertEqual([value["title"] for value in output["items"]], ["Haze affects Putrajaya", "Public policy update"])
        decisions = {result["jevDecision"]: result["publicationDecision"] for result in report["results"]}
        self.assertEqual(decisions["direct_life_impact"], "selected")
        self.assertEqual(decisions["public_information"], "selected")
        self.assertEqual(decisions["unclear"], "excluded_editorial_budget")
        self.assertEqual(decisions["unrelated_noise"], "excluded_unrelated_noise")

    def test_direct_impact_is_protected_but_still_respects_the_editorial_budget(self) -> None:
        direct_items = [item(f"Direct {index}", f"https://example.test/direct-{index}") for index in range(3)]
        pool = payload(direct_items)

        with patch.object(routing, "TARGET_CARD_COUNT", 2):
            output, report = routing.route_candidates(
                pool,
                payload([]),
                enabled=True,
                api_key="fixture-key",
                timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"),
            )

        self.assertEqual([value["title"] for value in output["items"]], ["Direct 0", "Direct 1"])
        self.assertEqual(report["summary"]["selectedCount"], 2)
        self.assertEqual(report["results"][2]["publicationDecision"], "excluded_editorial_budget")

    def test_unclear_item_is_kept_only_when_the_legacy_baseline_selected_it(self) -> None:
        output, report = routing.route_candidates(
            payload([self.unclear]),
            payload([]),
            enabled=True,
            api_key="fixture-key",
            timeout_seconds=1,
            post_json=lambda *_: response("unclear"),
        )

        self.assertEqual(output["items"], [])
        self.assertEqual(report["results"][0]["publicationDecision"], "excluded_unclear")

    def test_source_diversity_is_applied_after_relevance(self) -> None:
        first = item("Paul Tan transport one", "https://example.test/pt-1", source="Paul Tan")
        second = item("Paul Tan transport two", "https://example.test/pt-2", source="Paul Tan")
        pool = payload(
            [first, second],
            post_relevance_policy={
                "target_card_count": 15,
                "default_source_limit": 24,
                "source_limits": {"Paul Tan": 1},
                "financial_limits": {},
            },
        )

        output, report = routing.route_candidates(
            pool,
            payload([]),
            enabled=True,
            api_key="fixture-key",
            timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"),
        )

        self.assertEqual([value["title"] for value in output["items"]], ["Paul Tan transport one"])
        self.assertEqual(report["results"][1]["publicationDecision"], "excluded_source_diversity")

    def test_financial_diversity_is_applied_after_relevance_and_metadata_is_not_published(self) -> None:
        first = item("Ringgit one", "https://example.test/ringgit-1", financial_bucket="ringgit")
        second = item("Ringgit two", "https://example.test/ringgit-2", financial_bucket="ringgit")
        pool = payload(
            [first, second],
            post_relevance_policy={
                "target_card_count": 15,
                "default_source_limit": 24,
                "source_limits": {},
                "financial_limits": {"ringgit": 1},
            },
        )

        output, report = routing.route_candidates(
            pool,
            payload([]),
            enabled=True,
            api_key="fixture-key",
            timeout_seconds=1,
            post_json=lambda *_: response("public_information"),
        )

        self.assertEqual([value["title"] for value in output["items"]], ["Ringgit one"])
        self.assertNotIn("routing_metadata", output["items"][0])
        self.assertEqual(report["results"][1]["publicationDecision"], "excluded_financial_diversity")

    def test_disabled_routing_keeps_the_legacy_selector_items(self) -> None:
        output, report = routing.route_candidates(
            self.pool,
            self.baseline,
            enabled=False,
            api_key=None,
            timeout_seconds=1,
            post_json=lambda *_: self.fail("disabled routing must not call Jev"),
        )

        self.assertEqual(report["status"], "disabled")
        self.assertFalse(report["routingEffect"])
        self.assertEqual(output["items"], self.baseline["items"])
        self.assertFalse(output["editorial_routing"]["applied"])

    def test_candidate_safety_cap_falls_back_without_calling_jev(self) -> None:
        candidates = [item(f"Candidate {index}", f"https://example.test/{index}") for index in range(151)]

        output, report = routing.route_candidates(
            payload(candidates),
            self.baseline,
            enabled=True,
            api_key="fixture-key",
            timeout_seconds=1,
            post_json=lambda *_: self.fail("candidate cap must stop before Jev calls"),
        )

        self.assertEqual(report["status"], "fallback_candidate_cap")
        self.assertEqual(output["items"], self.baseline["items"])

    def test_any_transport_failure_fails_open_to_the_legacy_baseline(self) -> None:
        def post_json(_: dict[str, object], __: str, ___: float) -> dict[str, object]:
            raise JevRequestError("timeout")

        output, report = routing.route_candidates(
            self.pool,
            self.baseline,
            enabled=True,
            api_key="fixture-key",
            timeout_seconds=1,
            post_json=post_json,
        )

        self.assertEqual(report["status"], "fallback_classifier_error")
        self.assertFalse(report["routingEffect"])
        self.assertEqual(output["items"], self.baseline["items"])
        self.assertEqual(report["results"][0]["errorCode"], "timeout")

    def test_report_does_not_persist_article_text_or_urls(self) -> None:
        output, report = routing.route_candidates(
            self.pool,
            self.baseline,
            enabled=False,
            api_key=None,
            timeout_seconds=1,
        )

        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("Haze affects Putrajaya", rendered)
        self.assertNotIn("Description for Haze affects Putrajaya", rendered)
        self.assertNotIn("https://example.test/haze", rendered)
        self.assertEqual(output["items"], self.baseline["items"])


if __name__ == "__main__":
    unittest.main()
