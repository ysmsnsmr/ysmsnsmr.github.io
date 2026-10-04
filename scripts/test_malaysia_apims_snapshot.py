#!/usr/bin/env python3
import unittest
from pathlib import Path
from types import SimpleNamespace

from malaysia_apims_snapshot import build_snapshot, render_preview


def article(title: str, description: str, index: int, body: str = "") -> dict:
    return {
        "title": title,
        "description": description,
        "body_evidence_excerpt": body,
        "source": f"Source {index}",
        "link": f"https://example.test/{index}",
        "published_at": f"2026-10-03T{index + 8:02d}:00:00+08:00",
    }


class APIMSSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selected = {"items": [
            article("Haze: Sri Aman API readings", "Sri Aman API 152 at 9am.", 1),
            article("Jerebu: Pasir Gudang IPU", "Pasir Gudang IPU 155 at 5pm.", 2),
            article("Bursa market report", "API for trading changed.", 3),
        ]}

    def test_keeps_area_values_times_and_sources_separate(self) -> None:
        calls = []

        def request(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(parsed={"readings": [
                {"article_id": 1, "area_source_text": "Sri Aman", "api_value": 152,
                 "observed_at_source_text": "9am", "evidence_quote": "Sri Aman API 152 at 9am."},
                {"article_id": 2, "area_source_text": "Pasir Gudang", "api_value": 155,
                 "observed_at_source_text": "5pm", "evidence_quote": "Pasir Gudang IPU 155 at 5pm."},
            ]}, diagnostic={"transport_status": "success", "json_contract_status": "valid"})

        result = build_snapshot(self.selected, api_key="fixture-key", model_name="gpt-oss-120b", request=request)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["articleCount"], 2)
        self.assertEqual([(row["area_source_text"], row["api_value"], row["observed_at_source_text"])
                          for row in result["readings"]], [("Sri Aman", 152, "9am"), ("Pasir Gudang", 155, "5pm")])
        self.assertFalse(result["productionEffect"])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("fixture-key", str(result))
        preview = render_preview(result)
        self.assertIn("## Sri Aman\n\n- API/IPU 152（9am、Source 1）", preview)
        self.assertIn("## Pasir Gudang\n\n- API/IPU 155（5pm、Source 2）", preview)

    def test_rejects_invented_or_cross_article_evidence(self) -> None:
        result = build_snapshot(
            self.selected, api_key="key", model_name="gpt-oss-120b",
            request=lambda **_: SimpleNamespace(parsed={"readings": [
                {"article_id": 1, "area_source_text": "Sri Aman", "api_value": 155,
                 "observed_at_source_text": "9am", "evidence_quote": "Sri Aman API 152 at 9am."},
                {"article_id": 1, "area_source_text": "Pasir Gudang", "api_value": 155,
                 "observed_at_source_text": "5pm", "evidence_quote": "Pasir Gudang IPU 155 at 5pm."},
            ]}, diagnostic={}),
        )
        self.assertEqual(result["status"], "no_verified_readings")
        self.assertEqual(result["rejectedReadingCount"], 2)

    def test_unknown_observation_time_is_not_publication_time(self) -> None:
        self.selected["items"][0]["description"] = "Sri Aman API 152."
        result = build_snapshot(
            self.selected, api_key="key", model_name="gpt-oss-120b",
            request=lambda **_: SimpleNamespace(parsed={"readings": [
                {"article_id": 1, "area_source_text": "Sri Aman", "api_value": 152,
                 "observed_at_source_text": None, "evidence_quote": "Sri Aman API 152."},
            ]}, diagnostic={}),
        )
        self.assertEqual(result["readings"][0]["observation_time_status"], "unknown")
        self.assertIn("観測時刻不明", render_preview(result))

    def test_real_report_shape_preserves_morning_and_evening_readings(self) -> None:
        selected = {"items": [
            article(
                "Jerebu: IPU di Serian, Sri Aman menurun namun kekal tidak sihat setakat 5 petang",
                "Pasir Gudang di Johor kekal merekodkan bacaan IPU tertinggi di negara ini pada paras 155.", 1,
            ),
            article(
                "Four areas in Johor and Sarawak still in unhealthy API range, Sri Aman highest at 152",
                "Four areas recorded unhealthy Air Pollutant Index (API) readings as of 9am today.", 2,
                "Sri Aman in Sarawak recorded the highest reading at 152, followed by Pasir Gudang, Johor (151).",
            ),
        ]}
        captured = []

        def request(**kwargs):
            captured.append(kwargs["messages"][0]["content"])
            return SimpleNamespace(parsed={"readings": [
                {"article_id": 1, "area_source_text": "Pasir Gudang", "api_value": 155,
                 "observed_at_source_text": "5 petang",
                 "evidence_quote": "Pasir Gudang di Johor kekal merekodkan bacaan IPU tertinggi di negara ini pada paras 155."},
                {"article_id": 2, "area_source_text": "Pasir Gudang", "api_value": 151,
                 "observed_at_source_text": "9am today", "evidence_quote": "Pasir Gudang, Johor (151)"},
            ]}, diagnostic={})

        result = build_snapshot(selected, api_key="key", model_name="gpt-oss-120b", request=request)
        self.assertEqual([row["api_value"] for row in result["readings"]], [155, 151])
        self.assertEqual([row["observed_at_source_text"] for row in result["readings"]],
                         ["5 petang", "9am today"])
        self.assertIn("setakat 5 petang", captured[0])
        self.assertIn("as of 9am today", captured[0])

    def test_no_key_or_few_reports_makes_no_call(self) -> None:
        def unexpected(**kwargs):
            self.fail("request should not be sent")

        self.assertEqual(build_snapshot(self.selected, api_key=None, model_name="gpt-oss-120b",
                                        request=unexpected)["status"], "skipped_missing_api_key")
        self.assertEqual(build_snapshot({"items": self.selected["items"][:1]}, api_key="key",
                                        model_name="gpt-oss-120b", request=unexpected)["status"],
                         "skipped_insufficient_reports")

    def test_manual_workflow_opt_in_and_artifact(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/malaysia-rss-summary.yml").read_text()
        self.assertIn("enable_apims_snapshot:", workflow)
        self.assertIn("inputs.enable_apims_snapshot", workflow)
        self.assertIn("apims_snapshot_preview.md", workflow)


if __name__ == "__main__":
    unittest.main()
