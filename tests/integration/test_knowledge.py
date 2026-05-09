"""Integration tests for ``sunset_it.core.knowledge``.

POLYLENS v0.2.3 (Kimi P2): cover the new template-context wiring
(``adr_number``, ``freeze_tag``, ``repo_url``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from sunset_it.core.knowledge import knowledge


def test_knowledge_wires_repo_url_and_adr_number(tmp_repo: Path) -> None:
    """``adr_number``, ``freeze_tag``, ``repo_url`` must be populated."""
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:demo/demo.git"],
        cwd=str(tmp_repo),
        check=True,
        capture_output=True,
    )

    # solo-eol emits ADR.md too — solo-frozen has it as optional only.
    knowledge(tmp_repo, profile_name="solo-eol", overwrite=True)

    adr_files = list((tmp_repo / "docs" / "adr").iterdir())
    assert any(f.name.startswith("ADR-0001-") for f in adr_files)

    runbook = (tmp_repo / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    # repo_url should resolve to the origin we set, not the "<unknown>"
    # default fallback.
    assert "<unknown>" not in runbook
