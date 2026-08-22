#!/usr/bin/env python3
"""Parse Meta Ads workflows and enforce their security and responsibility boundaries."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "collect": ROOT / ".github/workflows/meta-ads-tracker-collect.yml",
    "weekly": ROOT / ".github/workflows/meta-ads-tracker-weekly.yml",
    "review": ROOT / ".github/workflows/meta-ads-tracker-review.yml",
    "publish": ROOT / ".github/workflows/meta-ads-tracker-publish.yml",
    "ci": ROOT / ".github/workflows/meta-ads-tracker-ci.yml",
}
PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict[str, Any]:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(payload, dict):
        fail(f"workflow must be an object: {path}")
    return payload


def run_blocks(workflow: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                blocks.append(step["run"])
    return blocks


def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for job in workflow.get("jobs", {}).values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]


def require_pinned_actions(name: str, workflow: dict[str, Any]) -> None:
    for step in steps(workflow):
        uses = step.get("uses")
        if not isinstance(uses, str):
            continue
        action, separator, revision = uses.partition("@")
        if action not in PINNED_ACTIONS:
            continue
        if not separator or revision != PINNED_ACTIONS[action]:
            fail(f"{name} must pin {action} to its approved immutable SHA")


def main() -> int:
    try:
        parsed = {name: load(path) for name, path in WORKFLOWS.items()}
        for name, workflow in parsed.items():
            for block in run_blocks(workflow):
                if "${{ inputs." in block:
                    fail(f"{name} interpolates workflow input directly into shell code")
        for name in ("collect", "weekly", "publish"):
            group = parsed[name].get("concurrency", {}).get("group")
            if group != "meta-ads-tracker-repository-write":
                fail(f"{name} must share repository-write concurrency")
        for name in ("collect", "publish"):
            require_pinned_actions(name, parsed[name])
        publish_runs = "\n".join(run_blocks(parsed["publish"]))
        if "meta_ads_tracker_groq.py" in publish_runs or "GROQ_API_KEY" in str(parsed["publish"]):
            fail("publish workflow must not run Groq")
        if parsed["review"].get("permissions", {}).get("contents") != "read":
            fail("review workflow must be read-only")
        collect_runs = "\n".join(run_blocks(parsed["collect"]))
        if "meta_ads_tracker_weekly" in collect_runs:
            fail("daily workflow must not own weekly paths")
        collect_steps = steps(parsed["collect"])
        kill_switch = next((step for step in collect_steps if step.get("id") == "kill_switch"), None)
        if kill_switch is None or "META_ADS_TRACKER_COLLECT_ENABLED" not in str(kill_switch):
            fail("collect workflow must have a strict collector kill switch")
        if any(
            step is not kill_switch and "steps.kill_switch.outputs.enabled == 'true'" not in str(step.get("if", ""))
            for step in collect_steps
        ):
            fail("every collecting step after the kill switch must be gated")
        if 'git add -- "${CANDIDATE}" data/meta_ads_tracker_state.json' not in collect_runs:
            fail("collect workflow must stage only the current candidate and state")
        if "--governance config/meta_ads_source_governance.json" not in collect_runs:
            fail("collect workflow must validate source governance before collection")
        artifact = next((step for step in collect_steps if step.get("name") == "Upload daily candidate artifacts"), None)
        if not isinstance(artifact, dict) or artifact.get("with", {}).get("path") != "${{ steps.collect.outputs.candidate }}":
            fail("collect workflow must upload only the current candidate")
        artifact_with = artifact.get("with", {}) if isinstance(artifact, dict) else {}
        if artifact_with.get("if-no-files-found") != "error" or artifact_with.get("retention-days") != "30":
            fail("collect artifact must fail on absence and retain exactly 30 days")
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: parsed and checked {len(parsed)} Meta Ads workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
