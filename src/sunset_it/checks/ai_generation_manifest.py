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


# Spec attack v0.1.1 (Codex P2): the previous version accepted ANY non-
# empty file with the right name, so a one-line ``# TODO`` passed the
# check — pure test theatre. We now require the file to mention at
# least one of these section keywords, matching the keys we ship in
# the Jinja2 template.
_REQUIRED_KEYWORDS = (
    "Models used",
    "models used",
    "Non-regenerable decisions",
    "Load-bearing prompts",
    "Known AI debt",
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    for candidate in _PATH_CANDIDATES:
        target = repo / candidate
        if not target.is_file():
            continue
        if target.stat().st_size == 0:
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matched = [kw for kw in _REQUIRED_KEYWORDS if kw in content]
        duration_ms = (time.monotonic() - t0) * 1000.0
        if matched:
            return CheckResult(
                name="ai_generation_manifest",
                severity=config.severity,
                passed=True,
                message=(
                    f"AI manifest found: {candidate} — sections: "
                    f"{', '.join(matched[:3])}"
                ),
                details={
                    "path": candidate,
                    "size_bytes": target.stat().st_size,
                    "matched_keywords": matched,
                },
                duration_ms=duration_ms,
            )
        # File exists but is content-empty — still a fail.
        return CheckResult(
            name="ai_generation_manifest",
            severity=config.severity,
            passed=False,
            message=(
                f"AI manifest {candidate} is present but contains none of "
                "the required sections (Models used / Non-regenerable "
                "decisions / Load-bearing prompts / Known AI debt). "
                "Re-run `sunset-it knowledge --overwrite` and fill in the "
                "TODO sections."
            ),
            details={
                "path": candidate,
                "size_bytes": target.stat().st_size,
                "missing_keywords": list(_REQUIRED_KEYWORDS),
            },
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
