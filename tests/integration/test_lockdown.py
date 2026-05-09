"""End-to-end lockdown phase tests on a real git repo (tmp_repo fixture)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sunset_it.core.lockdown import lockdown
from sunset_it.utils.git import has_branch, has_tag


def test_lockdown_creates_tag_branch_banner(tmp_repo: Path) -> None:
    report = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=True)
    assert report.tag_created is not None
    assert report.tag_created.startswith("freeze-")
    assert has_tag(tmp_repo, report.tag_created)
    assert report.branch_created == "maintenance"
    assert has_branch(tmp_repo, "maintenance")
    assert report.readme_banner_added is True
    readme = (tmp_repo / "README.md").read_text(encoding="utf-8")
    assert "Frozen" in readme
    assert "freeze-banner" in readme


def test_lockdown_idempotent(tmp_repo: Path) -> None:
    first = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=True)
    # Commit the README change so the working tree is clean for the second pass.
    subprocess.run(["git", "-C", str(tmp_repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_repo), "commit", "-m", "banner", "--quiet"],
        check=True,
    )
    second = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=False)
    # Tag and branch already exist; the second pass should skip them.
    assert any("tag_already_exists" in s for s in second.actions_skipped)
    assert any("branch_already_exists" in s for s in second.actions_skipped)
    assert any("readme_banner_already_present" in s for s in second.actions_skipped)
    assert first.tag_created is not None
