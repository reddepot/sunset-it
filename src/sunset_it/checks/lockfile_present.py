"""Check: a lockfile (uv.lock / poetry.lock / requirements.txt / Pipfile.lock) exists.

Why blocker for solo-frozen: a frozen project without a lockfile loses
its rebuild path within months — transitive dependencies move. This is
the single most-cited cause of "won't rebuild" in the closure
literature (8/8 voices in the run consolidated on this point).
"""

from __future__ import annotations

import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_CANDIDATES = (
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    "requirements-lock.txt",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    found: list[str] = []
    for candidate in _CANDIDATES:
        if (repo / candidate).is_file():
            found.append(candidate)
    duration_ms = (time.monotonic() - t0) * 1000.0

    if found:
        return CheckResult(
            name="lockfile_present",
            severity=config.severity,
            passed=True,
            message=f"Lockfile present: {', '.join(sorted(found))}",
            details={"lockfiles": sorted(found)},
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="lockfile_present",
        severity=config.severity,
        passed=False,
        message=(
            "No lockfile found (uv.lock / poetry.lock / requirements.txt / "
            "Pipfile.lock / package-lock.json / Cargo.lock / Gemfile.lock). "
            "Generate one before freeze: `uv lock` or `poetry lock` or "
            "`pip-compile --generate-hashes requirements.in`."
        ),
        details={"candidates_checked": list(_CANDIDATES)},
        duration_ms=duration_ms,
    )
