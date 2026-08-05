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


@dataclass(frozen=True)
class ModelProfile:
    name: str
    artifact_key: str
    model_id: str
    artifact_only: bool
    aliases: tuple[str, ...] = ()
    shutdown_date: str = ""
    preview: bool = False


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
    if value.get("schema_version") != "malaysia-groq-model-profiles/v1":
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
        if not name or not model_id or not SAFE_ARTIFACT_KEY.fullmatch(artifact_key):
            raise ValueError("model profile requires a name, model_id, and safe artifact_key")
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
        print("\t".join((profile.name, profile.artifact_key, profile.model_id)))
        return 0

    for profile in artifact_only_model_profiles(registry):
        print("\t".join((profile.name, profile.artifact_key, profile.model_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
