"""Check: declared Python runtime is not in EOL window.

Reads ``requires-python`` from pyproject.toml and ``python_requires``
hints; flags if any is below 3.11 (3.10 EOL October 2026, 3.9 already
EOL).

The window is conservative: if the project is freezing today and the
runtime EOLs in the next ``window_days`` days, the project is at risk
of supply-chain abandonment within the freeze period.
"""

from __future__ import annotations

import re
import time
import tomllib
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

# Last public Python release-cycle anchors at the time of writing. The
# table is intentionally hard-coded with a "data as of" comment so a
# future maintainer can refresh by reading https://devguide.python.org/versions/
# rather than scrape it at runtime (offline-friendly).
# Data as of 2026-05-09.
_PYTHON_EOL_DATES = {
    "3.9": "2025-10-31",
    "3.10": "2026-10-31",
    "3.11": "2027-10-31",
    "3.12": "2028-10-31",
    "3.13": "2029-10-31",
    "3.14": "2030-10-31",
}

_VERSION_RE = re.compile(r"\b3\.(\d+)\b")


def _extract_minimum_python(repo: Path) -> str | None:
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    requires = (
        data.get("project", {}).get("requires-python")
        or data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
    )
    if not isinstance(requires, str):
        return None
    match = _VERSION_RE.search(requires)
    if match is None:
        return None
    return f"3.{match.group(1)}"


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    from datetime import date

    t0 = time.monotonic()
    minimum = _extract_minimum_python(repo)
    duration_ms = (time.monotonic() - t0) * 1000.0
    if minimum is None:
        return CheckResult(
            name="python_runtime_supported",
            severity="info",
            passed=True,
            message="No requires-python declared; check skipped.",
            details={},
            duration_ms=duration_ms,
        )
    eol_iso = _PYTHON_EOL_DATES.get(minimum)
    if eol_iso is None:
        return CheckResult(
            name="python_runtime_supported",
            severity="info",
            passed=True,
            message=f"requires-python = {minimum}; no EOL data shipped.",
            details={"requires_python": minimum},
            duration_ms=duration_ms,
        )
    # Spec attack v0.1.1 (Gemini P3 + Codex P2): parse via ``date`` for
    # robust comparison and respect the profile-configurable
    # ``window_days`` (default 180j) so a runtime that EOLs *during* the
    # freeze window is flagged before it actually expires.
    try:
        eol_date = date.fromisoformat(eol_iso)
    except ValueError:
        return CheckResult(
            name="python_runtime_supported",
            severity="info",
            passed=True,
            message=f"EOL data malformed for {minimum}: {eol_iso}",
            details={"requires_python": minimum, "eol_iso_raw": eol_iso},
            duration_ms=duration_ms,
        )
    today = date.today()  # noqa: DTZ011 — date-only comparison, no tz needed
    days_until_eol = (eol_date - today).days
    window_days: int = int(config.params.get("window_days", 180))
    if days_until_eol <= 0:
        return CheckResult(
            name="python_runtime_supported",
            severity=config.severity,
            passed=False,
            message=(
                f"requires-python = {minimum}; reached EOL on {eol_iso} "
                f"({-days_until_eol} day(s) ago). Migrate before extending "
                "the freeze."
            ),
            details={
                "requires_python": minimum,
                "eol_date": eol_iso,
                "days_until_eol": days_until_eol,
                "window_days": window_days,
            },
            duration_ms=duration_ms,
        )
    if days_until_eol <= window_days:
        return CheckResult(
            name="python_runtime_supported",
            severity=config.severity,
            passed=False,
            message=(
                f"requires-python = {minimum}; EOL on {eol_iso} in "
                f"{days_until_eol} day(s) (window={window_days}). "
                "Plan migration during the freeze."
            ),
            details={
                "requires_python": minimum,
                "eol_date": eol_iso,
                "days_until_eol": days_until_eol,
                "window_days": window_days,
            },
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="python_runtime_supported",
        severity=config.severity,
        passed=True,
        message=(
            f"requires-python = {minimum}; supported until {eol_iso} "
            f"(in {days_until_eol} days)."
        ),
        details={
            "requires_python": minimum,
            "eol_date": eol_iso,
            "days_until_eol": days_until_eol,
            "window_days": window_days,
        },
        duration_ms=duration_ms,
    )
