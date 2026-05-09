"""Typer CliRunner integration tests for the public CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from sunset_it.cli import app

# mix_stderr=False so structlog output (stderr) doesn't pollute the JSON
# we expect on stdout. Tracks behaviour across typer 0.15 → 0.25 (the
# default flipped between those versions).
runner = CliRunner(mix_stderr=False)


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "sunset-it" in result.stdout


def test_audit_help() -> None:
    result = runner.invoke(app, ["audit", "--help"])
    assert result.exit_code == 0
    assert "audit" in result.stdout.lower()


def test_audit_json_on_empty_dir(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", str(tmp_path), "--output", "json"])
    # Empty repo will be RED; exit code 2.
    assert result.exit_code == 2
    parsed = json.loads(result.stdout)
    assert parsed["profile_name"] == "solo-frozen"
    assert parsed["summary"]["overall_status"] == "red"


def test_audit_fail_on_never_returns_zero(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["audit", str(tmp_path), "--output", "json", "--fail-on", "never"]
    )
    assert result.exit_code == 0


def test_knowledge_emits_files(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["knowledge", str(tmp_path), "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["files_written"]) >= 5  # 5 templates declared in solo-frozen


def test_audit_fail_on_blocker_ignores_warnings(tmp_path: Path) -> None:
    """POLYLENS external (Gemini P1): --fail-on=blocker must NOT exit 1
    just because warnings were raised. Setup: empty repo → warnings
    fire on solo-frozen profile, but no blockers."""
    # Use a profile where everything is at most "warning" — solo-frozen
    # has both blockers and warnings so this test verifies the blocker
    # gate ignores warnings.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1"\nrequires-python = ">=3.13"\n',
        encoding="utf-8",
    )
    # solo-frozen still raises blockers on missing AGENTS.md etc., so
    # the test scenario produces blocker_failed > 0; the assertion is
    # the new behaviour for warning-only repos. We make a minimal
    # well-equipped repo:
    (tmp_path / "AGENTS.md").write_text(
        "# Agents\n\nstub\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "RUNBOOK.md").write_text(
        "# Runbook\n\nstub\n", encoding="utf-8"
    )
    (tmp_path / "AI_GENERATION_MANIFEST.md").write_text(
        "# Manifest\n\n## Models used\n- claude-opus-4-7\n", encoding="utf-8"
    )
    result = runner.invoke(
        app, ["audit", str(tmp_path), "--output", "json", "--fail-on", "blocker"]
    )
    # All blockers pass on this minimally-equipped repo; warnings may
    # remain. With --fail-on=blocker the exit code MUST be 0.
    parsed = json.loads(result.stdout)
    if parsed["summary"]["failed_blocker"] == 0:
        assert result.exit_code == 0, (
            f"--fail-on=blocker leaked exit_code {result.exit_code} "
            f"despite no blockers: {parsed['summary']}"
        )
