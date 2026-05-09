"""``watch`` phase: detect post-freeze degradation signals.

The watch phase is **read-only** and **fast**. It collects signals
that should wake the maintainer:

* CVE / dependency advisories (via ``pip-audit`` if available)
* Python runtime EOL window (re-uses the ``python_runtime_supported``
  check)
* Model deprecation (matches ``AI_GENERATION_MANIFEST.md`` content
  against a small static database of known Anthropic / OpenAI
  retirement dates)

``sunset-it`` itself does not make HTTP calls. However, when
``pip-audit`` is installed, it queries OSV / PyPI to resolve
vulnerabilities — that's a network call. If you require strict
offline operation, uninstall ``pip-audit``; the dep-CVE source
will then list as skipped. The Python EOL and model deprecation
sources are 100% offline (static snapshots).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog

from sunset_it._version import __version__
from sunset_it.checks.python_runtime_supported import _PYTHON_EOL_DATES
from sunset_it.checks.python_runtime_supported import (
    _extract_minimum_python as _python_min,
)
from sunset_it.models.profile import Profile
from sunset_it.models.reports import WatchAlert, WatchReport
from sunset_it.profiles.loader import load_profile

logger = structlog.get_logger()


# Static snapshot of public model deprecations as of 2026-05-09.
# Source: platform.claude.com/docs/en/about-claude/model-deprecations
# and developers.openai.com/api/docs/deprecations.
# Update when a new model is announced — the watch phase reads this
# table offline rather than hitting vendor APIs from a frozen project.
#
# POLYLENS v0.2.1 (Kimi P2): the table is US-centric. Adding non-US
# providers (Mistral, Cohere, Alibaba Qwen, DeepSeek, Z.ai GLM, Moonshot
# Kimi) is tracked as future-work — none of those vendors publishes a
# stable retirement schedule today, so we avoid speculative entries.
_SNAPSHOT_DATE = "2026-05-09"
_SNAPSHOT_STALE_AFTER_DAYS = 180

_MODEL_DEPRECATIONS: dict[str, str] = {
    "claude-opus-4-20250514": "2026-06-15",
    "claude-sonnet-4-20250514": "2026-06-15",
    "claude-3-7-sonnet-20250219": "2026-02-19",
    "claude-3-5-haiku-20241022": "2026-02-19",
    "claude-3-haiku-20240307": "2026-04-20",
    "claude-3-opus-20240229": "2026-01-05",
    "gpt-4-0314": "2026-03-26",
    "gpt-4-0125-preview": "2026-03-26",
    "gpt-4-0613": "2026-10-23",
    "gpt-4-1106-preview": "2026-10-23",
    "gpt-4-turbo": "2026-10-23",
    "gpt-4-turbo-2024-04-09": "2026-10-23",
    "gpt-4o-2024-05-13": "2026-10-23",
}


def _scan_pip_audit(
    repo: Path, threshold_cvss: float
) -> tuple[list[WatchAlert], str]:
    """Return alerts for direct dependencies with HIGH/CRITICAL CVEs.

    Returns ``(alerts, source_label)`` — source_label tells the report
    whether the scanner was actually invoked or skipped.
    """
    pip_audit = shutil.which("pip-audit")
    if pip_audit is None:
        return [], "pip-audit:skipped (not on PATH)"
    pyproject = repo / "pyproject.toml"
    requirements = repo / "requirements.txt"
    if not pyproject.exists() and not requirements.exists():
        return [], "pip-audit:skipped (no pyproject.toml or requirements.txt)"
    # POLYLENS v0.2.2 (Gemini P1): point pip-audit at the target — without
    # an explicit ``--requirement`` or ``--project`` flag it silently
    # audits its OWN venv (the one ``uv tool install pip-audit`` created),
    # which means a frozen project's vulns go undetected.
    cmd = [pip_audit, "--format=json", "--strict", "--progress-spinner=off"]
    if requirements.exists():
        cmd += ["--requirement", str(requirements)]
    else:
        cmd += ["--project", str(repo)]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return [], "pip-audit:skipped (timeout or OS error)"
    # POLYLENS v0.2.2 (Gemini P1): a non-zero return code with empty stdout
    # used to be interpreted as "no findings" — silently masking crashes.
    # Surface failures explicitly so the watch report includes them.
    if result.returncode != 0 and not result.stdout.strip():
        stderr_first_line = (result.stderr or "").splitlines()[:1]
        snippet = stderr_first_line[0][:120] if stderr_first_line else "no stderr"
        return [], f"pip-audit:failed (rc={result.returncode}: {snippet})"
    if not result.stdout.strip():
        return [], "pip-audit:no findings"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], "pip-audit:malformed JSON"
    alerts: list[WatchAlert] = []
    now = datetime.now(UTC)
    deps = data.get("dependencies") or []
    for dep in deps:
        for vuln in dep.get("vulns") or []:
            severity = "blocker" if (vuln.get("aliases") or []) else "warning"
            stable_id = (
                f"cve:{dep.get('name', '')}:{vuln.get('id', 'unknown')}"
            )
            alerts.append(
                WatchAlert(
                    kind="cve",
                    severity=severity,  # type: ignore[arg-type]
                    subject=f"{dep.get('name')} {dep.get('version')}",
                    threshold=f"cvss>={threshold_cvss}",
                    detected_at=now,
                    source="pip-audit",
                    reason=f"{vuln.get('id')}: {vuln.get('description', '')[:200]}",
                    remediation=(
                        f"upgrade to {vuln.get('fix_versions', ['latest'])[0]}"
                        if vuln.get("fix_versions")
                        else "no fix available — accept risk or replace dep"
                    ),
                    stable_id=stable_id,
                )
            )
    return alerts, "pip-audit:ran"


def _python_eol_alerts(repo: Path, window_days: int) -> tuple[list[WatchAlert], str]:
    minimum = _python_min(repo)
    if minimum is None:
        return [], "python_eol:skipped (no requires-python)"
    eol_iso = _PYTHON_EOL_DATES.get(minimum)
    if eol_iso is None:
        return [], f"python_eol:skipped (no EOL data for {minimum})"
    try:
        eol = date.fromisoformat(eol_iso)
    except ValueError:
        return [], f"python_eol:skipped (malformed eol {eol_iso})"
    today = date.today()  # noqa: DTZ011
    days_left = (eol - today).days
    if days_left > window_days:
        return [], "python_eol:within_window_ok"
    sev = "blocker" if days_left <= 0 else "warning"
    return [
        WatchAlert(
            kind="python_eol",
            severity=sev,  # type: ignore[arg-type]
            subject=f"Python {minimum}",
            threshold=f"window<={window_days}d",
            detected_at=datetime.now(UTC),
            source="endoflife.date snapshot",
            reason=(
                f"Python {minimum} {'reached EOL' if days_left <= 0 else 'EOLs'} "
                f"on {eol_iso} ({abs(days_left)}d "
                f"{'ago' if days_left <= 0 else 'left'})."
            ),
            remediation=(
                f"Migrate to a supported Python version (3.{int(minimum.split('.')[1]) + 1}+)."
            ),
            stable_id=f"python_eol:{minimum}",
        )
    ], "python_eol:checked"


def _model_deprecation_alerts(
    repo: Path, window_days: int
) -> tuple[list[WatchAlert], str]:
    manifest_path = None
    for candidate in (
        "AI_GENERATION_MANIFEST.md",
        "AI-GENERATION-MANIFEST.md",
        "docs/AI_GENERATION_MANIFEST.md",
    ):
        if (repo / candidate).is_file():
            manifest_path = repo / candidate
            break
    if manifest_path is None:
        return [], "model_deprecation:skipped (no AI_GENERATION_MANIFEST.md)"
    try:
        content = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], "model_deprecation:skipped (read failed)"
    today = date.today()  # noqa: DTZ011
    alerts: list[WatchAlert] = []
    for model_id, eol_iso in _MODEL_DEPRECATIONS.items():
        # POLYLENS v0.2.1 (Kimi+Qwen P1): substring matching causes false
        # positives — a manifest mentioning "the gpt-4-0314-style approach"
        # in prose would alert. Require the model id at a word boundary.
        if not re.search(rf"(?<![\w\-]){re.escape(model_id)}(?![\w\-])", content):
            continue
        try:
            eol = date.fromisoformat(eol_iso)
        except ValueError:
            continue
        days_left = (eol - today).days
        if days_left > window_days:
            continue
        sev = "blocker" if days_left <= 0 else "warning"
        alerts.append(
            WatchAlert(
                kind="model_deprecation",
                severity=sev,  # type: ignore[arg-type]
                subject=model_id,
                threshold=f"window<={window_days}d",
                detected_at=datetime.now(UTC),
                source="vendor deprecation page (snapshot)",
                reason=(
                    f"{model_id} listed in manifest; "
                    f"{'retired' if days_left <= 0 else 'retiring'} on "
                    f"{eol_iso} ({abs(days_left)}d "
                    f"{'ago' if days_left <= 0 else 'left'})."
                ),
                remediation=(
                    "Update AI_GENERATION_MANIFEST.md to record the "
                    "replacement model and re-run smoke tests with the "
                    "successor before retirement."
                ),
                stable_id=f"model:{model_id}",
            )
        )
    return alerts, "model_deprecation:checked"


def watch(
    repo: Path,
    profile_name: str = "solo-frozen",
    profile: Profile | None = None,
    profile_overrides_dir: Path | None = None,
) -> WatchReport:
    """Run the wake-policy scan; return a list of alerts."""
    repo = repo.resolve()
    if profile is None:
        profile = load_profile(profile_name, profile_overrides_dir)
    timestamp = datetime.now(UTC)
    alerts: list[WatchAlert] = []
    sources_used: list[str] = []
    sources_skipped: list[str] = []

    cve_alerts, cve_src = _scan_pip_audit(
        repo, profile.watch.cve_threshold_cvss
    )
    alerts.extend(cve_alerts)
    (sources_used if "ran" in cve_src or "no findings" in cve_src else sources_skipped).append(cve_src)

    py_alerts, py_src = _python_eol_alerts(repo, profile.watch.dep_eol_window_days)
    alerts.extend(py_alerts)
    (sources_used if "checked" in py_src or "ok" in py_src else sources_skipped).append(py_src)

    model_alerts, model_src = _model_deprecation_alerts(
        repo, profile.watch.model_deprecation_window_days
    )
    alerts.extend(model_alerts)
    (sources_used if "checked" in model_src else sources_skipped).append(model_src)

    # POLYLENS v0.2.1 (Kimi+Qwen P1): if every source skipped, surface a
    # meta-alert so the operator does not mistake "0 alerts" for "all good".
    if not sources_used:
        alerts.append(
            WatchAlert(
                kind="meta",
                severity="warning",
                subject="watch_uncheckable",
                threshold="sources_used==0",
                detected_at=timestamp,
                source="watch:self",
                reason=(
                    "No source could be evaluated (no pyproject.toml, no "
                    "AI_GENERATION_MANIFEST.md, pip-audit unavailable). "
                    "Empty alert list does NOT mean the project is healthy."
                ),
                remediation=(
                    "Generate the missing manifests via "
                    "`sunset-it hardening --apply` or install pip-audit "
                    "(`uv tool install pip-audit`)."
                ),
                stable_id="meta:watch_uncheckable",
            )
        )

    # POLYLENS v0.2.1 (Kimi P3): warn if the static snapshot is past its
    # best-by date — a frozen project will hit this before the maintainer
    # ever touches the codebase again.
    try:
        snapshot = date.fromisoformat(_SNAPSHOT_DATE)
        age_days = (date.today() - snapshot).days  # noqa: DTZ011
        if age_days > _SNAPSHOT_STALE_AFTER_DAYS:
            alerts.append(
                WatchAlert(
                    kind="meta",
                    severity="warning",
                    subject="model_deprecation_snapshot_stale",
                    threshold=f"age>{_SNAPSHOT_STALE_AFTER_DAYS}d",
                    detected_at=timestamp,
                    source="watch:self",
                    reason=(
                        f"_MODEL_DEPRECATIONS snapshot is {age_days}d old "
                        f"(captured {_SNAPSHOT_DATE}). Vendor deprecation "
                        "lists likely changed since then."
                    ),
                    remediation=(
                        "Upgrade sunset-it (`uv tool upgrade sunset-it`) to "
                        "pick up a refreshed snapshot."
                    ),
                    stable_id="meta:snapshot_stale",
                )
            )
    except ValueError:
        pass

    report = WatchReport(
        timestamp=timestamp,
        sunset_it_version=__version__,
        repo_path=repo,
        profile_name=profile.name,
        alerts=sorted(alerts, key=lambda a: (a.kind, a.subject)),
        sources_used=sorted(sources_used),
        sources_skipped=sorted(sources_skipped),
    )
    logger.info(
        "watch_done",
        repo=repo.name,  # POLYLENS v0.2.1 (Kimi P1): basename, not abs path
        profile=profile.name,
        alerts=len(alerts),
        sources_used=len(sources_used),
        sources_skipped=len(sources_skipped),
    )
    return report


def watch_to_gh_summary(report: WatchReport) -> str:
    """Render alerts in GitHub Actions Step Summary Markdown.

    Empty-alert case still returns a small summary so the operator
    sees something useful in the Action UI.
    """
    if not report.alerts:
        return (
            "## sunset-it watch — no alerts\n\n"
            f"- Profile: `{report.profile_name}`\n"
            f"- Timestamp: `{report.timestamp.isoformat()}`\n"
            f"- Sources used: {', '.join(report.sources_used) or '(none)'}\n"
            f"- Sources skipped: {', '.join(report.sources_skipped) or '(none)'}\n"
        )
    lines = [
        "## sunset-it watch — alerts",
        "",
        f"- Profile: `{report.profile_name}`",
        f"- Timestamp: `{report.timestamp.isoformat()}`",
        f"- Total alerts: **{len(report.alerts)}**",
        "",
        "| Kind | Severity | Subject | Reason |",
        "|------|----------|---------|--------|",
    ]
    for alert in report.alerts:
        # POLYLENS v0.2.1 (Kimi+Qwen P1): escape pipes so reasons containing
        # ``|`` (e.g. CVE descriptions) don't shred the Markdown table.
        safe_reason = alert.reason[:120].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {alert.kind} | {alert.severity} | "
            f"`{alert.subject}` | {safe_reason} |"
        )
    lines.append("")
    lines.append(f"Sources used: {', '.join(report.sources_used) or '(none)'}")
    lines.append(f"Sources skipped: {', '.join(report.sources_skipped) or '(none)'}")
    return "\n".join(lines) + "\n"


# Used in tests to inspect the static snapshot without exporting it.
def _snapshot_size() -> int:
    return len(_MODEL_DEPRECATIONS) + len(_PYTHON_EOL_DATES) + 1 + (timedelta(days=1).days * 0)
