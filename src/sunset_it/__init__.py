"""sunset-it — Solo dev project freeze/maintenance/sunset toolkit.

Public API entry points:
    from sunset_it import (
        audit, knowledge, lockdown,
        hardening, watch, reactivate,
    )
    from sunset_it.models import (
        AuditReport, KnowledgeReport, LockdownReport,
        HardeningReport, WatchReport, ReactivateReport,
    )

POLYLENS external (Kimi P2): the v0.2 phases (hardening / watch /
reactivate) are now exposed at the top level so programmatic
consumers don't have to import from sub-modules whose path may
change in future versions.
"""

from sunset_it._version import __version__
from sunset_it.core.audit import audit
from sunset_it.core.hardening import hardening
from sunset_it.core.knowledge import knowledge
from sunset_it.core.lockdown import lockdown
from sunset_it.core.reactivate import reactivate
from sunset_it.core.watch import watch

__all__ = [
    "__version__",
    "audit",
    "hardening",
    "knowledge",
    "lockdown",
    "reactivate",
    "watch",
]
