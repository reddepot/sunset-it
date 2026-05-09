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
    # Self-attack P2: bare ``sk-`` is too broad — it matched legitimate
    # identifiers like ``sk-storage-class-v2-eu-west-3``. Restrict to the
    # 2026 OpenAI / Anthropic key prefixes.
    re.compile(r"\bsk-(proj|svcacct|admin|ant-api03|None|live|test)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
)
_TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".env", ".sh", ".md", ".txt", ".cfg", ".ini",
    ".rs", ".go", ".rb", ".java", ".kt", ".cs", ".html", ".css",
}
# Spec attack v0.1.1 (Codex P2): files like ``.env`` at repo root have
# ``Path(".env").suffix == ""`` so the suffix-only filter ignored them.
# Match by basename for the env-shaped exceptions.
_TEXT_BASENAMES = {".env", ".env.local", ".env.sample", ".envrc", "Makefile", "Dockerfile"}
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
        # Match either by suffix or by basename (covers .env / Dockerfile /
        # Makefile that have empty suffixes — Codex P2).
        if (
            path.suffix.lower() not in _TEXT_SUFFIXES
            and path.name not in _TEXT_BASENAMES
        ):
            continue
        out.append(path)
    return sorted(out)


def run(repo: Path, config: ProfileCheckConfig) -> CheckResult:
    t0 = time.monotonic()
    hits: list[dict[str, str | int]] = []
    for path in _iter_text_files(repo):
        # Spec attack v0.1.1 (Gemini P2): the previous version called
        # ``read_text()`` (which loads the entire file in memory) then
        # sliced. A 5 GB SQL dump or untracked log file would OOM the
        # whole audit before the check could even decide to skip it.
        # Streamed read caps physical RAM use at ``_MAX_BYTES_PER_FILE``.
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                content = fh.read(_MAX_BYTES_PER_FILE)
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
