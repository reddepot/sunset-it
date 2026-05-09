# `sunset-it` — Specification v0.1

> Lib/CLI Python qui automatise la transition d'un projet IT solo (focus
> code IA-généré) vers un état freeze, maintenance ou sunset, en
> intégrant les meilleures pratiques 2024-2026 consolidées par 8 voix
> Deep Research (DeepSeek, Grok, Qwen, Claude Anthropic web_search,
> Gemini, Perplexity Computer, ChatGPT DR, Kimi Agent Swarm).

## Objectifs

1. **Reproductible** : un repo gelé doit pouvoir être rebuilt et compris
   après 6-12 mois sans assistance IA originale.
2. **Idempotent** : `sunset-it audit` lancé deux fois donne le même
   résultat sauf changement upstream. Pas de side-effect en mode audit.
3. **Réversible** : freeze ≠ EOL définitif. La sortie doit être
   contrôlée et réutilisable (`reactivate`).
4. **Modulaire** : checks plug-in, profils overridables, templates
   custom.
5. **Honnête sur la dette IA** : adresse spécifiquement test theatre,
   model anchoring, prompt rot, hallucinations latentes.
6. **Solo-friendly** : 6-10 heures total d'usage, pas de gouvernance
   externe.

## Layout du repo

```
sunset-it/
├── pyproject.toml              # uv-managed, hatchling
├── README.md
├── LICENSE                     # MIT
├── .gitignore
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── docs/
│   ├── adr/
│   │   ├── ADR-0001-cli-framework-typer.md
│   │   ├── ADR-0002-profile-yaml-config.md
│   │   ├── ADR-0003-template-engine-jinja2.md
│   │   ├── ADR-0004-pydantic-v2-schemas.md
│   │   └── ADR-0005-checks-plugin-architecture.md
│   ├── HANDOFF.md
│   └── RUNBOOK.md
├── src/sunset_it/
│   ├── __init__.py
│   ├── _version.py
│   ├── cli.py                  # Typer entry point
│   ├── core/                   # 6 phases publiques
│   │   ├── __init__.py
│   │   ├── audit.py
│   │   ├── hardening.py
│   │   ├── knowledge.py
│   │   ├── lockdown.py
│   │   ├── watch.py
│   │   └── reactivate.py
│   ├── checks/                 # plug-in checks
│   │   ├── __init__.py
│   │   ├── base.py             # Check protocol
│   │   ├── lockfile.py
│   │   ├── secrets.py
│   │   ├── tests.py
│   │   ├── security_cve.py
│   │   ├── ai_specific.py
│   │   ├── docs.py
│   │   └── runtime.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── reports.py          # *Report Pydantic models
│   │   ├── profile.py
│   │   ├── check.py
│   │   └── enums.py
│   ├── profiles/               # ressources YAML
│   │   ├── __init__.py
│   │   ├── solo-frozen.yaml
│   │   ├── solo-eol.yaml
│   │   ├── team-maintenance.yaml
│   │   └── oss-archive.yaml
│   ├── templates/              # ressources Jinja2
│   │   ├── __init__.py
│   │   ├── AGENTS.md.j2
│   │   ├── RUNBOOK.md.j2
│   │   ├── ADR.md.j2
│   │   ├── AI_GENERATION_MANIFEST.md.j2
│   │   ├── LESSONS.md.j2
│   │   ├── SUNSET_NOTICE.md.j2
│   │   └── workflow_sunset_yml.j2
│   └── utils/
│       ├── __init__.py
│       ├── git.py
│       ├── shell.py
│       └── logging.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_audit.py
    │   ├── test_checks.py
    │   ├── test_profiles.py
    │   └── test_templates.py
    └── integration/
        ├── test_cli.py
        ├── test_dogfood_polybuild.py
        └── fixtures/
            └── sample_repo/
```

## Décisions architecturales clés

### ADR-0001 — Framework CLI : **Typer** (pas Click, pas Fire)

| Critère | Typer | Click | Fire | Argparse |
|---|:-:|:-:|:-:|:-:|
| Type hints natifs | ✅ | ⚠️ via params | ⚠️ inféré | ❌ |
| Sub-commands hiérarchiques | ✅ | ✅ | ⚠️ | ⚠️ |
| Autocomplétion shell | ✅ via `typer install --completion` | ✅ | ❌ | ❌ |
| Async support | ✅ via Typer 0.9+ | ⚠️ via plugins | ❌ | ❌ |
| Rich tracebacks | ✅ | ⚠️ | ❌ | ❌ |
| Vélocité de release 2024-2026 | active | active | inactive | stdlib |

**Décision** : Typer ≥ 0.12 (FastAPI-style, type hints first, intégration
naturelle avec Pydantic v2 pour les outputs).

### ADR-0002 — Profils : **YAML config + Pydantic validation**

YAML (humainement éditable, extends-able à la Renovate-style) plutôt
que Python config (impératif, inheritance ad-hoc). Validation stricte
via Pydantic v2 au load.

### ADR-0003 — Templating : **Jinja2** (pas cookiecutter, pas copier)

Jinja2 fait partie de la stdlib de l'écosystème scientifique Python ;
mature, sandboxable, scriptable. Cookiecutter et copier sont conçus
pour la *création* de projet, pas l'émission de fichiers individuels
dans un projet existant.

### ADR-0004 — Schemas : **Pydantic v2** avec `model_config = ConfigDict(extra="forbid", frozen=True)`

Pour tous les `*Report` outputs, schema_version `Literal[1]`,
extra="forbid" pour détecter les drift, frozen=True pour empêcher la
mutation après création.

### ADR-0005 — Checks : architecture **plugin-style protocol**

```python
class Check(Protocol):
    name: str  # unique identifier
    description: str
    severity: Literal["blocker", "warning", "info"]

    def applicable(self, repo: Path, profile: Profile) -> bool: ...
    def run(self, repo: Path, profile: Profile) -> CheckResult: ...
```

Avantage : ajouter un check = ajouter un fichier dans `checks/` sans
toucher au core. Découverte automatique via `pkgutil.iter_modules()`.

## API publique — 6 phases

### Phase 1 : `audit`

```python
def audit(
    repo: Path,
    profile_name: str = "solo-frozen",
    profile_overrides: dict[str, Any] | None = None,
    output_format: Literal["json", "markdown", "human"] = "human",
    fail_on: Literal["never", "warning", "blocker"] = "blocker",
    cache_dir: Path | None = None,
) -> AuditReport:
    """État actuel du repo. Read-only. Idempotent."""
```

**Output** :
```python
class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    timestamp: datetime
    sunset_it_version: str
    repo_path: Path
    profile_name: str
    checks: list[CheckResult]
    summary: AuditSummary

class CheckResult(BaseModel):
    name: str
    severity: Literal["blocker", "warning", "info"]
    passed: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float

class AuditSummary(BaseModel):
    total: int
    passed: int
    failed_blocker: int
    failed_warning: int
    overall_status: Literal["green", "yellow", "red"]
```

### Phase 2 : `hardening`

```python
def hardening(
    repo: Path,
    profile_name: str = "solo-frozen",
    check_only: bool = False,  # dry-run
    apply_fixes: bool = False,  # patches automatiques
    output_format: Literal["json", "markdown", "human"] = "human",
) -> HardeningReport:
    """Applique la Definition of Done étendue. Modifie le repo si apply_fixes=True."""
```

### Phase 3 : `knowledge`

```python
def knowledge(
    repo: Path,
    emit_dir: Path = Path("docs"),
    profile_name: str = "solo-frozen",
    overwrite: bool = False,  # n'overrwrite pas par défaut
    template_overrides_dir: Path | None = None,
) -> KnowledgeReport:
    """Émet AGENTS.md, RUNBOOK.md, ADRs, AI_GENERATION_MANIFEST.md, LESSONS.md, SUNSET_NOTICE.md."""
```

### Phase 4 : `lockdown`

```python
def lockdown(
    repo: Path,
    tag_name: str | None = None,  # default : freeze-YYYY-MM-DD
    branch_name: str = "maintenance",
    profile_name: str = "solo-frozen",
    pin_dependencies: bool = True,
    update_readme_banner: bool = True,
) -> LockdownReport:
    """Tag git annoté + branch maintenance + lockfile hashes + status banner README."""
```

### Phase 5 : `watch`

```python
def watch(
    repo: Path,
    profile_name: str = "solo-frozen",
    output_format: Literal["json", "markdown", "gh-summary"] = "json",
    emit_issues: bool = False,  # auto-create GH issues
) -> WatchReport:
    """Wake policy : CVE, EOL deps, model deprecation, prompt regression."""
```

### Phase 6 : `reactivate`

```python
def reactivate(
    repo: Path,
    reason: str,  # justification documentée
    branch_from: str = "maintenance",
) -> ReactivateReport:
    """Sortie de freeze contrôlée. Crée tag unfrozen-YYYY-MM-DD, ouvre branche dev."""
```

## Exit codes (universels sur toutes les phases)

| Code | Sens |
|---|---|
| 0 | OK — tous blockers passés |
| 1 | warnings — recommandés failed mais blockers OK |
| 2 | blockers — au moins un check bloquant a échoué |
| 3 | misuse — argv invalide, repo introuvable, profil inconnu |
| 4 | transient — timeout, lock, réseau |

## Profils prédéfinis

### `solo-frozen` (cas POLYBUILD)

- reversible, mainteneur unique, pas d'utilisateurs externes
- monitoring weekly Dependabot, mensuel pip-audit
- 5 ADRs minimum, AGENTS.md obligatoire, AI_GENERATION_MANIFEST obligatoire
- model_deprecation_window: 90 jours
- runtime_python_eol_window: 180 jours

### `solo-eol`

- sunset définitif, pas de réactivation prévue
- archivage Git, branch deletion
- final lessons learned obligatoire
- pas de monitoring continu (snapshot final uniquement)

### `team-maintenance`

- équipe en maintenance, utilisateurs actifs
- monitoring quotidien (CVE), hebdomadaire (deps)
- runbook complet (incident response inclus)
- on-call rotation documentée
- SLO/SLA explicites

### `oss-archive`

- projet OSS public archivé Apache Attic-style
- README banner "Archived as of YYYY-MM-DD"
- redirect vers fork si applicable
- lockdown final + GitHub repo archived flag

## Checks (9 livrés en v0.1, +6 prévus v0.2)

| Check | Severity (solo-frozen) | Description |
|---|---|---|
| `lockfile_present` | blocker | requirements.txt / poetry.lock / uv.lock existe |
| `lockfile_with_hashes` | warning | pip-compile --generate-hashes ou poetry lock |
| `secrets_clean` | blocker | gitleaks ou truffleHog scan clean |
| `tests_passing` | blocker | pytest exit 0 sur clean clone |
| `smoke_contract_present` | warning | au moins 1 e2e test |
| `cve_critical_high_clean` | blocker | pip-audit / Trivy : aucune CVE Critical/High avec fix |
| `python_runtime_supported` | warning | Python version pas en EOL window 180j |
| `agents_md_present` | blocker | AGENTS.md ou CLAUDE.md ou .cursor/rules à la racine |
| `runbook_present` | blocker | docs/RUNBOOK.md ou docs/runbook.md |
| `ai_generation_manifest_present` | warning | AI_GENERATION_MANIFEST.md mentionne modèles/dates |
| `adr_dir_present` | warning | docs/adr/ avec ≥ 3 ADRs |
| `git_freeze_tag_present` | warning | tag `freeze-*` ou `v*-frozen` |
| `readme_status_banner_present` | warning | README contient "Frozen", "Maintenance", ou similaire |
| `dependencies_pinned` | blocker | versions exactes (pas `^x.y.z`) |
| `model_used_not_deprecated` | warning | manifest référence des modèles encore actifs |

## Templates Jinja2 (variables exposées)

### AGENTS.md.j2

```jinja2
# Agent Instructions for {{ project_name }}

## Project overview
{{ project_overview }}

## Build and test
- Install: `{{ install_cmd }}`
- Unit tests: `{{ test_cmd }}`
- Smoke: `{{ smoke_cmd }}`

## Conventions
{% for convention in conventions %}
- {{ convention }}
{% endfor %}

## Known pitfalls
{% for pitfall in pitfalls %}
- {{ pitfall }}
{% endfor %}

## Freeze policy
This project is in **{{ freeze_status }}** as of {{ freeze_date }}.
{% if reactivation_path %}
Reactivation: {{ reactivation_path }}
{% endif %}
```

### AI_GENERATION_MANIFEST.md.j2

```jinja2
# AI Generation Manifest

## Project state
- Freeze date: {{ freeze_date }}
- Freeze tag: {{ freeze_tag }}
- Primary language/runtime: {{ language }} {{ runtime_version }}

## Models used
{% for model in models %}
| Tool | Model | Period | Role |
|---|---|---|---|
| {{ model.tool }} | {{ model.id }} | {{ model.period }} | {{ model.role }} |
{% endfor %}

## Non-regenerable decisions
{% for d in decisions %}
- {{ d.title }} → ADR-{{ d.adr }}
{% endfor %}

## Known AI debt
{% for debt in ai_debts %}
- {{ debt.area }}: {{ debt.risk }} → {{ debt.mitigation }}
{% endfor %}
```

(Autres templates RUNBOOK, ADR, LESSONS, SUNSET_NOTICE, workflow_sunset.yml décrits dans sections séparées du repo.)

## Intégration GitHub Actions

`sunset-it knowledge` peut émettre `.github/workflows/sunset.yml` qui
exécute `sunset-it watch --emit-issues` en cron weekly + on-demand.

## Stack technique

```toml
[project]
name = "sunset-it"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydantic>=2.5",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "rich>=13.0",
    "structlog>=23.0",
    "click>=8.1",  # transitive via typer
]

[project.optional-dependencies]
audit = [
    "pip-audit>=2.7",
]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "ruff>=0.1",
    "mypy>=1.7",
    "bandit>=1.7",
    "hypothesis>=6.92",
]

[project.scripts]
sunset-it = "sunset_it.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Non-goals (V1)

- Pas de support multi-langage : Python only en V1 (extensible Rust/Go en V2 si demande)
- Pas de GUI / web dashboard
- Pas de Postgres backend (file-based JSON outputs uniquement)
- Pas de notification Slack/email built-in (laissé à l'intégration CI)
- Pas de prompt versioning automatique (référence externe via `prompts/` directory documentée dans AI_GENERATION_MANIFEST)
- Pas d'analyse statique propriétaire (réutilise pip-audit, Trivy, gitleaks via subprocess)

## MVP scope (v0.1.0)

3 phases sur 6, profil unique :
- `audit` (15 checks)
- `knowledge` (templates AGENTS.md + RUNBOOK + AI_GENERATION_MANIFEST)
- `lockdown` (lockfile + tag + banner)
- profil `solo-frozen` uniquement
- Dogfooding immédiat sur POLYBUILD v3.2.6

V0.2 ajoutera : `hardening`, `watch`, `reactivate`, profils `solo-eol` + `team-maintenance` + `oss-archive`.
