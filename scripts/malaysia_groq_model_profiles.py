#!/usr/bin/env python3
"""Load the single model-profile registry used by the Malaysia Groq workflow."""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).with_name("malaysia_groq_model_profiles.json")
SAFE_ARTIFACT_KEY = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
RESPONSE_MODES = {"json_object", "json_schema_strict"}
REASONING_MODES = {"default", "low_hidden", "hidden"}
COMPARISON_PROMPT_LAYOUTS = {"production", "user_only", "user_only_explicit_contract"}
COMPARISON_CONTRACTS = {"editorial_entry_v2"}
DEFAULT_COMPARISON_MAX_TOKENS = 500
MAX_COMPARISON_MAX_TOKENS = 1200
DEFAULT_PRODUCTION_MAX_TOKENS = 500
MAX_PRODUCTION_MAX_TOKENS = 1200
DEFAULT_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS = 0
MAX_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS = 60


@dataclass(frozen=True)
class ModelProfile:
    name: str
    artifact_key: str
    model_id: str
    artifact_only: bool
    aliases: tuple[str, ...] = ()
    shutdown_date: str = ""
    preview: bool = False
    response_mode: str = "json_object"
    reasoning_mode: str = "default"
    comparison_prompt_layout: str = "production"
    comparison_max_tokens: int = DEFAULT_COMPARISON_MAX_TOKENS
    comparison_contract: str = "editorial_entry_v2"
    production_prompt_layout: str = "production"
    production_max_tokens: int = DEFAULT_PRODUCTION_MAX_TOKENS
    production_contract: str = "editorial_entry_v2"
    production_rate_reset_wait_max_seconds: int = DEFAULT_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS


@dataclass(frozen=True)
class ModelProfileRegistry:
    default_production_profile: str
    profiles: tuple[ModelProfile, ...]


def clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def load_model_profile_registry(path: Path = DEFAULT_CONFIG_PATH) -> ModelProfileRegistry:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("model profile config root must be an object")
    if value.get("schema_version") != "malaysia-groq-model-profiles/v2":
        raise ValueError("unsupported model profile schema")

    raw_profiles = value.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("model profile config must contain profiles")

    profiles: list[ModelProfile] = []
    known_names: set[str] = set()
    known_aliases: set[str] = set()
    known_artifact_keys: set[str] = set()
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            raise ValueError("model profile must be an object")
        name = clean_text(raw_profile.get("name"))
        artifact_key = clean_text(raw_profile.get("artifact_key"))
        model_id = clean_text(raw_profile.get("model_id"))
        response_mode = clean_text(raw_profile.get("response_mode"))
        reasoning_mode = clean_text(raw_profile.get("reasoning_mode"))
        comparison_prompt_layout = clean_text(raw_profile.get("comparison_prompt_layout")) or "production"
        comparison_max_tokens = raw_profile.get("comparison_max_tokens", DEFAULT_COMPARISON_MAX_TOKENS)
        comparison_contract = clean_text(raw_profile.get("comparison_contract")) or "editorial_entry_v2"
        production_prompt_layout = clean_text(raw_profile.get("production_prompt_layout")) or "production"
        production_max_tokens = raw_profile.get("production_max_tokens", DEFAULT_PRODUCTION_MAX_TOKENS)
        production_contract = clean_text(raw_profile.get("production_contract")) or "editorial_entry_v2"
        production_rate_reset_wait_max_seconds = raw_profile.get(
            "production_rate_reset_wait_max_seconds",
            DEFAULT_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS,
        )
        if not name or not model_id or not SAFE_ARTIFACT_KEY.fullmatch(artifact_key):
            raise ValueError("model profile requires a name, model_id, and safe artifact_key")
        if response_mode not in RESPONSE_MODES:
            raise ValueError(f"unsupported model profile response_mode: {response_mode}")
        if reasoning_mode not in REASONING_MODES:
            raise ValueError(f"unsupported model profile reasoning_mode: {reasoning_mode}")
        if comparison_prompt_layout not in COMPARISON_PROMPT_LAYOUTS:
            raise ValueError(
                "unsupported model profile comparison_prompt_layout: "
                f"{comparison_prompt_layout}"
            )
        if comparison_contract not in COMPARISON_CONTRACTS:
            raise ValueError(f"unsupported model profile comparison_contract: {comparison_contract}")
        if production_prompt_layout not in COMPARISON_PROMPT_LAYOUTS:
            raise ValueError(
                "unsupported model profile production_prompt_layout: "
                f"{production_prompt_layout}"
            )
        if production_contract not in COMPARISON_CONTRACTS:
            raise ValueError(f"unsupported model profile production_contract: {production_contract}")
        if (
            not isinstance(comparison_max_tokens, int)
            or isinstance(comparison_max_tokens, bool)
            or not 1 <= comparison_max_tokens <= MAX_COMPARISON_MAX_TOKENS
        ):
            raise ValueError(
                "model profile comparison_max_tokens must be an integer between "
                f"1 and {MAX_COMPARISON_MAX_TOKENS}"
            )
        if (
            not isinstance(production_max_tokens, int)
            or isinstance(production_max_tokens, bool)
            or not 1 <= production_max_tokens <= MAX_PRODUCTION_MAX_TOKENS
        ):
            raise ValueError(
                "model profile production_max_tokens must be an integer between "
                f"1 and {MAX_PRODUCTION_MAX_TOKENS}"
            )
        if (
            not isinstance(production_rate_reset_wait_max_seconds, int)
            or isinstance(production_rate_reset_wait_max_seconds, bool)
            or not 0 <= production_rate_reset_wait_max_seconds <= MAX_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS
        ):
            raise ValueError(
                "model profile production_rate_reset_wait_max_seconds must be an integer between "
                f"0 and {MAX_PRODUCTION_RATE_RESET_WAIT_MAX_SECONDS}"
            )
        if name in known_names or artifact_key in known_artifact_keys:
            raise ValueError("duplicate model profile name or artifact_key")

        raw_aliases = raw_profile.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise ValueError("model profile aliases must be a list")
        aliases = tuple(clean_text(alias) for alias in raw_aliases if clean_text(alias))
        lookup_values = {name.lower(), model_id.lower(), *(alias.lower() for alias in aliases)}
        if known_aliases & lookup_values:
            raise ValueError("duplicate model profile alias")

        profiles.append(
            ModelProfile(
                name=name,
                artifact_key=artifact_key,
                model_id=model_id,
                artifact_only=bool(raw_profile.get("artifact_only")),
                aliases=aliases,
                shutdown_date=clean_text(raw_profile.get("shutdown_date")),
                preview=bool(raw_profile.get("preview")),
                response_mode=response_mode,
                reasoning_mode=reasoning_mode,
                comparison_prompt_layout=comparison_prompt_layout,
                comparison_max_tokens=comparison_max_tokens,
                comparison_contract=comparison_contract,
                production_prompt_layout=production_prompt_layout,
                production_max_tokens=production_max_tokens,
                production_contract=production_contract,
                production_rate_reset_wait_max_seconds=production_rate_reset_wait_max_seconds,
            )
        )
        known_names.add(name)
        known_artifact_keys.add(artifact_key)
        known_aliases.update(lookup_values)

    default_name = clean_text(value.get("default_production_profile"))
    registry = ModelProfileRegistry(default_name, tuple(profiles))
    default_profile = resolve_model_profile(default_name, registry)
    if default_profile.artifact_only:
        raise ValueError("default production model profile cannot be artifact-only")
    return registry


def resolve_model_profile(value: str, registry: ModelProfileRegistry) -> ModelProfile:
    lookup = clean_text(value).lower()
    for profile in registry.profiles:
        profile_values = {
            profile.name.lower(),
            profile.model_id.lower(),
            *(alias.lower() for alias in profile.aliases),
        }
        if lookup in profile_values:
            return profile
    raise ValueError(f"unknown Groq model profile: {value}")


def production_model_profile(value: str, registry: ModelProfileRegistry) -> ModelProfile:
    profile = resolve_model_profile(value or registry.default_production_profile, registry)
    if profile.artifact_only:
        raise ValueError(f"artifact-only model profile cannot be used for production: {profile.name}")
    return profile


def artifact_only_model_profiles(registry: ModelProfileRegistry) -> tuple[ModelProfile, ...]:
    return tuple(profile for profile in registry.profiles if profile.artifact_only)


def production_profile_workflow_fields(profile: ModelProfile) -> tuple[str, ...]:
    return (
        profile.name,
        profile.artifact_key,
        profile.model_id,
        profile.production_prompt_layout,
        str(profile.production_max_tokens),
        profile.production_contract,
        str(profile.production_rate_reset_wait_max_seconds),
    )


def profile_for_model_id(value: str) -> ModelProfile:
    """Resolve configured models while preserving a safe JSON-object fallback for unknown IDs."""
    try:
        return resolve_model_profile(value, load_model_profile_registry())
    except ValueError:
        return ModelProfile(
            name=value or "legacy-model",
            artifact_key="legacy-model",
            model_id=value,
            artifact_only=False,
            response_mode="json_object",
            reasoning_mode="default",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve-production")
    resolve_parser.add_argument("profile", nargs="?", default="")
    resolve_parser.add_argument("--fallback-to-default", action="store_true")

    subparsers.add_parser("list-artifact-only")
    args = parser.parse_args()

    registry = load_model_profile_registry(args.config)
    if args.command == "resolve-production":
        try:
            profile = production_model_profile(args.profile, registry)
        except ValueError as error:
            if not args.fallback_to_default:
                raise
            profile = production_model_profile(registry.default_production_profile, registry)
            print(f"warning: {error}; using {profile.name}", file=sys.stderr)
        print("\t".join(production_profile_workflow_fields(profile)))
        return 0

    for profile in artifact_only_model_profiles(registry):
        print("\t".join((profile.name, profile.artifact_key, profile.model_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
