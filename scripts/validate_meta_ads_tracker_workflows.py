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
        publish_runs = "\n".join(run_blocks(parsed["publish"]))
        if "meta_ads_tracker_groq.py" in publish_runs or "GROQ_API_KEY" in str(parsed["publish"]):
            fail("publish workflow must not run Groq")
        if parsed["review"].get("permissions", {}).get("contents") != "read":
            fail("review workflow must be read-only")
        collect_runs = "\n".join(run_blocks(parsed["collect"]))
        if "meta_ads_tracker_weekly" in collect_runs:
            fail("daily workflow must not own weekly paths")
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: parsed and checked {len(parsed)} Meta Ads workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
