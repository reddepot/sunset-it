"""Check: a runbook exists somewhere obvious.

Why blocker for solo-frozen: future-you after 6 months needs to find
"how do I start this thing" without re-reading the source. Google SRE
practice: a runbook with start/debug/restore is the minimum for any
service in non-active development.
"""

from __future__ import annotations

import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_PATH_CANDIDATES = (
    "RUNBOOK.md",
    "RUNBOOK_PRODUCTION.md",
    "RUNBOOK_PROD.md",
    "docs/RUNBOOK.md",
    "docs/RUNBOOK_PRODUCTION.md",
    "docs/RUNBOOK_PROD.md",
    "docs/runbook.md",
    "docs/runbook_production.md",
    "docs/operations.md",
    "docs/ops.md",
    "OPERATIONS.md",
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    for candidate in _PATH_CANDIDATES:
        target = repo / candidate
        if target.is_file() and target.stat().st_size > 0:
            duration_ms = (time.monotonic() - t0) * 1000.0
            return CheckResult(
                name="runbook_present",
                severity=config.severity,
                passed=True,
                message=f"Runbook found: {candidate}",
                details={"path": candidate, "size_bytes": target.stat().st_size},
                duration_ms=duration_ms,
            )
    duration_ms = (time.monotonic() - t0) * 1000.0
    return CheckResult(
        name="runbook_present",
        severity=config.severity,
        passed=False,
        message=(
            "No runbook found. Run `sunset-it knowledge .` to scaffold "
            "a 1-page runbook with start/debug/restore commands."
        ),
        details={"candidates_checked": list(_PATH_CANDIDATES)},
        duration_ms=duration_ms,
    )
