"""Smoke tests on each individual check.

Each check is exercised twice: once on a passing fixture, once on a
failing fixture. We don't mock the filesystem — checks operate on
``Path``, so a tmp_path is the simplest fixture.
"""

from __future__ import annotations

from pathlib import Path

from sunset_it.checks.adr_dir_present import run as run_adr
from sunset_it.checks.agents_md_present import run as run_agents
from sunset_it.checks.ai_generation_manifest import run as run_manifest
from sunset_it.checks.lockfile_present import run as run_lockfile
from sunset_it.checks.python_runtime_supported import run as run_python
from sunset_it.checks.readme_freeze_banner import run as run_banner
from sunset_it.checks.runbook_present import run as run_runbook
from sunset_it.checks.secrets_clean import run as run_secrets
from sunset_it.models.profile import ProfileCheckConfig

CFG_BLOCKER = ProfileCheckConfig(severity="blocker", enabled=True)
CFG_WARNING = ProfileCheckConfig(severity="warning", enabled=True)


def test_lockfile_present_pass(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text("[]\n", encoding="utf-8")
    result = run_lockfile(tmp_path, CFG_BLOCKER)
    assert result.passed is True


def test_lockfile_present_fail(tmp_path: Path) -> None:
    result = run_lockfile(tmp_path, CFG_BLOCKER)
    assert result.passed is False


def test_agents_md_present_pass(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    result = run_agents(tmp_path, CFG_BLOCKER)
    assert result.passed is True


def test_agents_md_present_with_cursor_rules_dir_passes(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "default.mdc").write_text("rules\n", encoding="utf-8")
    result = run_agents(tmp_path, CFG_BLOCKER)
    assert result.passed is True


def test_runbook_present_fail(tmp_path: Path) -> None:
    result = run_runbook(tmp_path, CFG_BLOCKER)
    assert result.passed is False


def test_runbook_present_pass(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "RUNBOOK.md").write_text("ok\n", encoding="utf-8")
    result = run_runbook(tmp_path, CFG_BLOCKER)
    assert result.passed is True


def test_ai_generation_manifest_pass(tmp_path: Path) -> None:
    (tmp_path / "AI_GENERATION_MANIFEST.md").write_text("# manifest\n", encoding="utf-8")
    result = run_manifest(tmp_path, CFG_WARNING)
    assert result.passed is True


def test_ai_generation_manifest_fail(tmp_path: Path) -> None:
    result = run_manifest(tmp_path, CFG_WARNING)
    assert result.passed is False


def test_adr_dir_present_below_min_count_fails(tmp_path: Path) -> None:
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "ADR-0001.md").write_text("a", encoding="utf-8")
    result = run_adr(tmp_path, CFG_WARNING)
    assert result.passed is False


def test_adr_dir_present_meets_min_count_passes(tmp_path: Path) -> None:
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    for i in range(3):
        (adr / f"ADR-000{i}.md").write_text("a", encoding="utf-8")
    result = run_adr(tmp_path, CFG_WARNING)
    assert result.passed is True


def test_readme_freeze_banner_pass(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# project\n\n> **Frozen as of 2026-05-09**\n", encoding="utf-8"
    )
    result = run_banner(tmp_path, CFG_WARNING)
    assert result.passed is True


def test_readme_freeze_banner_fail_no_keyword(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# project\n\nA description.\n", encoding="utf-8")
    result = run_banner(tmp_path, CFG_WARNING)
    assert result.passed is False


def test_secrets_clean_passes_on_empty_repo(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    result = run_secrets(tmp_path, CFG_BLOCKER)
    assert result.passed is True


def test_secrets_clean_detects_aws_key(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text(
        'KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8"
    )
    result = run_secrets(tmp_path, CFG_BLOCKER)
    assert result.passed is False
    assert "secret" in result.message.lower() or "rotate" in result.message.lower()


def test_python_runtime_supported_skips_without_pyproject(tmp_path: Path) -> None:
    result = run_python(tmp_path, CFG_WARNING)
    assert result.passed is True  # info-level skip


def test_python_runtime_supported_passes_for_311(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    result = run_python(tmp_path, CFG_WARNING)
    assert result.passed is True
