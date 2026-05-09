"""Shared README banner constants used by ``lockdown`` and ``reactivate``.

POLYLENS external (Kimi P2): the open/close marker strings and the
README candidate filenames were defined twice — once in lockdown.py
and once in reactivate.py. Single source of truth here so a marker
rename can't drift out of sync.
"""

from __future__ import annotations

BANNER_MARKER_OPEN = "<!-- sunset-it:freeze-banner -->"
BANNER_MARKER_CLOSE = "<!-- /sunset-it:freeze-banner -->"
README_CANDIDATES: tuple[str, ...] = ("README.md", "Readme.md", "readme.md")
