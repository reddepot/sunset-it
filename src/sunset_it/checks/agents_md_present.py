"""Check: an agent-instructions file exists at the repo root.

Looks for any of the cross-tool conventions that emerged in 2024-2026:
AGENTS.md (cross-tool standard), CLAUDE.md (Claude Code), GEMINI.md
(Gemini CLI), .cursorrules / .cursor/rules/*.mdc (Cursor),
.github/copilot-instructions.md (GitHub Copilot).

Why blocker for solo-frozen: an AI-coded project resumed by a future
LLM (or future-you after 6 months) needs durable instructions that
survive context erasure. Without one, every session re-discovers
build commands, conventions, and gotchas from scratch.
"""

from __future__ import annotations

import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_FILE_CANDIDATES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    ".aider.conf.yml",
)
_DIR_CANDIDATES = (
    ".cursor/rules",
    ".github/instructions",
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    found_files: list[str] = []
    for candidate in _FILE_CANDIDATES:
        if (repo / candidate).is_file():
            found_files.append(candidate)
    found_dirs: list[str] = []
    for candidate in _DIR_CANDIDATES:
        target = repo / candidate
        if target.is_dir() and any(target.iterdir()):
            found_dirs.append(candidate)
    duration_ms = (time.monotonic() - t0) * 1000.0

    if found_files or found_dirs:
        details: dict[str, list[str]] = {}
        if found_files:
            details["files"] = sorted(found_files)
        if found_dirs:
            details["directories"] = sorted(found_dirs)
        return CheckResult(
            name="agents_md_present",
            severity=config.severity,
            passed=True,
            message=(
                "Agent-instructions found: "
                + ", ".join(sorted(found_files) + sorted(found_dirs))
            ),
            details={k: list(v) for k, v in details.items()},
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="agents_md_present",
        severity=config.severity,
        passed=False,
        message=(
            "No AGENTS.md / CLAUDE.md / .cursor/rules / "
            ".github/copilot-instructions.md found. Run "
            "`sunset-it knowledge .` to scaffold an AGENTS.md from the "
            "current repo."
        ),
        details={"file_candidates": list(_FILE_CANDIDATES)},
        duration_ms=duration_ms,
    )
