"""Thin wrappers around the ``git`` binary.

We shell out rather than depend on ``GitPython``: keeps the runtime
small, makes errors explicit, avoids version-skew with system Git.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git invocation fails."""


def _git(repo: Path, *args: str, check: bool = True, timeout: float = 15.0) -> str:
    """Run ``git`` in ``repo`` and return stdout (text)."""
    git_bin = shutil.which("git")
    if git_bin is None:
        msg = "git binary not found on PATH"
        raise GitError(msg)
    if not (repo / ".git").exists():
        msg = f"{repo} is not a git repository"
        raise GitError(msg)
    try:
        result = subprocess.run(
            [git_bin, *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        msg = f"git {args[0]} failed: {type(e).__name__}: {e}"
        raise GitError(msg) from e
    if check and result.returncode != 0:
        msg = (
            f"git {args[0]} exited {result.returncode}: "
            f"{result.stderr.strip()[:300]}"
        )
        raise GitError(msg)
    return result.stdout


def list_tags(repo: Path) -> list[str]:
    """Return all tag names, sorted."""
    out = _git(repo, "tag", "--list")
    return sorted(t for t in out.splitlines() if t)


def has_tag(repo: Path, tag: str) -> bool:
    return tag in list_tags(repo)


def create_annotated_tag(repo: Path, tag: str, message: str) -> None:
    _git(repo, "tag", "-a", tag, "-m", message)


def list_branches(repo: Path) -> list[str]:
    out = _git(repo, "branch", "--list", "--format=%(refname:short)")
    return sorted(b.strip() for b in out.splitlines() if b.strip())


def has_branch(repo: Path, branch: str) -> bool:
    return branch in list_branches(repo)


def create_branch_from_head(repo: Path, branch: str) -> None:
    """Create ``branch`` at HEAD without checking it out."""
    _git(repo, "branch", branch)


def is_dirty(repo: Path) -> bool:
    """Return True if working tree or index has uncommitted changes."""
    out = _git(repo, "status", "--porcelain")
    return bool(out.strip())


def current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def current_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def add_paths(repo: Path, *paths: str) -> None:
    """Stage one or more paths."""
    _git(repo, "add", "--", *paths)


def commit_staged(repo: Path, message: str) -> None:
    """Commit currently-staged changes (no-op if nothing staged)."""
    _git(repo, "commit", "--quiet", "-m", message)
