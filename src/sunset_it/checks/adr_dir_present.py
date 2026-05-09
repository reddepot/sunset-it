"""Check: at least N ADRs (Architecture Decision Records) under docs/adr/.

Default threshold: 3 ADRs (override via ``params.min_count``).

Why warning for solo-frozen: ADRs capture the *why* an LLM never
writes spontaneously. Without them, future-you (or future-AI) opens
the project and refactors a load-bearing decision because nothing in
the code says "don't touch this".
"""

from __future__ import annotations

import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_DIR_CANDIDATES = (
    "docs/adr",
    "docs/adrs",
    "docs/architecture/decisions",
    "doc/adr",
    "adr",
)


def _count_adr_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(
        1
        for p in directory.iterdir()
        if p.is_file()
        and p.suffix in {".md", ".markdown"}
        and not p.name.startswith(".")
    )


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    min_count: int = int(config.params.get("min_count", 3))

    found_dir: str | None = None
    found_count = 0
    for candidate in _DIR_CANDIDATES:
        target = repo / candidate
        n = _count_adr_files(target)
        if n > 0:
            found_dir = candidate
            found_count = n
            break

    duration_ms = (time.monotonic() - t0) * 1000.0

    if found_dir is None:
        return CheckResult(
            name="adr_dir_present",
            severity=config.severity,
            passed=False,
            message=(
                "No ADR directory found "
                "(expected docs/adr/ with N markdown files). "
                "Run `sunset-it knowledge .` to scaffold the directory "
                "and a starter ADR."
            ),
            details={
                "min_count": min_count,
                "candidates_checked": list(_DIR_CANDIDATES),
            },
            duration_ms=duration_ms,
        )
    if found_count < min_count:
        return CheckResult(
            name="adr_dir_present",
            severity=config.severity,
            passed=False,
            message=(
                f"ADR directory {found_dir} has {found_count} entries; "
                f"profile requires at least {min_count}."
            ),
            details={
                "directory": found_dir,
                "found_count": found_count,
                "min_count": min_count,
            },
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="adr_dir_present",
        severity=config.severity,
        passed=True,
        message=f"ADR directory {found_dir} has {found_count} entries.",
        details={
            "directory": found_dir,
            "found_count": found_count,
            "min_count": min_count,
        },
        duration_ms=duration_ms,
    )
