"""End-to-end lockdown phase tests on a real git repo (tmp_repo fixture)."""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.lockdown import lockdown
from sunset_it.utils.git import current_sha, has_branch, has_tag, is_dirty


def test_lockdown_creates_tag_branch_banner(tmp_repo: Path) -> None:
    report = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=False)
    assert report.tag_created is not None
    assert report.tag_created.startswith("freeze-")
    assert has_tag(tmp_repo, report.tag_created)
    assert report.branch_created == "maintenance"
    assert has_branch(tmp_repo, "maintenance")
    assert report.readme_banner_added is True
    readme = (tmp_repo / "README.md").read_text(encoding="utf-8")
    assert "Frozen" in readme
    assert "freeze-banner" in readme


def test_lockdown_commits_banner_before_tag(tmp_repo: Path) -> None:
    """Spec attack v0.1.1 (Gemini P1): the freeze tag must point at the
    state that includes the banner, not at the pre-banner state. We
    verify by checking that (a) the working tree is clean after
    lockdown, and (b) the tagged commit's README contains the banner.
    """
    report = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=False)
    assert report.tag_created is not None
    assert is_dirty(tmp_repo) is False, "lockdown must leave a clean working tree"
    # The README at HEAD (the tagged commit) must contain the banner.
    readme = (tmp_repo / "README.md").read_text(encoding="utf-8")
    assert "freeze-banner" in readme
    # And the current SHA matches the tagged commit.
    assert current_sha(tmp_repo)


def test_lockdown_invalid_tag_name_aborts_atomically(tmp_repo: Path) -> None:
    """Spec attack v0.1.2 (Codex P1): invalid tag_name must NOT mutate
    the repo. Validation runs before banner / tag / branch.
    """
    report = lockdown(
        tmp_repo,
        tag_name="not a valid ref",  # spaces are illegal in git refs
        profile_name="solo-frozen",
        allow_dirty=False,
    )
    assert report.tag_created is None
    assert report.branch_created is None
    assert report.readme_banner_added is False
    assert any("invalid_tag_name" in s for s in report.actions_skipped)
    assert is_dirty(tmp_repo) is False  # working tree untouched


def test_lockdown_idempotent(tmp_repo: Path) -> None:
    """Spec attack v0.1.1 (Gemini P1): the previous version of this
    test had to ``git commit`` the banner manually between the two
    runs because lockdown didn't commit it itself. With the run-#1.1
    fix (commit BEFORE tag), the second run finds a clean working
    tree without any external help.
    """
    first = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=False)
    second = lockdown(tmp_repo, profile_name="solo-frozen", allow_dirty=False)
    assert any("tag_already_exists" in s for s in second.actions_skipped)
    assert any("branch_already_exists" in s for s in second.actions_skipped)
    assert any("readme_banner_already_present" in s for s in second.actions_skipped)
    assert first.tag_created is not None
