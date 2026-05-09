"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Iterator[Path]:
    """Initialise a minimal git repo under tmp_path. Used by integration tests."""
    git_bin = shutil.which("git")
    if git_bin is None:
        pytest.skip("git binary unavailable")
    subprocess.run(
        [git_bin, "init", "--initial-branch=main", "--quiet"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [git_bin, "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [git_bin, "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "README.md").write_text("# Sample\n", encoding="utf-8")
    subprocess.run(
        [git_bin, "add", "."],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [git_bin, "commit", "--quiet", "-m", "initial"],
        cwd=tmp_path,
        check=True,
    )
    yield tmp_path
