# sunset-it

> Solo dev project freeze / maintenance / sunset toolkit, with a
> particular focus on AI-coded codebases. CLI Python ≥ 3.11.

`sunset-it` automates the transition of a repository from active
development to a stable, resumable, reasonably-safe state. It is
designed for the case where:

- You are **the only maintainer**, and
- The code was **co-written with AI assistants** (Claude Code, Cursor,
  Codex, Gemini CLI, Kimi…), and
- You want a **reversible freeze** — not an EOL — that you (or a
  future agent) can safely reopen in 6-12 months.

The tool consolidates 2024-2026 best practices from formal closure
methodologies (PMBOK, PRINCE2), open-source sunsetting playbooks
(Apache Attic, CNCF, CHAOSS), DevOps SRE handbooks (Google SRE,
Atlassian, GitLab, Microsoft) and AI-coding-specific debt research
(arXiv 2024-2026 on test theatre, model anchoring, package
hallucinations) into a single CLI.

## Status

**v0.1 — MVP**. Three phases shipped: `audit`, `knowledge`,
`lockdown`. Three more (`hardening`, `watch`, `reactivate`) are
planned for v0.2. Suitable for dogfooding on small Python projects
right now.

## Install

```bash
uv tool install sunset-it
# or, from a clone:
uv pip install -e .
```

## Quick start

```bash
# 1. Audit the repo against the default profile (read-only).
sunset-it audit .

# 2. Generate the documentation set (AGENTS.md, RUNBOOK, manifest, …).
sunset-it knowledge .

# 3. Apply the freeze (annotated tag + maintenance branch + README banner).
sunset-it lockdown .
```

## Phases

| Phase | Status | What it does |
|-------|--------|--------------|
| `audit` | ✅ v0.1 | Read-only check of the repo against a profile. |
| `knowledge` | ✅ v0.1 | Render Jinja2 templates: AGENTS.md, RUNBOOK.md, AI_GENERATION_MANIFEST.md, SUNSET_NOTICE.md, LESSONS.md. |
| `lockdown` | ✅ v0.1 | Annotated git tag + maintenance branch + README freeze banner. |
| `hardening` | 🚧 v0.2 | Apply extended Definition of Done (smoke contract, CI gates, dep pinning). |
| `watch` | 🚧 v0.2 | Wake-policy CI: CVE / dep EOL / model deprecation. |
| `reactivate` | 🚧 v0.2 | Controlled exit from freeze. |

## Profiles

`solo-frozen` ships with v0.1. Three more (`solo-eol`,
`team-maintenance`, `oss-archive`) ship in v0.2.

You can override any profile by dropping a YAML file under
`--profile-overrides-dir` (single-level `extends:` supported).

## Why "AI-coded specific"?

Existing closure tooling does not address the failure modes we now see
on AI-co-written codebases:

- **Model anchoring** — code that only re-generates identically with a
  specific model snapshot. Anthropic and OpenAI both retire models
  with 60+ day notice; a project that depends on a retired model
  silently loses regenerability.
- **Test theatre** — tests written by the same model as the code may
  validate the bug rather than the spec. Empirical 2024-2026 work
  finds 20-38% mutation detection on tests authored by their own
  generator.
- **Package hallucinations** — 5-22% of LLM-generated Python samples
  reference packages that don't exist on PyPI (slopsquatting risk).
- **Prompt rot** — prompts that produced working code on model X
  silently underperform on model X+1.

`sunset-it` writes an `AI_GENERATION_MANIFEST.md` that documents
which models produced what, and the `audit` phase checks that the
manifest exists, the lockfile uses hashes, and the AGENTS.md /
runbook are present so a future agent (or future-you) can resume
without re-discovering everything from the source.

## Repo layout

```
src/sunset_it/
├── cli.py               # Typer entry point
├── core/                # 6 phases (3 implemented in v0.1)
├── checks/              # plug-in checks (10 ships in v0.1)
├── models/              # Pydantic v2 schemas
├── profiles/            # YAML profiles (solo-frozen ships in v0.1)
├── templates/           # Jinja2 templates
└── utils/
tests/
├── unit/
└── integration/
```

## Develop

```bash
uv sync --all-extras --dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## License

MIT — see [LICENSE](LICENSE).

## Origin

`sunset-it` is itself an AI-coded project. Its specification was
synthesised from 8 Deep Research voices (Claude Anthropic web_search,
ChatGPT DR, Perplexity, Grok 4.3, Qwen 3.6 Plus, Gemini DR, DeepSeek,
Kimi Agent Swarm), challenged by Codex CLI on three architectural
axes (CLI framework, API surface, GitHub Actions integration), and
implemented in one autonomous session. The first dogfood target is
[POLYBUILD v3.2.6](https://github.com/reddepot/polybuild_v3) — itself
a multi-LLM orchestrator. Eat your own dog food, especially when the
dog is silicon.
