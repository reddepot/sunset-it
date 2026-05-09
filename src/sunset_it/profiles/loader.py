"""Profile loader: reads YAML from package resources or override directory.

Resolution order:
    1. ``profile_overrides_dir`` argument (explicit user override)
    2. Package resource ``sunset_it.profiles/{name}.yaml``

Profiles support a single-level ``extends:`` mechanism (deep-merge a
parent profile then apply this profile's overrides). No multi-level
inheritance — keeps the resolution understandable from a glance.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from sunset_it.models.profile import Profile


def _coerce_mapping(raw: Any, source: str) -> dict[str, Any]:
    """Reject YAML inputs that aren't a top-level mapping.

    Spec attack v0.1.1 (Codex P3): a hand-written profile that happens
    to deserialise as a list (e.g. accidentally starting with ``- foo:``)
    used to crash with ``AttributeError: 'list' object has no attribute
    'get'``. We now raise a domain-specific ``ValueError`` so the CLI
    layer can convert it to exit code 3 (misuse).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = (
            f"Profile YAML at {source} is not a mapping "
            f"(got {type(raw).__name__}). Expected a top-level dict "
            "with at least a 'name' key."
        )
        raise ValueError(msg)
    return raw


def _read_profile_yaml(name: str, override_dir: Path | None) -> dict[str, Any]:
    """Return the raw YAML mapping for ``name``."""
    if override_dir is not None:
        candidate = override_dir / f"{name}.yaml"
        if candidate.is_file():
            return _coerce_mapping(
                yaml.safe_load(candidate.read_text(encoding="utf-8")),
                str(candidate),
            )
    package_dir = resources.files("sunset_it.profiles")
    resource = package_dir / f"{name}.yaml"
    if not resource.is_file():
        msg = (
            f"Profile {name!r} not found "
            f"(override_dir={override_dir}, package={package_dir})"
        )
        raise FileNotFoundError(msg)
    return _coerce_mapping(
        yaml.safe_load(resource.read_text(encoding="utf-8")),
        str(resource),
    )


def _deep_merge(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two YAML mappings — child wins on key conflict."""
    out: dict[str, Any] = dict(parent)
    for key, value in child.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_profile(name: str, override_dir: Path | None = None) -> Profile:
    """Load a profile by name, applying ``extends`` once if present."""
    raw = _read_profile_yaml(name, override_dir)
    parent_name = raw.get("extends")
    if parent_name:
        parent_raw = _read_profile_yaml(parent_name, override_dir)
        # Strip the parent's own "extends" so we keep a single level.
        parent_raw = {k: v for k, v in parent_raw.items() if k != "extends"}
        raw = _deep_merge(parent_raw, raw)
        raw["extends"] = parent_name
    return Profile.model_validate(raw)


def list_profiles(override_dir: Path | None = None) -> list[str]:
    """Return all profile names visible to the loader."""
    out: set[str] = set()
    if override_dir is not None and override_dir.is_dir():
        out.update(p.stem for p in override_dir.glob("*.yaml"))
    package_dir = resources.files("sunset_it.profiles")
    for entry in package_dir.iterdir():
        if entry.name.endswith(".yaml"):
            out.add(entry.name.removesuffix(".yaml"))
    return sorted(out)
