#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import load_model_profile_registry, production_model_profile
from run_malaysia_groq_model_comparison import (
    comparison_metrics,
    probe_contract_observation,
    probe_status_from_diagnostic,
    quality_cohort_links,
    update_golden_fixture,
)


class ModelComparisonTest(unittest.TestCase):
    def test_fixed_metrics_keep_requested_and_selected_fallback_rates_separate(self) -> None:
        improved = {
            "counts": {"requested": 4, "accepted": 1, "fallback": 3},
            "diagnostics": {
                "json_render_fallback_counts": {
                    "topic_fallback_count": 2,
                    "generic_fallback_count": 2,
                },
                "entry_candidate_observation": {"entry_contract_complete_count": 2},
                "entry_review_observation": {"reviewed_entry_available_count": 1},
                "json_render_summary_provenance": {
                    "line_counts": {"rss_derived": 7, "groq_replaced": 2, "groq_inherited": 1}
                },
            },
        }
        validator = {
            "passed": True,
            "counts": {"rendered_urls": 5},
            "url_validation": {"missing_selected_urls": []},
            "markdown_validation": {"forbidden_matches": []},
        }

        metrics = comparison_metrics(5, improved, validator)

        self.assertEqual(metrics["url_retention_rate"], 1.0)
        self.assertEqual(metrics["accepted_rate_of_requested"], 0.25)
        self.assertEqual(metrics["request_fallback_rate"], 0.75)
        self.assertEqual(metrics["selected_fallback_rate"], 0.8)
        self.assertEqual(metrics["groq_replaced_summary_line_rate"], 0.2)

        unavailable = comparison_metrics(5, None, None)
        self.assertIsNone(unavailable["url_retention_rate"])

    def test_golden_fixture_appends_failures_without_deleting_existing_items(self) -> None:
        registry = load_model_profile_registry()
        production = production_model_profile("llama", registry)
        selected = {
            "items": [
                {"title": "Existing", "link": "https://example.test/existing"},
                {"title": "New", "link": "https://example.test/new"},
            ]
        }
        improved = {
            "diagnostics": {
                "decision_records": [
                    {
                        "link": "https://example.test/new",
                        "requested": True,
                        "accepted": False,
                        "decision": "fallback",
                        "reason": "HTTP 429",
                    },
                    {
                        "link": "https://example.test/existing",
                        "requested": True,
                        "accepted": True,
                        "decision": "accepted",
                        "reason": "",
                    },
                ]
            }
        }
        existing_fixture = {
            "schema_version": "malaysia-groq-model-migration-golden/v1",
            "description": "fixture",
            "items": [
                {
                    "link": "https://example.test/existing",
                    "first_observed_on": "2026-08-01",
                    "production_profile": "llama33-70b",
                    "failure_reasons": ["ValueError"],
                    "item": {"title": "Existing", "link": "https://example.test/existing"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "golden.json"
            path.write_text(json.dumps(existing_fixture), encoding="utf-8")

            added = update_golden_fixture(path, selected, improved, production, "2026-08-04")
            result = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(added, 1)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["link"], "https://example.test/existing")
        self.assertEqual(result["items"][1]["failure_reasons"], ["HTTP 429"])

    def test_cohort_uses_requested_records_by_priority_then_index(self) -> None:
        improved = {
            "diagnostics": {
                "decision_records": [
                    {"link": "https://example.test/one", "requested": True, "force_all_priority": 10, "index": 1},
                    {"link": "https://example.test/two", "requested": True, "force_all_priority": 30, "index": 3},
                    {"link": "https://example.test/three", "requested": True, "force_all_priority": 30, "index": 2},
                ]
            }
        }

        self.assertEqual(
            quality_cohort_links(improved),
            ["https://example.test/three", "https://example.test/two"],
        )

    def test_metrics_separate_transport_contract_and_disabled_entry_review(self) -> None:
        improved = {
            "counts": {"requested": 2, "accepted": 1, "fallback": 1},
            "diagnostics": {
                "entry_review_observation": {"entry_review_policy": "disabled_for_model_comparison"},
                "decision_records": [
                    {
                        "link": "https://example.test/one",
                        "requested": True,
                        "accepted": True,
                        "groq_call": {"transport_status": "success", "json_contract_status": "valid"},
                    },
                    {
                        "link": "https://example.test/two",
                        "requested": True,
                        "accepted": False,
                        "reason": "HTTP 429",
                        "groq_call": {"transport_status": "rate_limited", "json_contract_status": "not_evaluated"},
                    },
                ],
            },
        }

        metrics = comparison_metrics(2, improved, None, ["https://example.test/one", "https://example.test/two"])

        self.assertEqual(metrics["entry_review_policy"], "disabled_for_model_comparison")
        self.assertIsNone(metrics["reviewed_entry_available_rate_of_requested"])
        self.assertEqual(metrics["transport_status_counts"], {"rate_limited": 1, "success": 1})
        self.assertEqual(metrics["json_contract_status_counts"], {"not_evaluated": 1, "valid": 1})
        self.assertEqual(metrics["quality_cohort"]["accepted_count"], 1)

    def test_probe_classifies_server_json_validation_as_contract_failure(self) -> None:
        diagnostic = {
            "transport_status": "http_error",
            "http_status": 400,
            "json_contract_status": "not_evaluated",
            "error": {"code": "json_validate_failed"},
        }

        self.assertEqual(probe_status_from_diagnostic(diagnostic), "contract_failed")
        self.assertEqual(
            probe_contract_observation({"diagnostic": diagnostic}),
            {
                "transport_status": "http_error",
                "json_contract_status": "not_evaluated",
                "contract_observation": "server_json_validate_failed",
                "error_code": "json_validate_failed",
            },
        )

    def test_probe_keeps_network_errors_as_transport_failure(self) -> None:
        self.assertEqual(
            probe_status_from_diagnostic(
                {
                    "transport_status": "network_error",
                    "http_status": None,
                    "error": {"code": ""},
                }
            ),
            "transport_failed",
        )


if __name__ == "__main__":
    unittest.main()
