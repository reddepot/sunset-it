"""Check: a git tag matching ``freeze-*`` or ``v*-frozen`` exists.

A tag is the canonical "exact state at the moment of freeze". Without
it, a CVE patch six months later can't easily diff against the
known-good state.

Implementation: shells out to ``git tag --list`` rather than re-
implementing tag parsing — git is a hard dep here anyway.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_TAG_PATTERNS = (
    re.compile(r"^freeze-\d{4}-\d{2}-\d{2}.*$"),
    re.compile(r"^freeze-.*$"),
    re.compile(r"^v.*-frozen$"),
    re.compile(r"^sunset-.*$"),
)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    git_bin = shutil.which("git")
    if git_bin is None:
        duration_ms = (time.monotonic() - t0) * 1000.0
        return CheckResult(
            name="git_freeze_tag",
            severity=config.severity,
            passed=False,
            message="git binary not found on PATH; cannot inspect tags.",
            details={},
            duration_ms=duration_ms,
        )
    if not (repo / ".git").exists():
        duration_ms = (time.monotonic() - t0) * 1000.0
        return CheckResult(
            name="git_freeze_tag",
            severity=config.severity,
            passed=False,
            message=f"{repo} is not a git repository (.git not found).",
            details={},
            duration_ms=duration_ms,
        )
    try:
        result = subprocess.run(
            [git_bin, "tag", "--list"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        duration_ms = (time.monotonic() - t0) * 1000.0
        return CheckResult(
            name="git_freeze_tag",
            severity=config.severity,
            passed=False,
            message=f"git tag listing failed: {type(e).__name__}",
            details={},
            duration_ms=duration_ms,
        )
    duration_ms = (time.monotonic() - t0) * 1000.0
    if result.returncode != 0:
        return CheckResult(
            name="git_freeze_tag",
            severity=config.severity,
            passed=False,
            message=(
                f"git tag --list exited {result.returncode}: "
                f"{result.stderr.strip()[:200]}"
            ),
            details={},
            duration_ms=duration_ms,
        )
    tags = [t for t in result.stdout.splitlines() if t]
    matched = sorted(
        tag for tag in tags if any(pat.match(tag) for pat in _TAG_PATTERNS)
    )
    if matched:
        return CheckResult(
            name="git_freeze_tag",
            severity=config.severity,
            passed=True,
            message=f"Freeze-style tag(s) present: {', '.join(matched)}",
            details={"matched_tags": matched, "total_tags": len(tags)},
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="git_freeze_tag",
        severity=config.severity,
        passed=False,
        message=(
            "No freeze-* / sunset-* / v*-frozen tag found. Run "
            "`sunset-it lockdown .` to create one."
        ),
        details={"total_tags": len(tags)},
        duration_ms=duration_ms,
    )
