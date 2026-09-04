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
    "secondary_shadow": ROOT / ".github/workflows/meta-ads-tracker-secondary-shadow.yml",
    "friday_preflight": ROOT / ".github/workflows/meta-ads-tracker-friday-preflight.yml",
    "weekly_recovery": ROOT / ".github/workflows/meta-ads-tracker-weekly-recovery.yml",
    "recovery_promotion": ROOT / ".github/workflows/meta-ads-tracker-recovery-promote.yml",
    "presentation_backfill": ROOT / ".github/workflows/meta-ads-personal-feed-presentation-backfill.yml",
    "schema_probe": ROOT / ".github/workflows/meta-ads-personal-feed-groq-schema-probe.yml",
    "real_candidate_probe": ROOT / ".github/workflows/meta-ads-personal-feed-groq-real-candidate-probe.yml",
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
        for name in ("friday_preflight", "weekly_recovery", "recovery_promotion"):
            if r"\\n" in WORKFLOWS[name].read_text(encoding="utf-8"):
                fail(f"{name} must write GitHub output values with real newlines")
        for name in ("collect", "weekly", "publish", "friday_preflight", "weekly_recovery", "recovery_promotion", "presentation_backfill"):
            group = parsed[name].get("concurrency", {}).get("group")
            if group != "meta-ads-tracker-repository-write":
                fail(f"{name} must share repository-write concurrency")
        for name in ("collect", "publish", "secondary_shadow", "friday_preflight", "weekly_recovery", "recovery_promotion", "presentation_backfill"):
            require_pinned_actions(name, parsed[name])
        require_pinned_actions("schema_probe", parsed["schema_probe"])
        require_pinned_actions("real_candidate_probe", parsed["real_candidate_probe"])
        schema_probe = parsed["schema_probe"]
        probe_dispatch = schema_probe.get("on", {}).get("workflow_dispatch", {})
        probe_input = probe_dispatch.get("inputs", {}).get("field_count", {}) if isinstance(probe_dispatch, dict) else {}
        if not isinstance(probe_input, dict) or probe_input.get("type") != "choice" or probe_input.get("options") != ["1", "2", "4"]:
            fail("Groq schema probe must offer exactly one-, two-, or four-field choices")
        locale_input = probe_dispatch.get("inputs", {}).get("locale", {}) if isinstance(probe_dispatch, dict) else {}
        if not isinstance(locale_input, dict) or locale_input.get("type") != "choice" or locale_input.get("options") != ["en", "ja", "bilingual"]:
            fail("Groq schema probe must offer English, Japanese, and bilingual diagnostic choices")
        if schema_probe.get("permissions", {}).get("contents") != "read":
            fail("Groq schema probe must be read-only")
        probe_runs = "\n".join(run_blocks(schema_probe))
        if "meta_ads_groq_schema_probe.py" not in probe_runs:
            fail("Groq schema probe must run the dedicated diagnostic script")
        if any(value in probe_runs for value in ("meta_ads_personal_feed.py", "personal-feed.json", "meta_ads_personal_feed_state.json")):
            fail("Groq schema probe must not run the collector or write feed/state")
        probe_step = next((step for step in steps(schema_probe) if step.get("name") == "Probe one strict Groq schema request"), None)
        probe_env = probe_step.get("env", {}) if isinstance(probe_step, dict) else {}
        if not isinstance(probe_env, dict) or probe_env.get("GROQ_API_KEY") != "${{ secrets.GROQ_API_KEY }}":
            fail("Groq schema probe must provide the API key through the environment")
        if probe_env.get("FIELD_COUNT") != "${{ inputs.field_count }}":
            fail("Groq schema probe must pass field count through an environment variable")
        if probe_env.get("PROBE_LOCALE") != "${{ inputs.locale }}":
            fail("Groq schema probe must pass locale through an environment variable")
        real_probe = parsed["real_candidate_probe"]
        if real_probe.get("permissions", {}).get("contents") != "read":
            fail("Groq real-candidate probe must be read-only")
        real_runs = "\n".join(run_blocks(real_probe))
        if "meta_ads_groq_real_candidate_probe.py" not in real_runs:
            fail("Groq real-candidate probe must run the dedicated diagnostic script")
        if any(value in real_runs for value in ("git add", "git commit", "write_json", "upload-artifact")):
            fail("Groq real-candidate probe must not write repository files or artifacts")
        real_step = next(
            (step for step in steps(real_probe) if step.get("name") == "Probe one real candidate with the production bilingual prompt"),
            None,
        )
        real_env = real_step.get("env", {}) if isinstance(real_step, dict) else {}
        if not isinstance(real_env, dict) or real_env.get("GROQ_API_KEY") != "${{ secrets.GROQ_API_KEY }}":
            fail("Groq real-candidate probe must provide the API key through the environment")
        if real_env.get("PROBE_SOURCE_ID") != "${{ inputs.source_id }}":
            fail("Groq real-candidate probe must pass source ID through an environment variable")
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
        if "meta_ads_personal_feed.py" not in collect_runs or "validate_meta_ads_personal_feed.py" not in collect_runs:
            fail("collect workflow must build and validate the Personal Feed")
        if any(value in collect_runs for value in ("meta_ads_tracker_collect.py", "meta_ads_tracker_weekly", "meta_ads_tracker_decisions", "meta_ads_tracker_groq.py")):
            fail("Personal Feed collection must not depend on candidate, weekly, decision, or Groq stages")
        personal_collect = next((step for step in collect_steps if step.get("name") == "Collect Personal Feed sources"), None)
        personal_env = personal_collect.get("env", {}) if isinstance(personal_collect, dict) else {}
        if not isinstance(personal_env, dict) or personal_env.get("GROQ_API_KEY") != "${{ secrets.GROQ_API_KEY }}":
            fail("Personal Feed collection must provide the optional Japanese-presentation API key")
        if "META_ADS_PERSONAL_FEED_JA_ENABLED" not in personal_env or "META_ADS_PERSONAL_FEED_GROQ_MODEL" not in personal_env:
            fail("Personal Feed collection must expose Japanese-presentation controls")
        reseed_input = parsed["collect"].get("on", {}).get("workflow_dispatch", {}).get("inputs", {}).get("reseed_source_id", {})
        if not isinstance(reseed_input, dict) or reseed_input.get("type") != "string":
            fail("Personal Feed collection must expose a string-only source-local reseed input")
        if personal_env.get("META_ADS_PERSONAL_FEED_RESEED_SOURCE_ID") != "${{ inputs.reseed_source_id }}":
            fail("Personal Feed reseed input must pass through an environment variable")
        if '--reseed-source "${META_ADS_PERSONAL_FEED_RESEED_SOURCE_ID}"' not in collect_runs:
            fail("Personal Feed collection must pass the reseed environment value to Python")
        if 'git add -- data/meta_ads_personal_feed_state.json meta-ads-updates/personal-feed.json' not in collect_runs:
            fail("Personal Feed collection must stage only its explicit state and public feed paths")
        artifact = next((step for step in collect_steps if step.get("name") == "Upload Personal Feed artifact"), None)
        if not isinstance(artifact, dict) or artifact.get("with", {}).get("path") != "meta-ads-updates/personal-feed.json":
            fail("Personal Feed collection must upload only the current public feed")
        artifact_with = artifact.get("with", {}) if isinstance(artifact, dict) else {}
        if artifact_with.get("if-no-files-found") != "error" or artifact_with.get("retention-days") != "30":
            fail("collect artifact must fail on absence and retain exactly 30 days")
        backfill = parsed["presentation_backfill"]
        if "workflow_dispatch" not in backfill.get("on", {}):
            fail("Personal Feed presentation backfill must be manual only")
        backfill_inputs = backfill["on"]["workflow_dispatch"].get("inputs", {})
        limit_input = backfill_inputs.get("presentation_limit", {}) if isinstance(backfill_inputs, dict) else {}
        if limit_input.get("options") != [str(value) for value in range(1, 13)]:
            fail("Personal Feed presentation backfill must offer only limits 1 through 12")
        backfill_steps = steps(backfill)
        backfill_kill_switch = next((step for step in backfill_steps if step.get("id") == "kill_switch"), None)
        if backfill_kill_switch is None or "META_ADS_TRACKER_COLLECT_ENABLED" not in str(backfill_kill_switch):
            fail("Personal Feed presentation backfill must have the strict collector kill switch")
        if any(
            step is not backfill_kill_switch and "steps.kill_switch.outputs.enabled == 'true'" not in str(step.get("if", ""))
            for step in backfill_steps
        ):
            fail("every Personal Feed presentation-backfill step after the kill switch must be gated")
        backfill_runs = "\n".join(run_blocks(backfill))
        if "meta_ads_personal_feed.py" not in backfill_runs or "validate_meta_ads_personal_feed.py" not in backfill_runs:
            fail("Personal Feed presentation backfill must build and validate the Personal Feed")
        if '--presentation-limit "${PRESENTATION_LIMIT}"' not in backfill_runs:
            fail("Personal Feed presentation backfill must pass its bounded environment input to the collector")
        if any(value in backfill_runs for value in ("meta_ads_tracker_collect.py", "meta_ads_tracker_weekly", "meta_ads_tracker_decisions", "meta_ads_tracker_groq.py")):
            fail("Personal Feed presentation backfill must not depend on candidate, weekly, decision, or Groq stages")
        backfill_collect = next((step for step in backfill_steps if step.get("name") == "Generate bounded Japanese presentation backfill"), None)
        backfill_env = backfill_collect.get("env", {}) if isinstance(backfill_collect, dict) else {}
        if not isinstance(backfill_env, dict) or backfill_env.get("GROQ_API_KEY") != "${{ secrets.GROQ_API_KEY }}":
            fail("Personal Feed presentation backfill must provide the optional Japanese-presentation API key")
        if backfill_env.get("PRESENTATION_LIMIT") != "${{ inputs.presentation_limit }}":
            fail("Personal Feed presentation backfill must pass the input through an environment variable")
        if "META_ADS_PERSONAL_FEED_JA_ENABLED" not in backfill_env or "META_ADS_PERSONAL_FEED_GROQ_MODEL" not in backfill_env:
            fail("Personal Feed presentation backfill must expose Japanese-presentation controls")
        if 'git add -- data/meta_ads_personal_feed_state.json meta-ads-updates/personal-feed.json' not in backfill_runs:
            fail("Personal Feed presentation backfill must stage only its explicit state and public feed paths")
        backfill_artifact = next((step for step in backfill_steps if step.get("name") == "Upload Personal Feed backfill artifact"), None)
        if not isinstance(backfill_artifact, dict) or backfill_artifact.get("with", {}).get("path") != "meta-ads-updates/personal-feed.json":
            fail("Personal Feed presentation backfill must upload only the current public feed")
        backfill_artifact_with = backfill_artifact.get("with", {}) if isinstance(backfill_artifact, dict) else {}
        if backfill_artifact_with.get("if-no-files-found") != "error" or backfill_artifact_with.get("retention-days") != "30":
            fail("Personal Feed presentation-backfill artifact must fail on absence and retain exactly 30 days")
        preflight = parsed["friday_preflight"]
        preflight_steps = steps(preflight)
        preflight_kill_switch = next((step for step in preflight_steps if step.get("id") == "kill_switch"), None)
        if preflight_kill_switch is None or "META_ADS_TRACKER_COLLECT_ENABLED" not in str(preflight_kill_switch):
            fail("Friday preflight must have the strict collector kill switch")
        if any(
            step is not preflight_kill_switch and "steps.kill_switch.outputs.enabled == 'true'" not in str(step.get("if", ""))
            for step in preflight_steps
        ):
            fail("every Friday-preflight step after the kill switch must be gated")
        preflight_runs = "\n".join(run_blocks(preflight))
        if "meta_ads_tracker_weekly_recovery.py preflight" not in preflight_runs:
            fail("Friday preflight must create explicit weekly coverage evidence")
        if "env.RUN_BACKUP == 'true'" not in str(preflight) or "backup_eligible" not in str(preflight):
            fail("Friday backup collection must require an explicit human request and preflight eligibility")
        if 'git add -- "${CANDIDATE}" data/meta_ads_tracker_state.json' not in preflight_runs:
            fail("Friday preflight must stage only its backup candidate and state")
        preflight_artifact = next((step for step in preflight_steps if step.get("name") == "Upload Friday preflight evidence"), None)
        if not isinstance(preflight_artifact, dict) or preflight_artifact.get("with", {}).get("path") != "${{ steps.preflight.outputs.report }}":
            fail("Friday preflight must upload only its evidence report")
        preflight_artifact_with = preflight_artifact.get("with", {}) if isinstance(preflight_artifact, dict) else {}
        if preflight_artifact_with.get("if-no-files-found") != "error" or preflight_artifact_with.get("retention-days") != "30":
            fail("Friday preflight artifact must fail on absence and retain exactly 30 days")
        weekly_recovery = parsed["weekly_recovery"]
        recovery_runs = "\n".join(run_blocks(weekly_recovery))
        if "meta_ads_tracker_weekly_recovery.py recover" not in recovery_runs:
            fail("weekly recovery workflow must create only a recovery record")
        if any(value in recovery_runs for value in ("publish_meta_ads_tracker.py", "meta_ads_tracker_collect.py", "meta_ads_tracker_decisions", "meta-ads-updates")):
            fail("weekly recovery must not collect, publish, or modify decisions or UI")
        if 'git add -- "${RECOVERY}"' not in recovery_runs:
            fail("weekly recovery must stage only the resolved recovery record")
        recovery_steps = steps(weekly_recovery)
        recovery_artifact = next((step for step in recovery_steps if step.get("name") == "Upload non-public weekly recovery record"), None)
        if not isinstance(recovery_artifact, dict) or recovery_artifact.get("with", {}).get("path") != "${{ steps.recovery_path.outputs.path }}":
            fail("weekly recovery must upload only its recovery record")
        recovery_artifact_with = recovery_artifact.get("with", {}) if isinstance(recovery_artifact, dict) else {}
        if recovery_artifact_with.get("if-no-files-found") != "error" or recovery_artifact_with.get("retention-days") != "30":
            fail("weekly recovery artifact must fail on absence and retain exactly 30 days")
        promotion = parsed["recovery_promotion"]
        promotion_runs = "\n".join(run_blocks(promotion))
        if "meta_ads_tracker_recovery_promotion.py" not in promotion_runs:
            fail("recovery promotion workflow must build a promotion from immutable recovery data")
        if any(value in promotion_runs for value in ("meta_ads_tracker_collect.py", "meta_ads_tracker_groq.py")):
            fail("recovery promotion must not collect sources or run Groq")
        if 'git add -- "${PROMOTION}" meta-ads-updates/latest.json "${PUBLIC_WEEK}"' not in promotion_runs:
            fail("recovery promotion must stage only its promotion and explicit public report paths")
        promotion_steps = steps(promotion)
        promotion_artifact = next((step for step in promotion_steps if step.get("name") == "Upload delayed recovery promotion record"), None)
        if not isinstance(promotion_artifact, dict) or promotion_artifact.get("with", {}).get("path") != "${{ steps.paths.outputs.promotion }}":
            fail("recovery promotion must upload only its immutable promotion record")
        promotion_artifact_with = promotion_artifact.get("with", {}) if isinstance(promotion_artifact, dict) else {}
        if promotion_artifact_with.get("if-no-files-found") != "error" or promotion_artifact_with.get("retention-days") != "30":
            fail("recovery promotion artifact must fail on absence and retain exactly 30 days")
        shadow = parsed["secondary_shadow"]
        if shadow.get("concurrency", {}).get("group") != "meta-ads-tracker-secondary-shadow-state":
            fail("secondary shadow must use its dedicated state-branch concurrency group")
        if shadow.get("permissions", {}).get("contents") != "write":
            fail("secondary shadow needs contents: write only for its dedicated state branch")
        shadow_steps = steps(shadow)
        shadow_kill_switch = next((step for step in shadow_steps if step.get("id") == "kill_switch"), None)
        if shadow_kill_switch is None or "META_ADS_TRACKER_SHADOW_ENABLED" not in str(shadow_kill_switch):
            fail("secondary shadow must have a strict opt-in kill switch")
        if "${META_ADS_TRACKER_SHADOW_ENABLED:-false}" not in str(shadow_kill_switch):
            fail("secondary shadow must default to disabled when its variable is unset")
        if any(
            step is not shadow_kill_switch and "steps.kill_switch.outputs.enabled == 'true'" not in str(step.get("if", ""))
            for step in shadow_steps
        ):
            fail("every secondary-shadow step after the kill switch must be gated")
        shadow_runs = "\n".join(run_blocks(shadow))
        if any(path in shadow_runs for path in ("meta_ads_tracker_candidates", "meta_ads_tracker_weekly", "meta_ads_tracker_state.json", "meta-ads-updates")):
            fail("secondary shadow must not reference official candidates, state, weekly artifacts, or UI")
        if "automation/meta-ads-shadow-state" not in str(shadow):
            fail("secondary shadow must use the dedicated shadow state branch")
        if 'git add -- "${SHADOW_REPORT_FILE}" "${SHADOW_STATE_FILE}"' not in shadow_runs:
            fail("secondary shadow must stage only its report and state files explicitly")
        shadow_artifact = next((step for step in shadow_steps if step.get("name") == "Upload secondary shadow observation artifact"), None)
        if not isinstance(shadow_artifact, dict) or shadow_artifact.get("with", {}).get("path") != "${{ steps.collect.outputs.report }}":
            fail("secondary shadow must upload only the current observation report")
        shadow_artifact_with = shadow_artifact.get("with", {}) if isinstance(shadow_artifact, dict) else {}
        if shadow_artifact_with.get("if-no-files-found") != "error" or shadow_artifact_with.get("retention-days") != "30":
            fail("secondary shadow artifact must fail on absence and retain exactly 30 days")
        ci_runs = "\n".join(run_blocks(parsed["ci"]))
        if "validate_meta_ads_tracker_gate_b.py" not in ci_runs:
            fail("Tracker CI must validate the Gate B review-ledger contract")
        if "validate_meta_ads_tracker_weekly_recovery.py" not in ci_runs:
            fail("Tracker CI must validate non-public weekly recovery records")
        if "validate_meta_ads_tracker_recovery_promotion.py" not in ci_runs:
            fail("Tracker CI must validate delayed-recovery promotion records")
        if "validate_meta_ads_tracker_recovery_decisions.py" not in ci_runs:
            fail("Tracker CI must validate delayed-recovery human decisions")
        if "validate_meta_ads_personal_feed.py" not in ci_runs:
            fail("Tracker CI must validate the Personal Feed contract")
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: parsed and checked {len(parsed)} Meta Ads workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
