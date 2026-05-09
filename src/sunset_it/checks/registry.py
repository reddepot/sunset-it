"""Check discovery and registration.

Each check module under ``sunset_it.checks`` exposes a ``run()``
function with the signature::

    def run(repo: Path, config: ProfileCheckConfig) -> CheckResult: ...

The module's filename (stem) is the check's canonical name. The
registry walks the package on first access and caches the mapping;
extension authors add a check by dropping a new file with a ``run()``
function — no central registration list to edit.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from pathlib import Path

import structlog

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

CheckCallable = Callable[[Path, ProfileCheckConfig], CheckResult]

_logger = structlog.get_logger()

_REGISTRY: dict[str, CheckCallable] | None = None
_INTERNAL_MODULES = {"registry", "__init__"}


def _discover() -> dict[str, CheckCallable]:
    """Walk the ``sunset_it.checks`` package and build the registry."""
    import sunset_it.checks as checks_pkg

    out: dict[str, CheckCallable] = {}
    for mod_info in pkgutil.iter_modules(checks_pkg.__path__):
        name = mod_info.name
        if name in _INTERNAL_MODULES or name.startswith("_"):
            continue
        # POLYLENS v0.2.2 (Kimi P1): a corrupt or import-erroring check
        # module used to crash the entire CLI during discovery. Catch
        # ImportError so a single broken plugin doesn't take everything
        # down — log it and skip.
        try:
            module = importlib.import_module(f"sunset_it.checks.{name}")
        except Exception as e:
            _logger.warning(
                "check_module_import_failed",
                module=name,
                error=str(e)[:200],
                error_type=type(e).__name__,
            )
            continue
        run = getattr(module, "run", None)
        if run is None or not callable(run):
            # Module without a run() callable is ignored. Lets contributors
            # add helper modules without registering them as checks.
            continue
        out[name] = run
    return out


def list_checks() -> list[str]:
    """Return all registered check names, deterministically sorted."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _discover()
    return sorted(_REGISTRY)


def get_check(name: str) -> CheckCallable | None:
    """Look up a check by name. Returns None if unregistered."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _discover()
    return _REGISTRY.get(name)


def reset_registry_for_tests() -> None:
    """Force re-discovery on the next access. Used by unit tests only."""
    global _REGISTRY
    _REGISTRY = None
