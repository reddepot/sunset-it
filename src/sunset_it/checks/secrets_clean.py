"""Check: no obvious secrets present in tracked files (best-effort regex).

This is a safety-net only. For real audits, run gitleaks or
truffleHog. The regex set covers the same 2026 ecosystem we matched
in POLYBUILD's secret redaction (AKIA / ghp_ / gho_ / ghs_ /
github_pat_ / AIza / hf_ / sk_live_ / sk-) so a forgotten test
fixture or accidental commit triggers the check before lockdown.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from sunset_it.models.check import CheckResult
from sunset_it.models.profile import ProfileCheckConfig

_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bghs_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
)
_TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".env", ".sh", ".md", ".txt", ".cfg", ".ini",
    ".rs", ".go", ".rb", ".java", ".kt", ".cs", ".html", ".css",
}
_IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    "htmlcov", "target",
}
_MAX_BYTES_PER_FILE = 200_000


def _iter_text_files(repo: Path) -> list[Path]:
    out: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in path.relative_to(repo).parts):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        out.append(path)
    return sorted(out)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    hits: list[dict[str, str | int]] = []
    for path in _iter_text_files(repo):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[
                :_MAX_BYTES_PER_FILE
            ]
        except OSError:
            continue
        for pattern in _PATTERNS:
            match = pattern.search(content)
            if match is not None:
                hits.append(
                    {
                        "path": str(path.relative_to(repo)),
                        "pattern": pattern.pattern,
                        "preview": match.group(0)[:24] + "…",
                    }
                )
                break  # one hit per file is enough to flag it
    duration_ms = (time.monotonic() - t0) * 1000.0

    if not hits:
        return CheckResult(
            name="secrets_clean",
            severity=config.severity,
            passed=True,
            message="No obvious secrets matched in tracked text files.",
            details={
                "patterns_checked": len(_PATTERNS),
                "files_scanned": len(_iter_text_files(repo)),
            },
            duration_ms=duration_ms,
        )
    return CheckResult(
        name="secrets_clean",
        severity=config.severity,
        passed=False,
        message=(
            f"Possible secret(s) detected in {len(hits)} file(s). "
            "Rotate and remove from git history (consider git-filter-repo) "
            "before freeze. Run gitleaks for a thorough audit."
        ),
        details={"hits": hits[:20]},
        duration_ms=duration_ms,
    )
