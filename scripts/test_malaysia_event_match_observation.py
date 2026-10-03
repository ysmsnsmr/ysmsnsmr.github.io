#!/usr/bin/env python3
import unittest
from pathlib import Path
from types import SimpleNamespace

from malaysia_event_match_observation import MAX_CANDIDATES, observe, select_cohort


def candidate(index: int) -> dict:
    return {
        "source": "Fixture Source",
        "link": f"https://example.test/{index}",
        "published_at": "2026-09-26T10:00:00+08:00",
        "title": f"Report {index}",
        "description": f"Description {index}",
    }


def routing(choices: list[str], status: str = "applied") -> dict:
    return {
        "status": status,
        "results": [
            {"candidateRank": index, "outcome": "classified", "jevDecision": choice}
            for index, choice in enumerate(choices, start=1)
        ],
    }


class EventMatchObservationTests(unittest.TestCase):
    def test_workflow_runs_coverage_before_publication(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/malaysia-rss-summary.yml").read_text()
        self.assertIn("--event-coverage", workflow)
        self.assertIn("--event-report-output \"${run_dir}/event_match_observation.json\"", workflow)
        self.assertNotIn("- name: Observe same-event Malaysia reports", workflow)

    def test_one_call_compares_positive_candidates(self) -> None:
        pool = {"items": [candidate(index) for index in range(1, 5)]}
        calls = []

        def request(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(parsed={"omissions": [{"keep": 1, "omit": 2, "reason": "Same announcement and figures"}]}, diagnostic={"transport_status": "success"})

        result = observe(
            pool, routing(["direct_life_impact", "direct_life_impact", "unrelated_noise", "public_information"]),
            api_key="fixture-key", model_name="gpt-oss-120b", request=request,
        )
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["productionEffect"])
        self.assertEqual(len(calls), 1)
        self.assertEqual([row["candidateRank"] for row in result["cohort"]], [1, 2, 4])
        self.assertEqual(result["coverageDecisions"], [{"keep": 1, "omit": 2, "reason": "Same announcement and figures"}])
        self.assertEqual(calls[0]["json_schema_name"], "malaysia_news_event_coverage_v2")
        self.assertIn("important new information", calls[0]["messages"][0]["content"])
        self.assertNotIn("fixture-key", str(result))
        self.assertNotIn("https://example.test", str(result))

    def test_skips_when_routing_is_not_applied_or_cohort_is_too_small(self) -> None:
        def unexpected(**kwargs):
            self.fail("no event call should be made")

        pool = {"items": [candidate(1), candidate(2)]}
        disabled = observe(pool, routing(["direct_life_impact", "direct_life_impact"], "disabled"),
                           api_key="key", model_name="gpt-oss-120b", request=unexpected)
        self.assertEqual(disabled["status"], "skipped_routing_not_applied")
        small = observe(pool, routing(["direct_life_impact", "unrelated_noise"]),
                        api_key="key", model_name="gpt-oss-120b", request=unexpected)
        self.assertEqual(small["status"], "skipped_insufficient_candidates")

    def test_invalid_references_do_not_produce_partial_pairs(self) -> None:
        pool = {"items": [candidate(1), candidate(2)]}
        result = observe(
            pool, routing(["direct_life_impact", "public_information"]), api_key="key",
            model_name="gpt-oss-120b",
            request=lambda **_: SimpleNamespace(parsed={"omissions": [{"keep": 1, "omit": 3, "reason": "same"}]}, diagnostic={}),
        )
        self.assertEqual(result["status"], "invalid_coverage")
        self.assertEqual(result["coverageDecisions"], [])

    def test_malformed_json_object_response_is_not_marked_completed(self) -> None:
        pool = {"items": [candidate(1), candidate(2)]}
        result = observe(
            pool, routing(["direct_life_impact", "public_information"]), api_key="key",
            model_name="gpt-oss-120b",
            request=lambda **_: SimpleNamespace(parsed={"omissions": [{"keep": "1", "omit": 2, "reason": "same"}]}, diagnostic={}),
        )
        self.assertEqual(result["status"], "invalid_coverage")
        self.assertEqual(result["coverageDecisions"], [])

    def test_request_failure_is_observation_only(self) -> None:
        pool = {"items": [candidate(1), candidate(2)]}

        def failure(**kwargs):
            raise TimeoutError("fixture")

        result = observe(pool, routing(["direct_life_impact", "public_information"]),
                         api_key="key", model_name="gpt-oss-120b", request=failure)
        self.assertEqual(result["status"], "request_failed")
        self.assertEqual(result["coverageDecisions"], [])

    def test_rejects_chained_and_ambiguous_omissions(self) -> None:
        pool = {"items": [candidate(index) for index in range(1, 4)]}
        for decisions in (
            [{"keep": 1, "omit": 2, "reason": "same"}, {"keep": 2, "omit": 3, "reason": "same"}],
            [{"keep": 1, "omit": 3, "reason": "same"}, {"keep": 2, "omit": 3, "reason": "same"}],
        ):
            result = observe(
                pool, routing(["direct_life_impact"] * 3), api_key="key", model_name="gpt-oss-120b",
                request=lambda **_: SimpleNamespace(parsed={"omissions": decisions}, diagnostic={}),
            )
            self.assertEqual(result["status"], "invalid_coverage")
            self.assertEqual(result["coverageDecisions"], [])

    def test_truncated_description_cannot_justify_omission(self) -> None:
        pool = {"items": [candidate(1), candidate(2)]}
        pool["items"][1]["description"] = "a" * 351
        result = observe(
            pool, routing(["direct_life_impact"] * 2), api_key="key", model_name="gpt-oss-120b",
            request=lambda **_: SimpleNamespace(
                parsed={"omissions": [{"keep": 1, "omit": 2, "reason": "same"}]}, diagnostic={}
            ),
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["coverageDecisions"], [])
        self.assertEqual(result["discardedTruncatedInputCount"], 1)

    def test_request_has_bounded_cohort(self) -> None:
        pool = {"items": [candidate(index) for index in range(1, MAX_CANDIDATES + 8)]}
        choices = ["direct_life_impact"] * len(pool["items"])
        result = observe(pool, routing(choices), api_key=None, model_name="gpt-oss-120b")
        self.assertEqual(result["status"], "skipped_missing_api_key")
        self.assertEqual(result["candidateCount"], MAX_CANDIDATES)

    def test_rejects_report_from_another_candidate_pool(self) -> None:
        pool = {"items": [candidate(1), candidate(2)]}
        report = routing(["direct_life_impact", "public_information"])
        report["results"][0]["itemFingerprint"] = "wrong-run"
        with self.assertRaisesRegex(ValueError, "does not match"):
            select_cohort(pool, report)


if __name__ == "__main__":
    unittest.main()
