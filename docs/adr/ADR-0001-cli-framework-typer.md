# ADR-0001 — CLI framework: Typer

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: solo maintainer (orchestrator), informed by Codex CLI SQ1 review

## Context

`sunset-it` ships as a CLI installable via `uv tool install` with six
sub-commands (`audit`, `hardening`, `knowledge`, `lockdown`, `watch`,
`reactivate`). It must:

- Expose a clean help screen and shell completion.
- Accept type-annotated arguments without manual coercion.
- Support sub-command nesting if profiles or checks gain their own
  inspection commands later.
- Stay light on transitive dependencies (this is a closure tool, not
  a long-running daemon).

The contenders considered: Typer, Click, Fire, argparse, Cyclopts.

## Decision

Use **Typer ≥ 0.12** as the CLI framework.

## Consequences

### Positive

- Native type hints; the same Pydantic v2 types we use for outputs
  feed straight into the CLI signatures.
- Auto-generated `--help` and shell completion (`typer install`).
- Click-compatible internals → access to a mature ecosystem
  (`testing.CliRunner`, exception handling, autocomplete).
- Trivial subcommand grouping if the API grows.
- Rich tracebacks via Typer's optional Rich integration.

### Negative / trade-offs

- One more runtime dep beyond stdlib (Typer + Click + click-help-colors).
- Slightly slower import than argparse on cold start (~50 ms on M-series).
- Breaking changes in 0.x are possible; we pin to ≥ 0.12 to avoid the
  pre-0.10 callable-signature API.

## Alternatives considered

- **Click** — picked Typer because its Click backend gives us the
  same maturity with type hints first.
- **Fire** — rejected: introspection-based magic surfaces internals
  in the CLI shape; help text quality is uneven; vélocité de release
  has slowed since 2023.
- **argparse** — rejected: stdlib-only is attractive, but writing
  type-safe sub-command trees by hand is busywork that delays the
  freeze story.
- **Cyclopts** — promising (type-first, modern), but smaller user base
  in 2025-2026; we keep it as a migration target if Typer's pace slows.
