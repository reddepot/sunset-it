"""Plugin-style checks discovered automatically.

Each check is a callable that takes (repo, profile_check_config) and
returns a ``CheckResult``. New checks ship as new modules in this
package; the discovery routine in ``registry.py`` finds them via
``pkgutil.iter_modules``.
"""

from sunset_it.checks.registry import CheckCallable, get_check, list_checks

__all__ = ["CheckCallable", "get_check", "list_checks"]
