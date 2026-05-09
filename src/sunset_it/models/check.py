"""Shared types for individual checks executed inside phases."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["blocker", "warning", "info"]
OverallStatus = Literal["green", "yellow", "red"]


class CheckResult(BaseModel):
    """Output of a single ``Check.run()``.

    Frozen so consumers can rely on the value being stable once
    constructed (the audit phase aggregates many CheckResults into the
    AuditReport — mutation downstream would break determinism).

    Spec attack v0.1.1 (Gemini P2): ``duration_ms`` is excluded from
    serialisation by default because it varies wallclock-to-wallclock
    even on identical inputs, breaking the determinism contract
    advertised in the audit phase docstring. Consumers that want the
    timing data can opt back in with ``model_dump(exclude={})``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    severity: Severity
    passed: bool
    message: str
    details: dict[str, Any] = {}
    duration_ms: float = Field(default=0.0, exclude=True)
