"""Check: README displays an explicit freeze/maintenance status banner.

Without a banner the project status is ambiguous to anyone who lands
on the repo (including future-you). The check is conservative: it
matches a small dictionary of well-known status keywords near the top
of the README so a normal long-form description is not mistaken for
a banner.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_README_CANDIDATES = (
    "README.md",
    "README.rst",
    "README.txt",
    "Readme.md",
    "readme.md",
)
_BANNER_KEYWORDS = re.compile(
    r"\b(frozen|freeze|sunset|sunsetting|deprecated|archived|"
    r"maintenance[ -]mode|read[ -]?only|in[ -]?stasis|EOL)\b",
    re.IGNORECASE,
)
_HEAD_BYTES = 4096


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    target: Path | None = None
    for candidate in _README_CANDIDATES:
        path = repo / candidate
        if path.is_file():
            target = path
            break
    duration_ms = (time.monotonic() - t0) * 1000.0
    if target is None:
        return CheckResult(
            name="readme_freeze_banner",
            severity=config.severity,
            passed=False,
            message="No README.md/.rst/.txt found at repo root.",
            details={"candidates_checked": list(_README_CANDIDATES)},
            duration_ms=duration_ms,
        )
    head = target.read_text(encoding="utf-8", errors="replace")[:_HEAD_BYTES]
    match = _BANNER_KEYWORDS.search(head)
    if match is not None:
        return CheckResult(
            name="readme_freeze_banner",
            severity=config.severity,
            passed=True,
            message=(
                f"README banner keyword '{match.group(0)}' found "
                f"in first {_HEAD_BYTES} bytes of {target.name}."
            ),
            details={"path": target.name, "keyword": match.group(0)},
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="readme_freeze_banner",
        severity=config.severity,
        passed=False,
        message=(
            "README has no freeze/maintenance/sunset banner. Add a "
            "one-line status near the top so the project state is "
            "unambiguous to readers."
        ),
        details={"path": target.name},
        duration_ms=duration_ms,
    )
