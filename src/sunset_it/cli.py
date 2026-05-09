"""Typer entry point for ``sunset-it``.

Three sub-commands are wired in v0.1: ``audit``, ``knowledge``,
``lockdown``. ``hardening``, ``watch``, and ``reactivate`` are
planned for v0.2 — they print a helpful "not yet implemented"
message rather than crashing.

Output format selection mirrors the JSON-friendly tools (``gh``,
``trivy``): ``--output json`` writes structured data to stdout,
``--output human`` writes prose. Logs always go to stderr via
structlog so stdout stays parsable.
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
from sunset_it.core.knowledge import knowledge
from sunset_it.core.lockdown import lockdown


class OutputFormat(StrEnum):
    json = "json"
    markdown = "markdown"
    human = "human"


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


# Stubs for v0.2 — print a helpful message rather than crash.
@app.command("hardening")
def hardening_cmd() -> None:
    """[v0.2] Apply extended Definition of Done."""
    typer.echo(
        "sunset-it hardening: not yet implemented (planned for v0.2). "
        "Use `sunset-it audit` to see what would be flagged.",
        err=True,
    )
    raise typer.Exit(code=3)


@app.command("watch")
def watch_cmd() -> None:
    """[v0.2] Wake-policy CI: CVE / EOL / model deprecation."""
    typer.echo(
        "sunset-it watch: not yet implemented (planned for v0.2). "
        "Configure Dependabot / OSV-Scanner Action in the meantime.",
        err=True,
    )
    raise typer.Exit(code=3)


@app.command("reactivate")
def reactivate_cmd() -> None:
    """[v0.2] Controlled exit from freeze."""
    typer.echo(
        "sunset-it reactivate: not yet implemented (planned for v0.2). "
        "For now: `git checkout maintenance && git tag unfrozen-$(date +%Y-%m-%d)`.",
        err=True,
    )
    raise typer.Exit(code=3)


if __name__ == "__main__":  # pragma: no cover
    app()
