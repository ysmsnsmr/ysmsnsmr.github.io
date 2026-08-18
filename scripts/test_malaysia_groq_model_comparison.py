#!/usr/bin/env python3
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import load_model_profile_registry, resolve_model_profile
from run_malaysia_groq_model_comparison import run_artifact_profile


class ModelComparisonTest(unittest.TestCase):
    def test_probe_passes_but_empty_baseline_cohort_skips_quality_calls(self) -> None:
        registry = load_model_profile_registry()
        profile = resolve_model_profile("gpt-oss-20b", registry)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                output_dir=root / "comparison",
                json_input=root / "input.json",
                selected_json=root / "selected.json",
                rss_markdown_input=root / "fallback.md",
                cohort_output=root / "cohort.json",
                debug_groq=False,
            )
            with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), patch(
                "run_malaysia_groq_model_comparison.run_compatibility_probe",
                return_value={"probe_status": "passed", "rate_wait": "not_needed"},
            ), patch("run_malaysia_groq_model_comparison.run_command") as run_command:
                result = run_artifact_profile(profile, args, 1, [])

            self.assertEqual(result["run_status"], "skipped_no_quality_cohort")
            self.assertFalse(run_command.called)
            self.assertEqual(
                (args.output_dir / profile.artifact_key / "run_status.txt").read_text(encoding="utf-8"),
                "skipped_no_quality_cohort\n",
            )


if __name__ == "__main__":
    unittest.main()
