"""``knowledge`` phase: emit the documentation set required for resume.

Renders Jinja2 templates from ``sunset_it.templates`` into the target
directory. Default behaviour: do not overwrite existing files (let
the maintainer keep their hand-written prose). Pass ``overwrite=True``
to force.

Determinism: rendering is pure given (template, context). No
wallclock outside the explicit ``generated_at`` variable. Files are
emitted in deterministic name-sorted order.
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sunset_it._version import __version__
from sunset_it.models.profile import Profile
from sunset_it.models.reports import KnowledgeReport
from sunset_it.profiles.loader import load_profile

logger = structlog.get_logger()

_TARGET_BY_TEMPLATE = {
    "AGENTS.md": Path("AGENTS.md"),
    "RUNBOOK.md": Path("docs/RUNBOOK.md"),
    "AI_GENERATION_MANIFEST.md": Path("AI_GENERATION_MANIFEST.md"),
    "SUNSET_NOTICE.md": Path("docs/SUNSET_NOTICE.md"),
    "LESSONS.md": Path("docs/LESSONS.md"),
    "ADR.md": Path("docs/adr/ADR-0001-freeze-decision.md"),
}


def _build_jinja_env(template_overrides_dir: Path | None) -> Environment:
    """Build the Jinja2 env. Override dir wins over package resources."""
    search_paths: list[str] = []
    if template_overrides_dir is not None:
        search_paths.append(str(template_overrides_dir))
    package_dir = resources.files("sunset_it.templates")
    # ``resources.files`` returns a Traversable; for Jinja2's
    # FileSystemLoader we need a real filesystem path. The wheel layout
    # we ship is on disk, so ``str()`` is correct here.
    search_paths.append(str(package_dir))
    return Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape(disabled_extensions=("md", "j2", "txt")),
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _detect_project_meta(repo: Path) -> dict[str, Any]:
    """Best-effort metadata extraction from pyproject.toml."""
    out: dict[str, Any] = {
        "project_name": repo.name,
        "project_module": repo.name.replace("-", "_"),
    }
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return out
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return out
    project = data.get("project", {}) or {}
    name = project.get("name")
    if isinstance(name, str):
        out["project_name"] = name
        out["project_module"] = name.replace("-", "_")
    description = project.get("description")
    if isinstance(description, str):
        out["project_overview"] = description
    requires = project.get("requires-python")
    if isinstance(requires, str):
        out["python_min"] = requires
    return out


def _render_one(
    env: Environment,
    template_basename: str,
    target_relpath: Path,
    repo: Path,
    context: dict[str, Any],
    overwrite: bool,
) -> tuple[Path, str] | None:
    """Render one template; return (path, action) where action is
    'written' | 'skipped_existing' | 'failed'.
    """
    target_path = repo / target_relpath
    if target_path.is_file() and not overwrite:
        return target_path, "skipped_existing"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    template = env.get_template(f"{template_basename}.j2")
    rendered = template.render(**context)
    target_path.write_text(rendered, encoding="utf-8")
    return target_path, "written"


def knowledge(
    repo: Path,
    emit_dir: Path | None = None,
    profile_name: str = "solo-frozen",
    profile: Profile | None = None,
    overwrite: bool = False,
    template_overrides_dir: Path | None = None,
    extra_context: dict[str, Any] | None = None,
) -> KnowledgeReport:
    """Emit the documentation set declared by the profile.

    Args:
        repo: project root.
        emit_dir: alternative emit root (defaults to ``repo`` itself
            so files land at their canonical paths).
        profile_name: profile to load.
        profile: pre-loaded Profile (test injection).
        overwrite: force re-write of existing files.
        template_overrides_dir: directory of custom Jinja2 templates.
        extra_context: extra variables exposed to the templates.

    Returns:
        ``KnowledgeReport`` listing files written, skipped, failed.
    """
    repo = repo.resolve()
    target_root = (emit_dir or repo).resolve()
    if profile is None:
        profile = load_profile(profile_name)

    env = _build_jinja_env(template_overrides_dir)

    timestamp = datetime.now(UTC)
    base_context: dict[str, Any] = {
        "generated_at": timestamp.strftime("%Y-%m-%d"),
        "freeze_status": "frozen",
        "freeze_date": timestamp.strftime("%Y-%m-%d"),
        "profile_name": profile.name,
        "sunset_it_version": __version__,
    }
    base_context.update(_detect_project_meta(repo))
    if extra_context:
        base_context.update(extra_context)

    written: list[Path] = []
    skipped: list[Path] = []
    failed: list[str] = []

    for template_name in sorted(profile.templates.emit):
        target_rel = _TARGET_BY_TEMPLATE.get(template_name)
        if target_rel is None:
            failed.append(f"{template_name}: no target mapping")
            continue
        target_relpath_in_emit = target_rel
        if emit_dir is not None:
            # When emit_dir is set, write everything under it as a flat
            # tree so the user can preview the bundle before merging.
            target_relpath_in_emit = target_rel
        try:
            result = _render_one(
                env,
                template_name,
                target_relpath_in_emit,
                target_root,
                base_context,
                overwrite,
            )
        except Exception as e:
            logger.warning(
                "knowledge_template_failed",
                template=template_name,
                error=type(e).__name__,
                msg=str(e)[:300],
            )
            failed.append(f"{template_name}: {type(e).__name__}: {str(e)[:200]}")
            continue
        if result is None:
            continue
        path, action = result
        if action == "written":
            written.append(path)
        elif action == "skipped_existing":
            skipped.append(path)
        else:
            failed.append(f"{template_name}: {action}")

    report = KnowledgeReport(
        timestamp=timestamp,
        sunset_it_version=__version__,
        repo_path=repo,
        emit_dir=target_root,
        profile_name=profile.name,
        files_written=sorted(written),
        files_skipped_existing=sorted(skipped),
        files_failed=sorted(failed),
    )
    logger.info(
        "knowledge_done",
        repo=str(repo),
        emit_dir=str(target_root),
        written=len(written),
        skipped=len(skipped),
        failed=len(failed),
    )
    return report
