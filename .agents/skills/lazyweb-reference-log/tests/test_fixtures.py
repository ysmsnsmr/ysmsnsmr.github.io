#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SHARED_DIR = FIXTURES_DIR / "_shared"
VALIDATOR = SKILL_DIR / "scripts/lazyweb_reference_log.py"
INPUT_NAME = "2099-01-02-fixture-case"
INPUT_REL = Path("lazyweb/inbox") / INPUT_NAME
FINAL_REL = Path("lazyweb/output/lazyweb-reference-log-fixture-case.md")
NOW = "2026-08-04T10:00:00+08:00"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FixtureTest(unittest.TestCase):
    maxDiff = None

    def run_cli(self, root: Path, *arguments: str) -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), "--project-root", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        stream = completed.stdout.strip() or completed.stderr.strip()
        self.assertTrue(stream, msg=f"validator produced no JSON; stderr={completed.stderr}")
        return completed.returncode, json.loads(stream.splitlines()[-1])

    def arrange(self, case_name: str) -> tuple[Path, dict, str]:
        case = json.loads((FIXTURES_DIR / case_name / "case.json").read_text(encoding="utf-8"))
        temp_dir = Path(tempfile.mkdtemp(prefix=f"lazyweb-{case_name}-"))
        self.addCleanup(shutil.rmtree, temp_dir)

        input_dir = temp_dir / INPUT_REL
        input_dir.mkdir(parents=True)
        (temp_dir / "lazyweb/output").mkdir(parents=True)
        (temp_dir / "lazyweb/template").mkdir(parents=True)
        (temp_dir / ".agents/skills/lazyweb-reference-log").mkdir(parents=True)

        shutil.copy2(SHARED_DIR / "template.md", temp_dir / "lazyweb/template/reference-log-template.md")
        shutil.copy2(SKILL_DIR / "SKILL.md", temp_dir / ".agents/skills/lazyweb-reference-log/SKILL.md")
        if "article.md" not in case.get("omit", []):
            shutil.copy2(SHARED_DIR / "article.md", input_dir / "article.md")
        if "lazyweb-research.md" not in case.get("omit", []):
            shutil.copy2(SHARED_DIR / "research.md", input_dir / "lazyweb-research.md")
        (input_dir / "READY").write_text("ready\n", encoding="utf-8")

        draft = (SHARED_DIR / "valid-draft.md").read_text(encoding="utf-8")
        for old, new in case.get("replace", {}).items():
            self.assertIn(old, draft)
            draft = draft.replace(old, new, 1)
        if "existing_output" in case:
            (temp_dir / FINAL_REL).write_text(case["existing_output"], encoding="utf-8")
        return temp_dir, case, draft

    def exercise(self, case_name: str) -> None:
        root, case, draft = self.arrange(case_name)
        prepare_code, prepared = self.run_cli(
            root,
            "prepare",
            "--input-folder",
            INPUT_REL.as_posix(),
            "--now",
            NOW,
        )
        expected = case["expected_status"]

        if prepared["status"] != "ready":
            self.assertNotEqual(prepare_code, 0)
            self.assertEqual(prepared["status"], expected)
            self.assertFalse((root / INPUT_REL / "PROCESSED").exists())
            self.assertTrue((root / prepared["run_log"]).is_file())
            manifest = json.loads((root / prepared["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], expected)
            if expected == "missing_article":
                self.assertEqual(manifest["artifacts"]["article"]["state"], "missing")
                self.assertIsNone(manifest["artifacts"]["article"]["sha256"])
            if expected == "blocked_output_exists":
                final = root / FINAL_REL
                self.assertEqual(final.read_text(encoding="utf-8"), case["existing_output"])
                self.assertEqual(manifest["artifacts"]["output"]["state"], "existing_not_read")
                self.assertIsNone(manifest["artifacts"]["output"]["sha256"])
            return

        self.assertEqual(prepare_code, 0)
        temporary = root / prepared["temporary_output"]
        temporary.write_text(draft, encoding="utf-8")
        finalize_code, result = self.run_cli(
            root,
            "finalize",
            "--input-folder",
            INPUT_REL.as_posix(),
            "--temporary-output",
            prepared["temporary_output"],
            "--expected-context-sha256",
            prepared["context_sha256"],
        )
        self.assertEqual(result["status"], expected)

        if expected == "success":
            self.assertEqual(finalize_code, 0)
            final = root / result["final_output"]
            self.assertEqual(final.read_text(encoding="utf-8"), draft)
            self.assertFalse(temporary.exists())
            self.assertTrue((root / result["processed"]).is_file())
            manifest_path = root / result["manifest"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "success")
            expected_artifacts = {
                "article": root / INPUT_REL / "article.md",
                "research": root / INPUT_REL / "lazyweb-research.md",
                "template": root / "lazyweb/template/reference-log-template.md",
                "skill": root / ".agents/skills/lazyweb-reference-log/SKILL.md",
                "output": final,
            }
            for name, path in expected_artifacts.items():
                self.assertEqual(manifest["artifacts"][name]["sha256"], sha256(path))
            self.assertEqual(result["output_sha256"], sha256(final))
            self.assertTrue(manifest["safety_review"]["passed"])
        else:
            self.assertNotEqual(finalize_code, 0)
            self.assertTrue(temporary.is_file())
            self.assertFalse((root / FINAL_REL).exists())
            self.assertFalse((root / INPUT_REL / "PROCESSED").exists())
            manifest = json.loads((root / result["manifest"]).read_text(encoding="utf-8"))
            failed = {item["id"] for item in manifest["safety_review"]["checks"] if not item["passed"]}
            self.assertIn(case["expected_failed_check"], failed)

    def test_success(self) -> None:
        self.exercise("success")

    def test_missing_input(self) -> None:
        self.exercise("missing-input")

    def test_invalid_url(self) -> None:
        self.exercise("invalid-url")

    def test_output_collision(self) -> None:
        self.exercise("output-collision")

    def test_safety_violation(self) -> None:
        self.exercise("safety-violation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
