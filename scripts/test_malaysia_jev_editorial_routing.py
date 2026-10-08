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
        self.assertEqual(output["items"][0]["display_category"], "【暮らしに関わる更新】")
        self.assertEqual(output["items"][1]["display_category"], "【社会・経済の動き】")
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

    def test_covered_report_is_removed_before_budget_and_next_article_backfills(self) -> None:
        reports = [
            item("JPJ MyEG renewal announcement", "https://example.test/jpj-1"),
            item("Another report of the JPJ MyEG announcement", "https://example.test/jpj-2"),
            item("Separate Rapid KL service update", "https://example.test/rapid"),
        ]
        seen = []

        def compare(pool, classified, **kwargs):
            seen.append([row["jevDecision"] for row in classified["results"]])
            return {
                "status": "completed", "productionEffect": False,
                "cohort": [{"id": index, "candidateRank": index} for index in range(1, 4)],
                "coverageDecisions": [{"keep": 1, "omit": 2, "reason": "Same JPJ announcement"}],
            }

        with patch.object(routing, "TARGET_CARD_COUNT", 2):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
                event_api_key="groq-key", event_observer=compare,
            )
        self.assertEqual(len(seen), 1)
        self.assertEqual([row["title"] for row in output["items"]], [reports[0]["title"], reports[2]["title"]])
        self.assertEqual(report["results"][1]["publicationDecision"], "excluded_covered_event")
        self.assertEqual(report["results"][1]["coveredByCandidateRank"], 1)
        self.assertEqual(report["eventCoverage"]["suppressedCount"], 1)
        self.assertNotIn("jpj-1", json.dumps(report))

    def test_later_representative_is_selected_before_budget_and_older_story_is_omitted(self) -> None:
        reports = [
            item("Morning air quality status", "https://example.test/morning"),
            item("Separate service change", "https://example.test/service"),
            item("Afternoon air quality update covering morning status", "https://example.test/afternoon"),
        ]
        reports[2]["published_at"] = "2026-09-20T16:30:00+08:00"
        coverage = {
            "status": "completed", "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 3}],
            "coverageDecisions": [{"keep": 2, "omit": 1, "reason": "Later report includes morning status"}],
        }
        with patch.object(routing, "TARGET_CARD_COUNT", 2):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
                event_observer=lambda *args, **kwargs: coverage,
                haze_observer=lambda *args, **kwargs: {"status": "disabled", "cohort": [], "coverageDecisions": []},
            )
        self.assertEqual([row["title"] for row in output["items"]], [reports[2]["title"], reports[1]["title"]])
        self.assertEqual(report["results"][0]["publicationDecision"], "excluded_covered_event")
        self.assertEqual(report["results"][0]["coveredByCandidateRank"], 3)

    def test_later_representative_not_selected_keeps_earlier_story(self) -> None:
        reports = [
            item("Earlier blocked-source story", "https://example.test/other", source="Blocked"),
            item("Earlier district closure", "https://example.test/district", source="Available"),
            item("Later statewide closure", "https://example.test/state", source="Blocked"),
        ]
        coverage = {
            "status": "completed", "cohort": [{"id": 1, "candidateRank": 2}, {"id": 2, "candidateRank": 3}],
            "coverageDecisions": [{"keep": 2, "omit": 1, "reason": "Later report covers earlier closure"}],
        }
        output, report = routing.route_candidates(
            payload(reports, post_relevance_policy={"source_limits": {"Blocked": 1}}), payload([]),
            enabled=True, api_key="jev-key", timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
            event_observer=lambda *args, **kwargs: coverage,
            haze_observer=lambda *args, **kwargs: {"status": "disabled", "cohort": [], "coverageDecisions": []},
        )
        self.assertEqual([row["title"] for row in output["items"]], [reports[0]["title"], reports[1]["title"]])
        self.assertEqual(report["results"][1]["publicationDecision"], "selected")
        self.assertEqual(report["results"][2]["publicationDecision"], "excluded_source_diversity")

    def test_public_information_representative_does_not_replace_direct_impact(self) -> None:
        reports = [
            item("Affected district closure", "https://example.test/district"),
            item("Later statewide report", "https://example.test/state"),
        ]
        choices = {reports[0]["title"]: "direct_life_impact", reports[1]["title"]: "public_information"}
        coverage = {
            "status": "completed", "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 2}],
            "coverageDecisions": [{"keep": 2, "omit": 1, "reason": "Later report covers the district"}],
        }
        with patch.object(routing, "TARGET_CARD_COUNT", 1):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda request, *_: response(choices[request["state"]["title"]]),
                event_enabled=True, event_observer=lambda *args, **kwargs: coverage,
                haze_observer=lambda *args, **kwargs: {"status": "disabled", "cohort": [], "coverageDecisions": []},
            )
        self.assertEqual([row["title"] for row in output["items"]], [reports[0]["title"]])
        self.assertEqual(report["results"][0]["publicationDecision"], "selected")

    def test_haze_daily_coverage_preserves_klang_followup_and_backfills_budget(self) -> None:
        reports = [
            item("Haze API unhealthy in Segamat", "https://example.test/segamat"),
            item("Jerebu IPU unhealthy in Nilai", "https://example.test/nilai"),
            item("Haze API now affects Cheras", "https://example.test/cheras"),
            item("Haze API unhealthy in Johor", "https://example.test/johor"),
            item("Separate public transport update", "https://example.test/transport"),
        ]
        haze = {
            "status": "completed", "productionEffect": False,
            "cohort": [{"id": index, "candidateRank": index} for index in range(1, 5)],
            "coverageDecisions": [
                {"keep": 1, "omit": 2, "reason": "Same daily haze situation"},
                {"keep": 1, "omit": 4, "reason": "Same daily haze situation"},
            ],
        }
        with patch.object(routing, "TARGET_CARD_COUNT", 3):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
                event_api_key="groq-key",
                event_observer=lambda *args, **kwargs: {
                    "status": "invalid_coverage", "cohort": [], "coverageDecisions": [],
                },
                haze_observer=lambda *args, **kwargs: haze,
            )
        self.assertEqual(
            [row["title"] for row in output["items"]],
            [reports[0]["title"], reports[2]["title"], reports[4]["title"]],
        )
        self.assertEqual(report["hazeCoverage"]["suppressedCount"], 2)
        self.assertEqual(output["editorial_routing"]["haze_coverage_suppressed_count"], 2)
        self.assertEqual(report["results"][1]["coverageSource"], "haze_daily")
        self.assertNotIn("https://example.test", json.dumps(report))

    def test_haze_followup_can_replace_higher_priority_earlier_status(self) -> None:
        reports = [
            item("Morning air quality unhealthy in 35 areas", "https://example.test/morning"),
            item("Other local news", "https://example.test/other"),
            item("Afternoon air quality unhealthy in 37 stations", "https://example.test/afternoon"),
        ]
        haze = {
            "status": "completed", "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 3}],
            "coverageDecisions": [{"keep": 2, "omit": 1, "reason": "Updated status covers earlier affected areas"}],
        }
        with patch.object(routing, "TARGET_CARD_COUNT", 2):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
                event_observer=lambda *args, **kwargs: {"status": "disabled", "cohort": [], "coverageDecisions": []},
                haze_observer=lambda *args, **kwargs: haze,
            )
        self.assertEqual([row["title"] for row in output["items"]], [reports[2]["title"], reports[1]["title"]])
        self.assertEqual(report["results"][0]["coverageSource"], "haze_daily")
        self.assertEqual(report["hazeCoverage"]["suppressedCount"], 1)

    def test_failed_haze_matching_keeps_all_status_articles(self) -> None:
        reports = [
            item("Haze API in Johor", "https://example.test/haze-one"),
            item("Jerebu IPU in Nilai", "https://example.test/haze-two"),
        ]
        output, report = routing.route_candidates(
            payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
            event_observer=lambda *args, **kwargs: {
                "status": "invalid_coverage", "cohort": [], "coverageDecisions": [],
            },
            haze_observer=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("fixture")),
        )
        self.assertEqual(len(output["items"]), 2)
        self.assertEqual(report["hazeCoverage"]["status"], "request_failed")
        self.assertEqual(report["hazeCoverage"]["suppressedCount"], 0)

    def test_haze_policy_protects_klang_followup_from_generic_omission(self) -> None:
        reports = [
            item("Haze API unhealthy in Johor", "https://example.test/johor"),
            item("Haze API now affects Cheras", "https://example.test/cheras"),
        ]
        output, report = routing.route_candidates(
            payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
            event_observer=lambda *args, **kwargs: {
                "status": "completed",
                "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 2}],
                "coverageDecisions": [{"keep": 1, "omit": 2, "reason": "Same haze event"}],
            },
            haze_observer=lambda *args, **kwargs: {
                "status": "completed",
                "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 2}],
                "coverageDecisions": [],
            },
        )
        self.assertEqual(len(output["items"]), 2)
        self.assertEqual(report["eventCoverage"]["suppressedCount"], 0)
        self.assertEqual(report["hazeCoverage"]["suppressedCount"], 0)

    def test_failed_haze_call_does_not_fall_back_to_generic_haze_omission(self) -> None:
        reports = [
            item("Haze API unhealthy in Johor", "https://example.test/johor"),
            item("Haze API now affects Cheras", "https://example.test/cheras"),
        ]
        output, report = routing.route_candidates(
            payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
            event_api_key="groq-key",
            event_observer=lambda *args, **kwargs: {
                "status": "completed",
                "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 2}],
                "coverageDecisions": [{"keep": 1, "omit": 2, "reason": "Same haze event"}],
            },
            haze_observer=lambda *args, **kwargs: {
                "status": "request_failed",
                "cohort": [{"id": 1, "candidateRank": 1}, {"id": 2, "candidateRank": 2}],
                "coverageDecisions": [],
            },
        )
        self.assertEqual(len(output["items"]), 2)
        self.assertEqual(report["eventCoverage"]["suppressedCount"], 0)
        self.assertEqual(report["hazeCoverage"]["status"], "request_failed")

    def test_distinct_updates_and_failed_comparison_keep_both(self) -> None:
        reports = [
            item("Morning weather alert in Selangor", "https://example.test/weather-morning"),
            item("Evening weather alert in Perlis", "https://example.test/weather-evening"),
        ]
        for compare in (
            lambda *args, **kwargs: {"status": "completed", "cohort": [], "coverageDecisions": []},
            lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("fixture")),
        ):
            output, report = routing.route_candidates(
                payload(reports), payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
                post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
                event_observer=compare,
            )
            self.assertEqual(len(output["items"]), 2)
            self.assertEqual(report["eventCoverage"]["suppressedCount"], 0)

    def test_unselected_representative_does_not_hide_other_report(self) -> None:
        reports = [item("First", "https://example.test/first"), item("Second", "https://example.test/second")]
        pool = payload(reports, post_relevance_policy={"source_limits": {"Fixture Source": 1}})
        # A representative rejected by an earlier selection cannot cover the later report.
        reports[0]["source"] = "Blocked Source"
        pool["post_relevance_policy"]["source_limits"] = {"Blocked Source": 1}
        third = item("Earlier blocked-source story", "https://example.test/earlier", source="Blocked Source")
        pool["items"] = [third, *reports]
        pool["post_relevance_policy"]["source_limits"] = {"Blocked Source": 1}
        coverage = {
            "status": "completed", "cohort": [{"id": 1, "candidateRank": 2}, {"id": 2, "candidateRank": 3}],
            "coverageDecisions": [{"keep": 1, "omit": 2, "reason": "Equivalent"}],
        }
        output, report = routing.route_candidates(
            pool, payload([]), enabled=True, api_key="jev-key", timeout_seconds=1,
            post_json=lambda *_: response("direct_life_impact"), event_enabled=True,
            event_observer=lambda *args, **kwargs: coverage,
        )
        self.assertEqual([row["title"] for row in output["items"]], [third["title"], reports[1]["title"]])
        self.assertEqual(report["results"][1]["publicationDecision"], "excluded_source_diversity")
        self.assertEqual(report["results"][2]["publicationDecision"], "selected")


if __name__ == "__main__":
    unittest.main()
