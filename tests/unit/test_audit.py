"""Audit phase orchestrator tests."""

from __future__ import annotations

from pathlib import Path

from sunset_it.core.audit import audit, audit_to_human, audit_to_json


def test_audit_on_empty_repo_returns_red(tmp_path: Path) -> None:
    report = audit(tmp_path, profile_name="solo-frozen")
    assert report.summary.overall_status == "red"
    assert report.summary.failed_blocker > 0
    assert report.exit_code() == 2


def test_audit_human_render_includes_status(tmp_path: Path) -> None:
    report = audit(tmp_path, profile_name="solo-frozen")
    rendered = audit_to_human(report)
    assert "RED" in rendered or "GREEN" in rendered or "YELLOW" in rendered


def test_audit_json_is_parsable(tmp_path: Path) -> None:
    import json as _json

    report = audit(tmp_path, profile_name="solo-frozen")
    data = _json.loads(audit_to_json(report))
    assert data["profile_name"] == "solo-frozen"
    assert data["schema_version"] == 1
    assert "summary" in data


def test_audit_is_deterministic(tmp_path: Path) -> None:
    a = audit(tmp_path, profile_name="solo-frozen")
    b = audit(tmp_path, profile_name="solo-frozen")
    # Timestamps will differ but the check structure should be identical.
    assert [c.name for c in a.checks] == [c.name for c in b.checks]
    assert [c.passed for c in a.checks] == [c.passed for c in b.checks]
