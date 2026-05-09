"""Phase output schemas — frozen Pydantic v2 models.

Each ``*Report`` is the canonical JSON output of one CLI phase.
``schema_version`` is a Literal[N] so a future schema bump is
detectable by static schema-comparison and any consumer can branch on
the version.

Determinism: timestamps are explicit (constructed by the phase, not
by Pydantic defaults), all ``list[...]`` fields are sorted at phase
boundaries before model construction, no PRNG without seed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sunset_it.models.check import CheckResult, OverallStatus


class AuditSummary(BaseModel):
    """Aggregate counts for an AuditReport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int
    passed: int
    failed_blocker: int
    failed_warning: int
    failed_info: int
    overall_status: OverallStatus


class AuditReport(BaseModel):
    """Read-only audit phase output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    checks: list[CheckResult]
    summary: AuditSummary

    def exit_code(self) -> int:
        """Map summary to a process exit code (0/1/2)."""
        if self.summary.failed_blocker > 0:
            return 2
        if self.summary.failed_warning > 0:
            return 1
        return 0


class KnowledgeReport(BaseModel):
    """Output of the ``knowledge`` phase: which templates were emitted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    emit_dir: Path
    profile_name: str
    files_written: list[Path] = Field(default_factory=list)
    files_skipped_existing: list[Path] = Field(default_factory=list)
    files_failed: list[str] = Field(default_factory=list)


class LockdownReport(BaseModel):
    """Output of the ``lockdown`` phase: tag, branch, lockfile, banner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    tag_created: str | None = None
    branch_created: str | None = None
    lockfile_path: Path | None = None
    readme_banner_added: bool = False
    actions_taken: list[str] = Field(default_factory=list)
    actions_skipped: list[str] = Field(default_factory=list)


class HardeningReport(BaseModel):
    """Output of the ``hardening`` phase: scaffolds for extended DoD.

    The hardening phase runs the audit, then proposes (or applies, if
    ``apply=True``) fixes for blockers that have a deterministic
    template — typically the same files the ``knowledge`` phase
    produces, but also CI workflow, .gitignore, .pre-commit-config,
    and a starter pyproject.toml on green-field repos.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    apply: bool
    actions_planned: list[str] = Field(default_factory=list)
    actions_applied: list[str] = Field(default_factory=list)
    actions_skipped: list[str] = Field(default_factory=list)


class WatchAlert(BaseModel):
    """One wake-policy alert."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "cve",
        "dependency_eol",
        "python_eol",
        "model_deprecation",
        "image_drift",
        "prompt_regression",
    ]
    severity: Literal["blocker", "warning", "info"]
    subject: str
    threshold: str
    detected_at: datetime
    source: str
    reason: str
    remediation: str
    stable_id: str  # for issue dedup keying


class WatchReport(BaseModel):
    """Output of the ``watch`` phase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    alerts: list[WatchAlert] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    sources_skipped: list[str] = Field(default_factory=list)


class ReactivateReport(BaseModel):
    """Output of the ``reactivate`` phase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    reason: str
    unfreeze_tag: str | None = None
    branch_used: str
    banner_removed: bool = False
    actions_taken: list[str] = Field(default_factory=list)
    actions_skipped: list[str] = Field(default_factory=list)
