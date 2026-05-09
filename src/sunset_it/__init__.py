"""sunset-it — Solo dev project freeze/maintenance/sunset toolkit.

Public API entry points:
    from sunset_it import audit, knowledge, lockdown
    from sunset_it.models import AuditReport, KnowledgeReport, LockdownReport
"""

from sunset_it._version import __version__
from sunset_it.core.audit import audit
from sunset_it.core.knowledge import knowledge
from sunset_it.core.lockdown import lockdown

__all__ = [
    "__version__",
    "audit",
    "knowledge",
    "lockdown",
]
