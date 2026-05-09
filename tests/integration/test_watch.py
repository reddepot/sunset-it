"""Integration tests for ``sunset_it.core.watch``.

We don't depend on the live ``pip-audit`` binary in CI; what we
verify is the *plumbing*: the static EOL/model snapshots fire
correctly on a controlled fixture, and ``watch_to_gh_summary``
produces well-formed Markdown.
"""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.watch import watch, watch_to_gh_summary


def test_watch_no_signals_clean_repo(tmp_repo: Path) -> None:
    report = watch(tmp_repo, profile_name="solo-frozen")
    # Empty repo with only README: no manifest, no pyproject -> no alerts.
    assert report.alerts == []
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


def test_watch_to_gh_summary_empty_alerts(tmp_repo: Path) -> None:
    report = watch(tmp_repo, profile_name="solo-frozen")
    md = watch_to_gh_summary(report)
    assert md.startswith("## sunset-it watch — no alerts")


def test_watch_to_gh_summary_with_alerts(tmp_repo: Path) -> None:
    (tmp_repo / "AI_GENERATION_MANIFEST.md").write_text(
        "## Models used\n- claude-3-opus-20240229\n", encoding="utf-8"
    )
    report = watch(tmp_repo, profile_name="solo-eol")
    md = watch_to_gh_summary(report)
    assert "## sunset-it watch — alerts" in md
    assert "| Kind | Severity | Subject | Reason |" in md
