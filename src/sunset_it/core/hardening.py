"""``hardening`` phase: scaffold the Definition-of-Done items the audit
flagged as missing.

Hardening is bookended by audits: it runs ``audit`` first to know
which checks fail; for each known-fixable failure, it either prints
the planned action (``apply=False``, the default) or writes the
template (``apply=True``).

Idempotence: every action is a *create-if-absent* operation. Running
twice produces the same result as running once.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sunset_it._version import __version__
from sunset_it.core.audit import audit
from sunset_it.core.knowledge import knowledge
from sunset_it.models.profile import Profile
from sunset_it.models.reports import HardeningReport
from sunset_it.profiles.loader import load_profile

logger = structlog.get_logger()


# (audit_check_name → (target relpath, jinja2 template name))
_FIXABLE_BY_CHECK: dict[str, tuple[Path, str]] = {
    "agents_md_present": (Path("AGENTS.md"), "AGENTS.md"),
    "runbook_present": (Path("docs/RUNBOOK.md"), "RUNBOOK.md"),
    "ai_generation_manifest": (
        Path("AI_GENERATION_MANIFEST.md"),
        "AI_GENERATION_MANIFEST.md",
    ),
    "readme_freeze_banner": (Path("docs/SUNSET_NOTICE.md"), "SUNSET_NOTICE.md"),
    "adr_dir_present": (Path("docs/adr/ADR-0001-freeze-decision.md"), "ADR.md"),
}


def _build_jinja_env() -> Environment:
    package_dir = resources.files("sunset_it.templates")
    return Environment(
        loader=FileSystemLoader([str(package_dir)]),
        autoescape=select_autoescape(disabled_extensions=("md", "j2", "txt", "yml", "yaml")),
        keep_trailing_newline=True,
    )


def _drift_check(target: Path, rendered: str) -> str | None:
    """Return a drift label if existing content differs from the template.

    POLYLENS v0.2.1 (Kimi+Qwen P2): hardening previously skipped silently
    when a target existed, hiding the case where the user (or another
    tool) edited the file out-of-band. We don't overwrite — but we do
    surface the drift so the operator knows about it.
    """
    try:
        current = target.read_text(encoding="utf-8")
    except OSError:
        return None
    return None if current == rendered else f"drift: {target.name} differs from sunset-it template"


def _scaffold_gitignore(repo: Path, env: Environment, project_name: str) -> tuple[str, str | None]:
    target = repo / ".gitignore"
    template = env.get_template(".gitignore.j2")
    rendered = template.render(project_name=project_name)
    if target.exists():
        return "skipped: .gitignore already exists", _drift_check(target, rendered)
    target.write_text(rendered, encoding="utf-8")
    return "wrote: .gitignore", None


def _scaffold_workflow(repo: Path, env: Environment, profile_name: str) -> tuple[str, str | None]:
    target = repo / ".github" / "workflows" / "sunset.yml"
    template = env.get_template("sunset_workflow.yml.j2")
    rendered = template.render(
        profile_name=profile_name,
        sunset_it_version=__version__,
    )
    if target.exists():
        return (
            "skipped: .github/workflows/sunset.yml already exists",
            _drift_check(target, rendered),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    return "wrote: .github/workflows/sunset.yml", None


def hardening(
    repo: Path,
    profile_name: str = "solo-frozen",
    profile: Profile | None = None,
    apply: bool = False,
    profile_overrides_dir: Path | None = None,
) -> HardeningReport:
    """Scaffold the freeze-readiness artifacts.

    With ``apply=False`` (default), only print the planned actions —
    no filesystem mutation. With ``apply=True``, write the templates
    that fill in the audit's blocker-failures.
    """
    repo = repo.resolve()
    if profile is None:
        profile = load_profile(profile_name, profile_overrides_dir)
    timestamp = datetime.now(UTC)
    actions_planned: list[str] = []
    actions_applied: list[str] = []
    actions_skipped: list[str] = []

    # Step 1 — run the audit so we know what's missing.
    audit_report = audit(
        repo,
        profile_name=profile.name,
        profile_overrides_dir=profile_overrides_dir,
        profile=profile,
    )

    # Step 2 — for each fixable failed check, plan the scaffolding.
    fixable_failures: list[str] = []
    for check in audit_report.checks:
        if check.passed:
            continue
        if check.name in _FIXABLE_BY_CHECK:
            fixable_failures.append(check.name)

    for check_name in fixable_failures:
        target, _template_name = _FIXABLE_BY_CHECK[check_name]
        if (repo / target).exists():
            actions_skipped.append(f"target_exists: {target}")
            continue
        actions_planned.append(f"scaffold {target} (fixes {check_name})")

    # Always-on scaffolds (gitignore + sunset.yml) — useful even if
    # the audit didn't surface them as failures (the audit doesn't
    # check for them yet).
    if not (repo / ".gitignore").exists():
        actions_planned.append("scaffold .gitignore")
    if not (repo / ".github" / "workflows" / "sunset.yml").exists():
        actions_planned.append("scaffold .github/workflows/sunset.yml")

    # Step 3 — apply if asked.
    if apply and actions_planned:
        env = _build_jinja_env()
        # Scaffold knowledge templates (covers fixable_failures except
        # perhaps the workflow / .gitignore, handled below).
        knowledge_report = knowledge(
            repo,
            profile_name=profile.name,
            profile=profile,
            overwrite=False,
        )
        for path in knowledge_report.files_written:
            actions_applied.append(f"wrote: {path.relative_to(repo)}")
        for path in knowledge_report.files_skipped_existing:
            actions_skipped.append(f"target_exists: {path.relative_to(repo)}")

        gi_action, gi_drift = _scaffold_gitignore(repo, env, repo.name)
        actions_applied.append(gi_action)
        if gi_drift:
            actions_skipped.append(gi_drift)
        wf_action, wf_drift = _scaffold_workflow(repo, env, profile.name)
        actions_applied.append(wf_action)
        if wf_drift:
            actions_skipped.append(wf_drift)

    report = HardeningReport(
        timestamp=timestamp,
        sunset_it_version=__version__,
        repo_path=repo,
        profile_name=profile.name,
        apply=apply,
        actions_planned=sorted(actions_planned),
        actions_applied=sorted(a for a in actions_applied if a),
        actions_skipped=sorted(actions_skipped),
    )
    logger.info(
        "hardening_done",
        # POLYLENS v0.2.2 (Gemini P2): same basename rule as watch.
        repo=repo.name,
        profile=profile.name,
        apply=apply,
        planned=len(actions_planned),
        applied=len(report.actions_applied),
        skipped=len(actions_skipped),
    )
    return report
