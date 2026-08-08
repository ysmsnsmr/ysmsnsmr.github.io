"""Deterministic provenance manifests for local statement CSV outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import __version__


MANIFEST_VERSION = 1


def manifest_path_for_csv(csv_path: str | Path) -> Path:
    """Return the adjacent manifest path for a generated statement CSV."""
    return Path(csv_path).with_suffix(".manifest.json")


def sha256_file(path: str | Path) -> str:
    """Hash a local file without loading the complete file into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    manifest_path: str | Path,
    *,
    input_path: str | Path,
    rules_path: str | Path,
    csv_path: str | Path,
    statement_type: str,
) -> None:
    """Write a stable, privacy-minimal record for one CSV generation run."""
    output_path = Path(manifest_path)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "input_sha256": sha256_file(input_path),
        "rules_sha256": sha256_file(rules_path),
        "tool_version": __version__,
        "statement_type": statement_type,
        "csv_sha256": sha256_file(csv_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
