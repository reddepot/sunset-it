"""Profile loading + extends inheritance."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sunset_it.profiles.loader import list_profiles, load_profile


def test_solo_frozen_loads() -> None:
    profile = load_profile("solo-frozen")
    assert profile.name == "solo-frozen"
    assert "lockfile_present" in profile.checks
    assert profile.checks["lockfile_present"].severity == "blocker"


def test_unknown_profile_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_profile("does-not-exist")


def test_list_profiles_includes_builtin() -> None:
    names = list_profiles()
    assert "solo-frozen" in names


def test_extends_deep_merges(tmp_path: Path) -> None:
    parent = {
        "name": "parent",
        "checks": {
            "lockfile_present": {"severity": "blocker", "enabled": True},
            "agents_md_present": {"severity": "warning", "enabled": True},
        },
    }
    child = {
        "name": "child",
        "extends": "parent",
        "checks": {
            "agents_md_present": {"severity": "blocker"},
        },
    }
    (tmp_path / "parent.yaml").write_text(yaml.safe_dump(parent), encoding="utf-8")
    (tmp_path / "child.yaml").write_text(yaml.safe_dump(child), encoding="utf-8")
    profile = load_profile("child", override_dir=tmp_path)
    assert profile.checks["lockfile_present"].severity == "blocker"
    # Child overrides agents_md_present severity from warning to blocker.
    assert profile.checks["agents_md_present"].severity == "blocker"
    assert profile.checks["agents_md_present"].enabled is True
