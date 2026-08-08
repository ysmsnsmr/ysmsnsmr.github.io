#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_model_profiles import (
    artifact_only_model_profiles,
    load_model_profile_registry,
    production_model_profile,
    resolve_model_profile,
)


class ModelProfileTest(unittest.TestCase):
    def test_registry_resolves_legacy_alias_and_artifact_profiles(self) -> None:
        registry = load_model_profile_registry()

        production = production_model_profile("llama", registry)
        self.assertEqual(production.model_id, "llama-3.3-70b-versatile")
        self.assertEqual(
            [profile.model_id for profile in artifact_only_model_profiles(registry)],
            [
                "openai/gpt-oss-20b",
                "openai/gpt-oss-120b",
                "qwen/qwen3.6-27b",
            ],
        )
        self.assertEqual(resolve_model_profile("gpt-oss", registry).name, "gpt-oss-20b")
        self.assertEqual(production.response_mode, "json_object")
        self.assertEqual(resolve_model_profile("gpt-oss", registry).reasoning_mode, "low_hidden")
        self.assertEqual(resolve_model_profile("gptoss120b", registry).comparison_prompt_layout, "user_only")
        self.assertEqual(resolve_model_profile("gptoss120b", registry).comparison_max_tokens, 800)
        self.assertEqual(resolve_model_profile("qwen36", registry).comparison_prompt_layout, "user_only_explicit_contract")

    def test_artifact_only_profile_is_rejected_for_production(self) -> None:
        registry = load_model_profile_registry()

        with self.assertRaisesRegex(ValueError, "artifact-only"):
            production_model_profile("gpt-oss-120b", registry)

    def test_workflow_contains_no_model_ids(self) -> None:
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/malaysia-rss-summary.yml").read_text(
            encoding="utf-8"
        )

        for profile in load_model_profile_registry().profiles:
            self.assertNotIn(profile.model_id, workflow)

    def test_duplicate_alias_is_rejected(self) -> None:
        config = {
            "schema_version": "malaysia-groq-model-profiles/v2",
            "default_production_profile": "one",
            "profiles": [
                {
                    "name": "one",
                    "artifact_key": "one",
                    "model_id": "model/one",
                    "artifact_only": False,
                    "aliases": ["shared"],
                    "response_mode": "json_object",
                    "reasoning_mode": "default",
                },
                {
                    "name": "two",
                    "artifact_key": "two",
                    "model_id": "model/two",
                    "artifact_only": True,
                    "aliases": ["shared"],
                    "response_mode": "json_object",
                    "reasoning_mode": "default",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate model profile alias"):
                load_model_profile_registry(path)

    def test_unknown_transport_modes_are_rejected(self) -> None:
        config = {
            "schema_version": "malaysia-groq-model-profiles/v2",
            "default_production_profile": "one",
            "profiles": [
                {
                    "name": "one",
                    "artifact_key": "one",
                    "model_id": "model/one",
                    "artifact_only": False,
                    "response_mode": "free_text",
                    "reasoning_mode": "default",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "response_mode"):
                load_model_profile_registry(path)

    def test_unknown_comparison_prompt_layout_is_rejected(self) -> None:
        config = {
            "schema_version": "malaysia-groq-model-profiles/v2",
            "default_production_profile": "one",
            "profiles": [
                {
                    "name": "one",
                    "artifact_key": "one",
                    "model_id": "model/one",
                    "artifact_only": False,
                    "response_mode": "json_object",
                    "reasoning_mode": "default",
                    "comparison_prompt_layout": "unknown",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "comparison_prompt_layout"):
                load_model_profile_registry(path)


if __name__ == "__main__":
    unittest.main()
