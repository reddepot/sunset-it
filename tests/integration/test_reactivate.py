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
    # No prior lockdown -> README has no banner.
    report = reactivate(
        tmp_repo,
        reason="Just probing the no-banner path.",
        profile_name="solo-frozen",
    )
    assert report.banner_removed is False
    assert "banner_absent" in " ".join(report.actions_skipped)


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
