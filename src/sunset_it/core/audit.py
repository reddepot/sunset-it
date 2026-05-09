"""``audit`` phase: read-only state of the repository against a profile.

The phase iterates the profile's enabled checks in deterministic
(name-sorted) order, calls each ``Check.run(repo, config)``, collects
``CheckResult`` objects, and aggregates them into an ``AuditReport``.

Determinism guarantees:
    * checks are iterated by sorted name;
    * the report's ``timestamp`` is the only source of wallclock data;
    * no PRNG, no environment-dependent ordering.

Side-effects: NONE. The audit phase reads the repo and the local
filesystem; it never writes to the repo. ``cache_dir`` (when
provided) is the only writable location, and is reserved for
sub-process tools (pip-audit, etc.) that come in later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from sunset_it._version import __version__
from sunset_it.checks import get_check, list_checks
from sunset_it.models.check import CheckResult, OverallStatus
from sunset_it.models.profile import Profile
from sunset_it.models.reports import AuditReport, AuditSummary
from sunset_it.profiles.loader import load_profile

logger = structlog.get_logger()


def _build_summary(checks: list[CheckResult]) -> AuditSummary:
    failed_blocker = sum(
        1 for c in checks if not c.passed and c.severity == "blocker"
    )
    failed_warning = sum(
        1 for c in checks if not c.passed and c.severity == "warning"
    )
    failed_info = sum(
        1 for c in checks if not c.passed and c.severity == "info"
    )
    passed = sum(1 for c in checks if c.passed)
    overall: OverallStatus
    if failed_blocker > 0:
        overall = "red"
    elif failed_warning > 0:
        overall = "yellow"
    else:
        overall = "green"
    return AuditSummary(
        total=len(checks),
        passed=passed,
        failed_blocker=failed_blocker,
        failed_warning=failed_warning,
        failed_info=failed_info,
        overall_status=overall,
    )


def _run_one_check(
    name: str,
    repo: Path,
    profile: Profile,
) -> CheckResult | None:
    """Resolve and execute one named check; return None if not registered."""
    config = profile.checks.get(name)
    if config is None or not config.enabled:
        return None
    callable_ = get_check(name)
    if callable_ is None:
        # Profile references a check that does not exist on disk.
        # Spec attack v0.1.1 (Gemini P0): the previous version hard-coded
        # ``severity="info"`` here, which made the audit silently green
        # when a profile listed an unknown check at blocker severity.
        # Propagate the profile-declared severity instead so a blocker
        # check that was deleted-by-typo still fails the audit.
        return CheckResult(
            name=name,
            severity=config.severity,
            passed=False,
            message=(
                f"Profile {profile.name!r} references unknown check {name!r}. "
                "Either add a checks/ module with run() or remove the entry."
            ),
            details={"available_checks": sorted(list_checks())},
            duration_ms=0.0,
        )
    try:
        return callable_(repo, config)
    except Exception as e:
        logger.warning(
            "check_runtime_error",
            check=name,
            error=type(e).__name__,
            message=str(e)[:300],
        )
        return CheckResult(
            name=name,
            severity=config.severity,
            passed=False,
            message=f"Check raised {type(e).__name__}: {str(e)[:200]}",
            details={"exception_type": type(e).__name__},
            duration_ms=0.0,
        )


def audit(
    repo: Path,
    profile_name: str = "solo-frozen",
    profile_overrides_dir: Path | None = None,
    profile: Profile | None = None,
) -> AuditReport:
    """Run all enabled checks of ``profile_name`` against ``repo``.

    Args:
        repo: project root.
        profile_name: profile to load (ignored if ``profile`` is given).
        profile_overrides_dir: directory with custom YAML profiles.
        profile: pre-loaded Profile (test injection).

    Returns:
        ``AuditReport`` with deterministic check ordering.
    """
    repo = repo.resolve()
    if profile is None:
        profile = load_profile(profile_name, profile_overrides_dir)
    logger.info(
        "audit_start",
        repo=repo.name,
        profile=profile.name,
        checks=sorted(profile.checks),
    )
    results: list[CheckResult] = []
    for check_name in sorted(profile.checks):
        result = _run_one_check(check_name, repo, profile)
        if result is not None:
            results.append(result)

    summary = _build_summary(results)
    report = AuditReport(
        timestamp=datetime.now(UTC),
        sunset_it_version=__version__,
        repo_path=repo,
        profile_name=profile.name,
        checks=results,
        summary=summary,
    )
    logger.info(
        "audit_done",
        repo=repo.name,
        profile=profile.name,
        overall_status=summary.overall_status,
        passed=summary.passed,
        failed_blocker=summary.failed_blocker,
        failed_warning=summary.failed_warning,
    )
    return report


def audit_to_json(report: AuditReport) -> str:
    """Serialise an audit report to canonical sorted-keys JSON."""
    return report.model_dump_json(indent=2)


def audit_to_human(report: AuditReport) -> str:
    """Render an audit report in human-readable Markdown."""
    lines: list[str] = [
        f"# sunset-it audit — {report.profile_name}",
        "",
        # POLYLENS external (Gemini P2): basename, not absolute path —
        # this Markdown is often pasted into PR descriptions / issues.
        f"- Repo: `{report.repo_path.name}`",
        f"- Timestamp: `{report.timestamp.isoformat()}`",
        f"- sunset-it version: `{report.sunset_it_version}`",
        f"- Overall status: **{report.summary.overall_status.upper()}**",
        f"- Total: {report.summary.total} | "
        f"Passed: {report.summary.passed} | "
        f"Blockers: {report.summary.failed_blocker} | "
        f"Warnings: {report.summary.failed_warning}",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        icon = "✅" if check.passed else _icon_for_severity(check.severity)
        lines.append(f"### {icon} `{check.name}` ({check.severity})")
        lines.append("")
        lines.append(check.message)
        lines.append("")
        if check.details:
            lines.append("Details:")
            for k, v in sorted(check.details.items()):
                lines.append(f"- `{k}`: `{_short_repr(v)}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _icon_for_severity(severity: str) -> str:
    return {"blocker": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity, "·")


def _short_repr(v: Any, limit: int = 200) -> str:
    text = repr(v)
    if len(text) > limit:
        return text[:limit] + "…"
    return text
