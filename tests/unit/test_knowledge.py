"""Knowledge phase: template emission tests."""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.knowledge import knowledge


def test_knowledge_writes_default_set(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    report = knowledge(tmp_path, profile_name="solo-frozen")
    written = {p.name for p in report.files_written}
    assert "AGENTS.md" in written
    assert "RUNBOOK.md" in written
    assert "AI_GENERATION_MANIFEST.md" in written
    assert "SUNSET_NOTICE.md" in written
    assert "LESSONS.md" in written
    # No file should fail.
    assert report.files_failed == []


def test_knowledge_skips_existing_unless_overwrite(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# already here\n", encoding="utf-8")
    report = knowledge(tmp_path, profile_name="solo-frozen", overwrite=False)
    assert any(p.name == "AGENTS.md" for p in report.files_skipped_existing)
    # Force overwrite.
    report2 = knowledge(tmp_path, profile_name="solo-frozen", overwrite=True)
    assert any(p.name == "AGENTS.md" for p in report2.files_written)


def test_knowledge_uses_pyproject_name(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-cool-project"\nversion = "0.1"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    knowledge(tmp_path, profile_name="solo-frozen")
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "my-cool-project" in agents
