"""Profile YAML schema — what each predefined profile declares.

Profiles are user-overridable YAML files describing which checks run
for a given closure mode (solo-frozen, solo-eol, team-maintenance,
oss-archive). The Pydantic model below validates loaded YAML at
runtime so a typo or missing severity surfaces immediately.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sunset_it.models.check import Severity


class ProfileCheckConfig(BaseModel):
    """Per-check configuration inside a profile."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity = "warning"
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class WatchPolicyConfig(BaseModel):
    """Wake-policy thresholds for the ``watch`` phase."""

    model_config = ConfigDict(extra="forbid")

    schedule: str = "weekly"  # weekly | monthly | daily
    cve_threshold_cvss: float = 7.0
    dep_eol_window_days: int = 90
    image_drift_max_days: int = 180
    model_deprecation_window_days: int = 90
    prompt_regression_max_pct: float = 5.0
    emit_issues: bool = True


class TemplatesConfig(BaseModel):
    """Templates emitted by the ``knowledge`` phase."""

    model_config = ConfigDict(extra="forbid")

    emit: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    """Closure profile declaring checks, templates, and wake policy."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    extends: str | None = None
    checks: dict[str, ProfileCheckConfig] = Field(default_factory=dict)
    templates: TemplatesConfig = Field(default_factory=TemplatesConfig)
    watch: WatchPolicyConfig = Field(default_factory=WatchPolicyConfig)
