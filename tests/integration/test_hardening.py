"""Integration tests for ``sunset_it.core.hardening``.

The hardening phase runs an audit first and then plans/applies
scaffolding for the failing fixable checks. We assert:

* dry-run lists planned actions but writes nothing
* ``apply=True`` writes ``.gitignore``, the GitHub Actions
  workflow, and the knowledge templates flagged by audit
* a second ``apply=True`` is idempotent (no duplicate writes)
"""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.hardening import hardening


def test_hardening_dry_run_writes_nothing(tmp_repo: Path) -> None:
    report = hardening(tmp_repo, profile_name="solo-frozen", apply=False)
    assert report.apply is False
    assert report.actions_applied == []
    assert report.actions_planned, "expected at least one planned action"
    assert not (tmp_repo / ".gitignore").exists()
    assert not (tmp_repo / ".github" / "workflows" / "sunset.yml").exists()


def test_hardening_apply_creates_baseline(tmp_repo: Path) -> None:
    report = hardening(tmp_repo, profile_name="solo-frozen", apply=True)
    assert report.apply is True
    assert (tmp_repo / ".gitignore").read_text(encoding="utf-8").startswith("# ")
    workflow = tmp_repo / ".github" / "workflows" / "sunset.yml"
    assert workflow.exists()
    assert "sunset-it watch" in workflow.read_text(encoding="utf-8")
    # Knowledge templates flagged by audit should be there too.
    assert (tmp_repo / "AGENTS.md").exists()
    assert (tmp_repo / "docs" / "RUNBOOK.md").exists()


def test_hardening_apply_is_idempotent(tmp_repo: Path) -> None:
    first = hardening(tmp_repo, profile_name="solo-frozen", apply=True)
    second = hardening(tmp_repo, profile_name="solo-frozen", apply=True)
    # First run wrote files; second run should skip everything.
    assert any("wrote" in a for a in first.actions_applied)
    assert all(
        "skipped" in a or a == "" for a in second.actions_applied
    ), f"second pass should not re-write: {second.actions_applied}"


def test_hardening_solo_eol_profile_loads(tmp_repo: Path) -> None:
    report = hardening(tmp_repo, profile_name="solo-eol", apply=False)
    assert report.profile_name == "solo-eol"
