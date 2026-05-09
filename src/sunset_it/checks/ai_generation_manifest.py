"""Check: an AI generation manifest exists with model+date+prompt info.

Specific to AI-coded projects (the gap none of the formal frameworks
covers). The manifest documents which models produced the code, when,
and which prompts are load-bearing — required to anticipate model
deprecation and prompt rot.
"""

from __future__ import annotations

import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_PATH_CANDIDATES = (
    "AI_GENERATION_MANIFEST.md",
    "AI-GENERATION-MANIFEST.md",
    "docs/AI_GENERATION_MANIFEST.md",
    "docs/ai_generation_manifest.md",
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    for candidate in _PATH_CANDIDATES:
        target = repo / candidate
        if target.is_file() and target.stat().st_size > 0:
            duration_ms = (time.monotonic() - t0) * 1000.0
            return CheckResult(
                name="ai_generation_manifest",
                severity=config.severity,
                passed=True,
                message=f"AI manifest found: {candidate}",
                details={"path": candidate, "size_bytes": target.stat().st_size},
                duration_ms=duration_ms,
            )
    duration_ms = (time.monotonic() - t0) * 1000.0
    return CheckResult(
        name="ai_generation_manifest",
        severity=config.severity,
        passed=False,
        message=(
            "No AI_GENERATION_MANIFEST.md found. This file documents "
            "which LLMs produced the code, when, and which prompts are "
            "load-bearing — needed to anticipate model deprecation. "
            "Run `sunset-it knowledge .` to scaffold one."
        ),
        details={"candidates_checked": list(_PATH_CANDIDATES)},
        duration_ms=duration_ms,
    )
