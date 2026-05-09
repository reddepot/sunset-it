# ADR-0002 — Checks: plug-in module architecture

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: solo maintainer

## Context

The audit phase needs to run an arbitrary set of checks. Two extremes
exist:

- **Central registry**: a single `checks.py` with a `CHECKS = {...}`
  dict the maintainer edits when adding a check. Easy at small scale,
  becomes a merge magnet and a barrier to extension.
- **Plug-in protocol**: each check is a Python module exposing a
  `run(repo, config) -> CheckResult` function. The registry is built
  by walking the package via `pkgutil.iter_modules`.

POLYBUILD's experience with 16+ unmaintained routing profiles
(flagged 4× in POLYLENS audits) is a reminder that "easy to add"
must be matched by "easy to remove", which a central registry
discourages.

## Decision

Adopt the plug-in protocol. Each check is a module under
`sunset_it.checks/` whose `run()` function matches `CheckCallable`.
Discovery is automatic via `pkgutil.iter_modules`; the file's stem
is the check's name; profiles reference checks by that name.

## Consequences

### Positive

- Adding a check is a single new file, no central edit.
- Removing a check is a delete; profiles that reference an absent
  check surface as info-level failures (not crashes).
- Third-party extensions can drop checks via namespace package or
  custom `--checks-dir` (foreseen for v0.2).

### Negative / trade-offs

- Discovery is implicit — readers must know the convention to find
  all checks. Mitigated by `sunset-it audit --list-checks` (planned).
- Type-checking can't see plug-ins by name (registry is `str` keyed).
  Mitigated by structuring CheckCallable as a `Callable[..., CheckResult]`.

## Alternatives considered

- **Central registry dict** — rejected: lower extensibility, higher
  merge friction, easier to leave dead entries.
- **Entry points (setuptools)** — rejected for v0.1: works for
  third-party packages but adds a build-time wiring step that's
  unnecessary at this scale. Reconsider in v0.3 if external plugins
  become a use case.
