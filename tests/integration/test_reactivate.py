"""Integration tests for ``sunset_it.core.reactivate``.

We exercise the full flow:

1. Run lockdown to install the freeze banner + tag + branch.
2. Run reactivate to strip the banner and tag the unfreeze.
3. Re-run reactivate to assert idempotence (banner already gone).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from sunset_it.core.lockdown import lockdown
from sunset_it.core.reactivate import reactivate


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()


def test_reactivate_round_trip(tmp_repo: Path) -> None:
    lockdown_report = lockdown(tmp_repo, profile_name="solo-frozen")
    assert lockdown_report.tag_created
    assert lockdown_report.readme_banner_added

    report = reactivate(
        tmp_repo,
        reason="Critical bug in serialization needs a patch release.",
        profile_name="solo-frozen",
    )
    assert report.banner_removed is True
    assert report.unfreeze_tag is not None
    assert report.unfreeze_tag.startswith("unfrozen-")

    readme_text = (tmp_repo / "README.md").read_text(encoding="utf-8")
    assert "sunset-it:freeze-banner" not in readme_text

    tags = _git(tmp_repo, "tag", "--list").splitlines()
    assert lockdown_report.tag_created in tags  # freeze tag retained
    assert report.unfreeze_tag in tags


def test_reactivate_idempotent_when_no_banner(tmp_repo: Path) -> None:
    # No prior lockdown -> README has no banner. Use --skip-branch-check
    # because the strict default refuses without a maintenance branch.
    report = reactivate(
        tmp_repo,
        reason="Just probing the no-banner path.",
        profile_name="solo-frozen",
        require_maintenance_branch=False,
    )
    assert report.banner_removed is False
    assert "banner_absent" in " ".join(report.actions_skipped)


def test_reactivate_refuses_without_maintenance_branch_by_default(tmp_repo: Path) -> None:
    """POLYLENS v0.2.1 (Kimi+Qwen P2): strict-by-default."""
    report = reactivate(
        tmp_repo,
        reason="No lockdown happened — should refuse.",
        profile_name="solo-frozen",
    )
    assert report.unfreeze_tag is None
    assert any(s.startswith("maintenance_branch_missing") for s in report.actions_skipped)


def test_reactivate_invalid_tag_name(tmp_repo: Path) -> None:
    report = reactivate(
        tmp_repo,
        reason="x",
        unfreeze_tag_name="bad name with spaces",
        profile_name="solo-frozen",
    )
    assert report.unfreeze_tag is None
    assert any(s.startswith("invalid_unfreeze_tag_name") for s in report.actions_skipped)


def test_reactivate_refuses_dirty_tree(tmp_repo: Path) -> None:
    (tmp_repo / "uncommitted.txt").write_text("dirty", encoding="utf-8")
    report = reactivate(
        tmp_repo,
        reason="x",
        profile_name="solo-frozen",
    )
    assert report.unfreeze_tag is None
    assert any(s.startswith("working_tree_dirty") for s in report.actions_skipped)


def test_reactivate_rejects_symlink_readme_outside_repo(tmp_repo: Path, tmp_path: Path) -> None:
    """POLYLENS v0.2.1 (Kimi P0): refuse to write through escaping symlinks."""
    # Create a "victim" file outside the repo.
    victim = tmp_path / "outside_repo.txt"
    victim.write_text("# original\n", encoding="utf-8")

    # Replace README.md with a symlink pointing out of the repo.
    (tmp_repo / "README.md").unlink()
    (tmp_repo / "README.md").symlink_to(victim)

    # Even with a banner-shaped victim, _readme_path should refuse the
    # symlink and skip banner removal entirely.
    victim.write_text(
        "# external\n<!-- sunset-it:freeze-banner -->\nfrozen\n"
        "<!-- /sunset-it:freeze-banner -->\n",
        encoding="utf-8",
    )

    report = reactivate(
        tmp_repo,
        reason="probe symlink",
        profile_name="solo-frozen",
        require_maintenance_branch=False,
    )

    # The victim must be untouched.
    assert victim.read_text(encoding="utf-8").startswith("# external\n")
    assert report.banner_removed is False
