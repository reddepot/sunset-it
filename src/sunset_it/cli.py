"""Typer entry point for ``sunset-it``.

Six sub-commands wired (v0.2): ``audit``, ``knowledge``,
``lockdown``, ``hardening``, ``watch``, ``reactivate``.

Output format selection mirrors the JSON-friendly tools (``gh``,
``trivy``): ``--output json`` writes structured data to stdout,
``--output human`` writes prose. Logs always go to stderr via
structlog so stdout stays parsable. ``watch`` adds a
``gh-summary`` format (Markdown table for ``$GITHUB_STEP_SUMMARY``).
"""

from __future__ import annotations

import json
import logging
import sys
from enum import StrEnum
from pathlib import Path

import structlog
import typer

from sunset_it._version import __version__
from sunset_it.core.audit import audit, audit_to_human, audit_to_json
from sunset_it.core.hardening import hardening
from sunset_it.core.knowledge import knowledge
from sunset_it.core.lockdown import lockdown
from sunset_it.core.reactivate import reactivate
from sunset_it.core.watch import watch, watch_to_gh_summary


class OutputFormat(StrEnum):
    json = "json"
    markdown = "markdown"
    human = "human"
    gh_summary = "gh-summary"


app = typer.Typer(
    name="sunset-it",
    help=(
        "Solo dev project freeze/maintenance/sunset toolkit "
        "(focus AI-coded codebases)."
    ),
    add_completion=True,
    no_args_is_help=True,
)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(stream=sys.stderr, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"sunset-it {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Debug logging."),
) -> None:
    """sunset-it root command."""
    _configure_logging(verbose)


@app.command("audit")
def audit_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    profile_overrides_dir: Path | None = typer.Option(
        None, "--profile-overrides-dir", help="Directory of custom YAML profiles."
    ),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
    fail_on: str = typer.Option(
        "blocker",
        "--fail-on",
        help="never | warning | blocker — what triggers exit code != 0.",
    ),
) -> None:
    """Audit a repo against a profile (read-only)."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = audit(repo, profile_name=profile, profile_overrides_dir=profile_overrides_dir)

    if output == OutputFormat.json:
        sys.stdout.write(audit_to_json(report) + "\n")
    elif output == OutputFormat.markdown:
        sys.stdout.write(audit_to_human(report))
    else:
        sys.stdout.write(audit_to_human(report))

    exit_code = report.exit_code()
    if fail_on == "never":
        exit_code = 0
    elif fail_on == "warning" and report.summary.failed_warning > 0:
        exit_code = max(exit_code, 1)
    raise typer.Exit(code=exit_code)


@app.command("knowledge")
def knowledge_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    emit: Path | None = typer.Option(
        None,
        "--emit",
        help="Optional alternative output dir (defaults to writing to canonical paths inside repo).",
    ),
    overwrite: bool = typer.Option(False, "--overwrite"),
    template_overrides_dir: Path | None = typer.Option(
        None, "--templates-dir", help="Custom Jinja2 templates directory."
    ),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
) -> None:
    """Emit AGENTS.md, RUNBOOK, AI_GENERATION_MANIFEST, SUNSET_NOTICE, LESSONS, ADR."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = knowledge(
        repo,
        emit_dir=emit,
        profile_name=profile,
        overwrite=overwrite,
        template_overrides_dir=template_overrides_dir,
    )

    if output == OutputFormat.json:
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        sys.stdout.write(_render_knowledge_human(report))

    raise typer.Exit(code=0 if not report.files_failed else 2)


def _render_knowledge_human(report: object) -> str:
    data = json.loads(report.model_dump_json())  # type: ignore[attr-defined]
    lines = [
        f"# sunset-it knowledge — {data['profile_name']}",
        "",
        f"- Repo: `{data['repo_path']}`",
        f"- Emit dir: `{data['emit_dir']}`",
        f"- Timestamp: `{data['timestamp']}`",
        "",
        f"Files written: {len(data['files_written'])}",
    ]
    for path in data["files_written"]:
        lines.append(f"  - {path}")
    if data["files_skipped_existing"]:
        lines.append("")
        lines.append(f"Files skipped (existing): {len(data['files_skipped_existing'])}")
        for path in data["files_skipped_existing"]:
            lines.append(f"  - {path}")
    if data["files_failed"]:
        lines.append("")
        lines.append(f"Files failed: {len(data['files_failed'])}")
        for failure in data["files_failed"]:
            lines.append(f"  - {failure}")
    return "\n".join(lines).rstrip() + "\n"


@app.command("lockdown")
def lockdown_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    tag_name: str | None = typer.Option(None, "--tag", help="Override tag name (default: freeze-YYYY-MM-DD)."),
    branch_name: str = typer.Option("maintenance", "--branch"),
    no_banner: bool = typer.Option(False, "--no-banner", help="Skip README banner."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty"),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
) -> None:
    """Tag the freeze, create the maintenance branch, add a README banner."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = lockdown(
        repo,
        tag_name=tag_name,
        branch_name=branch_name,
        profile_name=profile,
        update_readme_banner=not no_banner,
        allow_dirty=allow_dirty,
    )

    if output == OutputFormat.json:
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        sys.stdout.write(_render_lockdown_human(report))

    # Spec attack v0.1.1 (Codex P1): the previous logic returned exit
    # code 1 on a re-run where everything was already done — the tag
    # already exists, the branch already exists, the banner is already
    # present. That's idempotent success, not failure. Treat any
    # ``*_already_exists`` / ``*_already_present`` / ``readme_not_found``
    # skip as benign; only ``*_failed`` and ``working_tree_dirty`` are
    # actual problems.
    benign_prefixes = (
        "tag_already_exists",
        "branch_already_exists",
        "readme_banner_already_present",
        "readme_not_found",
    )
    actual_failures = [
        s for s in report.actions_skipped
        if not any(s.startswith(p) for p in benign_prefixes)
    ]
    # v0.1.2: invalid_tag_name / invalid_branch_name are misuse (exit 3),
    # not runtime failures (exit 2).
    if any(s.startswith(("invalid_tag_name", "invalid_branch_name")) for s in actual_failures):
        raise typer.Exit(code=3)
    raise typer.Exit(code=2 if actual_failures else 0)


def _render_lockdown_human(report: object) -> str:
    data = json.loads(report.model_dump_json())  # type: ignore[attr-defined]
    lines = [
        f"# sunset-it lockdown — {data['profile_name']}",
        "",
        f"- Repo: `{data['repo_path']}`",
        f"- Timestamp: `{data['timestamp']}`",
        f"- Tag created: `{data['tag_created'] or '(none)'}`",
        f"- Branch created: `{data['branch_created'] or '(none)'}`",
        f"- README banner added: `{data['readme_banner_added']}`",
        "",
        "Actions taken:",
    ]
    for action in data["actions_taken"] or ["(none)"]:
        lines.append(f"  - {action}")
    lines.append("")
    lines.append("Actions skipped:")
    for skip in data["actions_skipped"] or ["(none)"]:
        lines.append(f"  - {skip}")
    return "\n".join(lines).rstrip() + "\n"


@app.command("hardening")
def hardening_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    apply: bool = typer.Option(False, "--apply", help="Write the planned files (default: dry-run)."),
    profile_overrides_dir: Path | None = typer.Option(
        None, "--profile-overrides-dir", help="Directory of custom YAML profiles."
    ),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
) -> None:
    """Scaffold the artefacts the audit flagged as missing."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = hardening(
        repo,
        profile_name=profile,
        apply=apply,
        profile_overrides_dir=profile_overrides_dir,
    )

    if output == OutputFormat.json:
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        sys.stdout.write(_render_hardening_human(report))

    raise typer.Exit(code=0)


def _render_hardening_human(report: object) -> str:
    data = json.loads(report.model_dump_json())  # type: ignore[attr-defined]
    lines = [
        f"# sunset-it hardening — {data['profile_name']}",
        "",
        f"- Repo: `{data['repo_path']}`",
        f"- Apply: `{data['apply']}`",
        f"- Timestamp: `{data['timestamp']}`",
        "",
        "Actions planned:",
    ]
    for action in data["actions_planned"] or ["(none)"]:
        lines.append(f"  - {action}")
    if data["actions_applied"]:
        lines.append("")
        lines.append("Actions applied:")
        for action in data["actions_applied"]:
            lines.append(f"  - {action}")
    if data["actions_skipped"]:
        lines.append("")
        lines.append("Actions skipped:")
        for skip in data["actions_skipped"]:
            lines.append(f"  - {skip}")
    return "\n".join(lines).rstrip() + "\n"


@app.command("watch")
def watch_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    profile_overrides_dir: Path | None = typer.Option(
        None, "--profile-overrides-dir", help="Directory of custom YAML profiles."
    ),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
    fail_on_alert: bool = typer.Option(
        False,
        "--fail-on-alert",
        help="Exit non-zero when any blocker alert is raised.",
    ),
) -> None:
    """Run the wake-policy scan and emit alerts."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = watch(
        repo,
        profile_name=profile,
        profile_overrides_dir=profile_overrides_dir,
    )

    if output == OutputFormat.json:
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    elif output == OutputFormat.gh_summary:
        sys.stdout.write(watch_to_gh_summary(report))
    else:
        sys.stdout.write(_render_watch_human(report))

    if fail_on_alert and any(a.severity == "blocker" for a in report.alerts):
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


def _render_watch_human(report: object) -> str:
    data = json.loads(report.model_dump_json())  # type: ignore[attr-defined]
    lines = [
        f"# sunset-it watch — {data['profile_name']}",
        "",
        f"- Repo: `{data['repo_path']}`",
        f"- Timestamp: `{data['timestamp']}`",
        f"- Alerts: {len(data['alerts'])}",
        "",
    ]
    if not data["alerts"]:
        lines.append("No alerts raised.")
    else:
        for alert in data["alerts"]:
            lines.append(
                f"- [{alert['severity']}] {alert['kind']} `{alert['subject']}`: "
                f"{alert['reason']}"
            )
            lines.append(f"    remediation: {alert['remediation']}")
    if data["sources_used"]:
        lines.append("")
        lines.append(f"Sources used: {', '.join(data['sources_used'])}")
    if data["sources_skipped"]:
        lines.append(f"Sources skipped: {', '.join(data['sources_skipped'])}")
    return "\n".join(lines).rstrip() + "\n"


@app.command("reactivate")
def reactivate_cmd(
    repo: Path = typer.Argument(Path(), help="Path to repo root."),
    reason: str = typer.Option(..., "--reason", "-r", help="Why are we reactivating?"),
    branch_from: str = typer.Option("maintenance", "--from-branch"),
    unfreeze_tag: str | None = typer.Option(
        None, "--tag", help="Override unfreeze tag name (default: unfrozen-YYYY-MM-DD)."
    ),
    profile: str = typer.Option("solo-frozen", "--profile", "-p"),
    profile_overrides_dir: Path | None = typer.Option(
        None, "--profile-overrides-dir", help="Directory of custom YAML profiles."
    ),
    allow_dirty: bool = typer.Option(False, "--allow-dirty"),
    skip_branch_check: bool = typer.Option(
        False,
        "--skip-branch-check",
        help="Allow reactivate even if the maintenance branch is missing.",
    ),
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", "-o"),
) -> None:
    """Exit a freeze — strip banner, commit, tag the unfreeze."""
    if not repo.exists():
        typer.echo(f"error: repo path not found: {repo}", err=True)
        raise typer.Exit(code=3)

    report = reactivate(
        repo,
        reason=reason,
        branch_from=branch_from,
        unfreeze_tag_name=unfreeze_tag,
        profile_name=profile,
        profile_overrides_dir=profile_overrides_dir,
        allow_dirty=allow_dirty,
        require_maintenance_branch=not skip_branch_check,
    )

    if output == OutputFormat.json:
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        sys.stdout.write(_render_reactivate_human(report))

    benign_prefixes = (
        "unfreeze_tag_already_exists",
        "banner_absent",
        "readme_not_found",
        "maintenance_branch_present",
        "maintenance_branch_missing",
    )
    actual_failures = [
        s for s in report.actions_skipped
        if not any(s.startswith(p) for p in benign_prefixes)
    ]
    if any(s.startswith("invalid_unfreeze_tag_name") for s in actual_failures):
        raise typer.Exit(code=3)
    raise typer.Exit(code=2 if actual_failures else 0)


def _render_reactivate_human(report: object) -> str:
    data = json.loads(report.model_dump_json())  # type: ignore[attr-defined]
    lines = [
        f"# sunset-it reactivate — {data['profile_name']}",
        "",
        f"- Repo: `{data['repo_path']}`",
        f"- Timestamp: `{data['timestamp']}`",
        f"- Reason: {data['reason']}",
        f"- Unfreeze tag: `{data['unfreeze_tag'] or '(none)'}`",
        f"- Branch used: `{data['branch_used']}`",
        f"- Banner removed: `{data['banner_removed']}`",
        "",
        "Actions taken:",
    ]
    for action in data["actions_taken"] or ["(none)"]:
        lines.append(f"  - {action}")
    lines.append("")
    lines.append("Actions skipped:")
    for skip in data["actions_skipped"] or ["(none)"]:
        lines.append(f"  - {skip}")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":  # pragma: no cover
    app()
