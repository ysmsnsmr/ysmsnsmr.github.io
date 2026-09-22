from __future__ import annotations

import json
import unittest

from malaysia_jev_selector_shadow import (
    CHOICES,
    QUESTION_ID,
    build_report,
    build_request,
    select_cohort,
)


def selection_item(
    *,
    title: str,
    description: str,
    link: str,
    decision: str,
    stage: str,
    score: int,
    rank: int | None,
) -> dict:
    return {
        "source": "Example News",
        "feed": "https://example.invalid/feed",
        "published_at": "2026-09-20T01:00:00+00:00",
        "title": title,
        "description": description,
        "link": link,
        "selector_evaluated": True,
        "score": score,
        "decision": decision,
        "decision_stage": stage,
        "decision_reason": f"{stage} for test",
        "candidate_rank": rank,
    }


def provider_response(choice: str) -> dict:
    probabilities = {name: 0.0 for name in CHOICES}
    probabilities[choice] = 1.0
    return {
        "model": "typesafe/jev-1.13-test",
        "answers": {
            QUESTION_ID: {
                "type": "choice",
                "choice": choice,
                "confidence": 0.9,
                "probabilities": probabilities,
            }
        },
    }


class MalaysiaJevSelectorShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selected = selection_item(
            title="Selected weather warning",
            description="Heavy rain is expected in Selangor.",
            link="https://example.invalid/selected",
            decision="selected",
            stage="selected",
            score=10,
            rank=1,
        )
        self.excluded = selection_item(
            title="Excluded local closure",
            description="A Penang road lane will be closed.",
            link="https://example.invalid/excluded",
            decision="excluded",
            stage="selector_excluded",
            score=8,
            rank=None,
        )
        self.noise = selection_item(
            title="Selected ceremony",
            description="A corporate event was held.",
            link="https://example.invalid/noise",
            decision="selected",
            stage="selected",
            score=7,
            rank=2,
        )
        self.outside_window = {
            **selection_item(
                title="Old item",
                description="Not eligible.",
                link="https://example.invalid/old",
                decision="excluded",
                stage="outside_recent_window",
                score=0,
                rank=None,
            ),
            "selector_evaluated": False,
            "score": None,
        }
        self.selection = {
            "schema_version": "malaysia-rss-selection-observation/v1",
            "date": "2026-09-20",
            "items": [self.selected, self.excluded, self.noise, self.outside_window],
        }

    def test_request_sends_only_public_title_and_description(self) -> None:
        request = build_request(self.selected)
        self.assertEqual(set(request["state"]), {"title", "sourceDescription"})
        criteria = request["questions"][QUESTION_ID]["criteria"]
        self.assertIn("eligibility", criteria["direct_life_impact"])
        self.assertIn("isolated crime or accident", criteria["unrelated_noise"])
        serialized = json.dumps(request)
        self.assertNotIn(self.selected["link"], serialized)
        self.assertNotIn("selector_excluded", serialized)

    def test_cohort_is_deterministic_and_excludes_outside_window(self) -> None:
        cohort = select_cohort(self.selection, 10)
        self.assertEqual([index for index, _ in cohort], [1, 3, 2])

    def test_shadow_report_never_changes_routing_or_persists_article_text(self) -> None:
        choices = iter(["direct_life_impact", "unrelated_noise", "direct_life_impact"])

        def post_json(payload: dict, api_key: str, timeout_seconds: float) -> dict:
            self.assertEqual(api_key, "test-key")
            self.assertEqual(timeout_seconds, 7)
            return provider_response(next(choices))

        report = build_report(
            self.selection,
            "selection-sha",
            {
                self.selected["link"]: {"status": "not_rejected", "reason": ""},
                self.excluded["link"]: {"status": "rejected", "reason": "english_lead"},
            },
            {"status": "passed"},
            "test-key",
            7,
            10,
            post_json=post_json,
            generated_at="2026-09-20T00:00:00Z",
            commit_sha="abc123",
        )
        self.assertEqual(report["status"], "completed")
        self.assertFalse(report["productionEffect"])
        self.assertFalse(report["routingEffect"])
        self.assertTrue(report["principles"]["safetyConditionsAreFixedNotValidatorImplementation"])
        self.assertFalse(report["principles"]["hardSafetyBypassAllowed"])
        self.assertEqual(report["principles"]["reviewDefault"], "retain_baseline")
        by_index = {entry["selectionObservationIndex"]: entry for entry in report["results"]}
        self.assertEqual(by_index[2]["suggestedRouting"], "candidate_promote_for_review")
        self.assertEqual(by_index[2]["routingDecision"], "retain_baseline")
        self.assertEqual(by_index[3]["suggestedRouting"], "selected_review")
        self.assertEqual(by_index[2]["hardSafetyObservation"]["status"], "rejected")
        self.assertEqual(by_index[2]["finalPublicationDecision"], "excluded")

        rendered = json.dumps(report)
        self.assertNotIn("test-key", rendered)
        for item in (self.selected, self.excluded, self.noise, self.outside_window):
            self.assertNotIn(item["title"], rendered)
            self.assertNotIn(item["description"], rendered)
            self.assertNotIn(item["link"], rendered)

    def test_disabled_mode_makes_no_calls(self) -> None:
        def post_json(*_args: object) -> dict:
            self.fail("disabled shadow must not call Jev")

        report = build_report(
            self.selection,
            "selection-sha",
            {},
            {"status": "not_run"},
            None,
            7,
            10,
            post_json=post_json,
            enabled=False,
        )
        self.assertEqual(report["status"], "disabled")
        self.assertEqual(report["results"], [])


if __name__ == "__main__":
    unittest.main()
