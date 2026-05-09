# ADR-0003 — Reports: Pydantic v2, frozen, schema_version Literal

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: solo maintainer, informed by POLYBUILD POLYLENS run #4 fix on
  `ShadowDivergence.schema_version`.

## Context

Each phase outputs a structured report consumed by humans, scripts,
and CI. Three properties matter:

1. The output schema must be **strictly closed** so a malformed
   producer fails fast rather than emitting silent extra fields.
2. The output must be **immutable** once constructed — downstream
   consumers should not mutate the report.
3. **Schema evolution** must be detectable: a future-v2 report
   should not be silently parsed as v1.

POLYLENS run #4 audit on the POLYBUILD shadow scorer caught the
opposite mistake (`schema_version: int = 1` accepts any int, allowing
a v2 record to load as v1). We avoid that here by design.

## Decision

All `*Report` classes use:

```python
class XxxReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    ...
```

`extra="forbid"` rejects unknown fields at parse time; `frozen=True`
prevents post-construction mutation; `Literal[1]` rejects records
written by a future schema version.

## Consequences

### Positive

- Schema-level guard against drift on both the producer and consumer
  sides.
- Consumers can match on `schema_version` for migration paths.
- Frozen instances are safe to share across threads/loops.

### Negative / trade-offs

- A schema bump (1 → 2) requires either a discriminated union or two
  loader entry points. That cost is intentional — silent drift is
  worse than explicit migration.
- Test fixtures must rebuild full reports rather than mutate.

## Alternatives considered

- **Plain `int`** — rejected (the run-#4 anti-pattern).
- **No schema_version field** — rejected: closes off graceful
  evolution.
- **Dataclasses** — rejected: lose the JSON schema generation,
  forbid_extra, and `model_validate_json`.
