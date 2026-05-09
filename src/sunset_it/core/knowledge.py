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

import re
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
    # Spec attack v0.1.1 (Gemini P3): ADR target is now resolved
    # dynamically via ``_next_adr_path`` so re-running on a repo that
    # already has 3 ADRs creates ADR-0004, not a collision on
    # ADR-0001-freeze-decision.md.
    "ADR.md": None,  # resolved at render time
}
_ADR_DIR = Path("docs/adr")
_ADR_FILENAME_RE = re.compile(r"^ADR-(\d+)[-_].*\.md$")


def _build_jinja_env(template_overrides_dir: Path | None) -> Environment:
    """Build the Jinja2 env. Override dir wins over package resources.

    POLYLENS v0.2.2 (Kimi+Qwen P2): user-provided templates run in a
    SandboxedEnvironment to block ``__class__``-walking RCE tricks. The
    package's own templates are still trusted, but the loader doesn't
    know which file came from where, so we sandbox uniformly.
    """
    from jinja2.sandbox import SandboxedEnvironment

    search_paths: list[str] = []
    if template_overrides_dir is not None:
        search_paths.append(str(template_overrides_dir))
    package_dir = resources.files("sunset_it.templates")
    # ``resources.files`` returns a Traversable; for Jinja2's
    # FileSystemLoader we need a real filesystem path. The wheel layout
    # we ship is on disk, so ``str()`` is correct here.
    search_paths.append(str(package_dir))
    return SandboxedEnvironment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape(disabled_extensions=("md", "j2", "txt")),
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _next_adr_path(repo: Path) -> Path:
    """Return ``docs/adr/ADR-<N+1>-freeze-decision.md`` where N is the
    highest existing ADR number found under ``docs/adr/``.

    Falls back to ``ADR-0001-freeze-decision.md`` if the directory is
    empty or absent.
    """
    adr_dir = repo / _ADR_DIR
    next_n = 1
    if adr_dir.is_dir():
        existing = []
        for entry in adr_dir.iterdir():
            if entry.is_file():
                match = _ADR_FILENAME_RE.match(entry.name)
                if match is not None:
                    existing.append(int(match.group(1)))
        if existing:
            next_n = max(existing) + 1
    return _ADR_DIR / f"ADR-{next_n:04d}-freeze-decision.md"


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
    # POLYLENS v0.2.2 (Kimi P2): atomic write — tmp file in the same dir
    # then ``replace``. Avoids leaving truncated files on SIGKILL / power
    # loss between ``open()`` and the final write.
    tmp = target_path.with_suffix(target_path.suffix + ".sunset-tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(target_path)
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
        if template_name == "ADR.md":
            target_rel = _next_adr_path(target_root)
        elif template_name in _TARGET_BY_TEMPLATE:
            mapped = _TARGET_BY_TEMPLATE[template_name]
            if mapped is None:
                failed.append(f"{template_name}: no target mapping")
                continue
            target_rel = mapped
        else:
            failed.append(f"{template_name}: no target mapping")
            continue
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
