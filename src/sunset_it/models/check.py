"""Shared types for individual checks executed inside phases."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Severity = Literal["blocker", "warning", "info"]
OverallStatus = Literal["green", "yellow", "red"]


class CheckResult(BaseModel):
    """Output of a single ``Check.run()``.

    Frozen so consumers can rely on the value being stable once
    constructed (the audit phase aggregates many CheckResults into the
    AuditReport — mutation downstream would break determinism).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    severity: Severity
    passed: bool
    message: str
    details: dict[str, Any] = {}
    duration_ms: float = 0.0
