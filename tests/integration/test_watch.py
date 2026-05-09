"""Integration tests for ``sunset_it.core.watch``.

We don't depend on the live ``pip-audit`` binary in CI; what we
verify is the *plumbing*: the static EOL/model snapshots fire
correctly on a controlled fixture, and ``watch_to_gh_summary``
produces well-formed Markdown.
"""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.watch import watch, watch_to_gh_summary


def test_watch_meta_alert_when_nothing_checkable(tmp_repo: Path) -> None:
    """POLYLENS v0.2.1 (Kimi+Qwen P1): empty repo must surface a meta-alert.

    The pre-fix behaviour returned an empty alert list, which an operator
    might mistake for "all good". The fix emits a meta:watch_uncheckable
    alert whenever every source skipped.
    """
    report = watch(tmp_repo, profile_name="solo-frozen")
    assert any(a.kind == "meta" and a.subject == "watch_uncheckable" for a in report.alerts)
    assert "model_deprecation:skipped" in " ".join(report.sources_skipped)


def test_watch_flags_deprecated_model_in_manifest(tmp_repo: Path) -> None:
    (tmp_repo / "AI_GENERATION_MANIFEST.md").write_text(
        "# Manifest\n\n## Models used\n\n- claude-3-opus-20240229 (deprecated)\n",
        encoding="utf-8",
    )
    # solo-eol has window 365d — captures the long-past 2026-01-05 EOL.
    report = watch(tmp_repo, profile_name="solo-eol")
    assert any(a.kind == "model_deprecation" for a in report.alerts)


def test_watch_flags_eol_python(tmp_repo: Path) -> None:
    # 3.9 reached EOL 2025-10-31; on 2026-05-09 it is past EOL,
    # so any non-zero window should fire.
    (tmp_repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.0.0"\nrequires-python = ">=3.9"\n',
        encoding="utf-8",
    )
    report = watch(tmp_repo, profile_name="solo-frozen")
    py_alerts = [a for a in report.alerts if a.kind == "python_eol"]
    assert py_alerts, "expected a Python EOL alert for 3.9"


def test_watch_to_gh_summary_with_meta_alert(tmp_repo: Path) -> None:
    """An empty repo now produces a meta-alert (POLYLENS v0.2.1)."""
    report = watch(tmp_repo, profile_name="solo-frozen")
    md = watch_to_gh_summary(report)
    assert "## sunset-it watch — alerts" in md
    assert "meta" in md and "watch_uncheckable" in md


def test_watch_to_gh_summary_with_alerts(tmp_repo: Path) -> None:
    (tmp_repo / "AI_GENERATION_MANIFEST.md").write_text(
        "## Models used\n- claude-3-opus-20240229\n", encoding="utf-8"
    )
    report = watch(tmp_repo, profile_name="solo-eol")
    md = watch_to_gh_summary(report)
    assert "## sunset-it watch — alerts" in md
    assert "| Kind | Severity | Subject | Reason |" in md


def test_watch_word_boundary_avoids_substring_false_positive(tmp_repo: Path) -> None:
    """POLYLENS v0.2.2 (Kimi+Qwen+GLM P1): substring → word-boundary.

    The previous behaviour matched any ``model_id`` that appeared as a
    substring. Critical case: ``gpt-4-0314`` is a *prefix* of the
    hypothetical ``gpt-4-0314-vnext``. With word-boundary semantics,
    only the exact id matches; the longer id alone must NOT trigger
    a deprecation alert for the shorter one.
    """
    (tmp_repo / "AI_GENERATION_MANIFEST.md").write_text(
        "## Models used\n\n"
        "- We migrated to `gpt-4-0314-vnext` (a fictional successor).\n"
        "- We also still use gpt-4-turbo verbatim.\n",
        encoding="utf-8",
    )
    report = watch(tmp_repo, profile_name="solo-eol")
    subjects = {a.subject for a in report.alerts if a.kind == "model_deprecation"}
    # gpt-4-0314 is a *prefix* of gpt-4-0314-vnext — must NOT trigger.
    assert "gpt-4-0314" not in subjects, (
        "Word-boundary regex should not let a prefix-only mention fire"
    )
    # gpt-4-turbo appears at a word boundary — must trigger.
    assert "gpt-4-turbo" in subjects


def test_watch_pipe_escape_in_gh_summary(tmp_repo: Path) -> None:
    """POLYLENS v0.2.2 (Kimi+Qwen+GLM P1): table-breaking pipes."""
    from sunset_it.core.watch import watch_to_gh_summary

    (tmp_repo / "AI_GENERATION_MANIFEST.md").write_text(
        "## Models used\n- gpt-4-turbo\n", encoding="utf-8"
    )
    report = watch(tmp_repo, profile_name="solo-eol")
    md = watch_to_gh_summary(report)
    # No raw pipe inside a row beyond the column separators (5 pipes per row).
    for line in md.splitlines():
        if line.startswith("| ") and "model_deprecation" in line:
            assert line.count("|") == 5, f"row should have 5 pipes: {line!r}"
