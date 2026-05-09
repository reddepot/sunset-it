"""Pydantic v2 schemas for sunset-it reports and configuration.

Public types:
    Severity, OverallStatus — closed enums shared across reports.
    CheckResult — output of a single Check.
    AuditReport, KnowledgeReport, LockdownReport — phase outputs.
    Profile, ProfileCheckConfig — YAML configuration loaded from profiles/.
"""

from sunset_it.models.check import CheckResult, OverallStatus, Severity
from sunset_it.models.profile import Profile, ProfileCheckConfig
from sunset_it.models.reports import (
    AuditReport,
    AuditSummary,
    KnowledgeReport,
    LockdownReport,
)

__all__ = [
    "AuditReport",
    "AuditSummary",
    "CheckResult",
    "KnowledgeReport",
    "LockdownReport",
    "OverallStatus",
    "Profile",
    "ProfileCheckConfig",
    "Severity",
]
