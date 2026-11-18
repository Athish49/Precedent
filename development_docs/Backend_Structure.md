# Backend Structure & Conventions — Precedent

## Repository root layout

```
precedent/
├── development_docs/     ← PRD, Architecture, specs, plan (this folder)
├── backend/              ← all backend code (see §2 below)
├── frontend/             ← web client (see Implementation_Plan_Frontend.md)
├── playbook_status.md / playbook_plan.md / playbook_implementation.md   ← playbook audit, target design, task breakdown
└── (assorted source list files — reference material, do not treat as spec)
```

All backend code lives under `backend/`. The layout is organized so every service, workflow, shared component, API route, and test is easy to locate. This document is the map; Implementation_Plan_Backend.md tasks reference these paths directly.

## 1. Guiding principles

- **Service-oriented modules.** Each of S1–S9 is a self-contained package under `app/services/`, exposing a small public interface (a service class or module functions). Services depend on shared `core/` utilities and the data layer, never on each other's internals — cross-service needs go through the other service's public interface or the DB.
- **Thin API, fat services.** Routers in `app/api/` do validation + call one service method + shape the response. Business logic lives in services, never in routers.
- **Deterministic vs LLM separation is visible in the tree.** Deterministic logic sits in plain modules; every LLM call is a task in `core/llm/` with a Pydantic schema and a versioned prompt template. You can audit "where does the system use an LLM?" by listing `core/llm/prompts/`.
- **One DB layer.** All persistence goes through `app/db/` (SQLAlchemy models + repositories). Services use repositories, not raw sessions scattered around.
- **Config and clients are singletons in `core/`.** LLM gateway, embeddings, object storage, settings — one place each.
- **One namespace.** `PROJECT_NAMESPACE` in `core/config.py` is the only place the project name is written. The Postgres schema and the object-key prefix derive from it; nothing else hard-codes either.
- **Cloud only.** No local database and no local storage backend. Scripts never write project data to disk; files in transit stay in memory.
- **Seed is a separate folder.** `backend/seed/` holds all seed code, content and seed tests. The application never depends on it (§6).

## 2. Directory tree

```
backend/
├── pyproject.toml / requirements.txt      # deps (Tech_Stack §11)
├── .env.example                           # every env var (Tech_Stack §10)
├── alembic.ini
├── README.md                              # how to run locally
├── migrations/                            # Alembic migrations + env.py
│   └── versions/
│       ├── 001 … 009                      # original schema + analytics views
│       ├── 010_playbook_lookups.py        # agreement_type, clause_family, clause_issue, context_dimension, approver_role, escalation_policy + reference rows
│       ├── 011_playbook_structure.py      # playbook/rule extensions, versions, change log, six rule child tables, legacy backfill
│       └── 012_playbook_outcomes.py       # contract/clause/flag/risk_score/redline/decision_event/review_run columns, playbook_exception
├── scripts/                               # OPERATIONAL scripts only — no seed code here
│   ├── run_monitor.py                     # entrypoint the cron hits (S8 daily pass)
│   ├── check_partition.py                 # read-only: nothing of this project outside its schema / prefix; no local storage folder
│   ├── move_to_schema.py                  # one-time move of the original objects from public into the project schema (--dry-run default)
│   └── run_rule_tests.py                  # CLI for the rule test-case runner
├── seed/                                  # ALL seed code, content and seed tests (§6). Optional; deletable
├── tests/
│   ├── conftest.py                        # fixtures: placeholder DB + storage settings, sample contracts, fake LLM gateway
│   ├── in_memory_storage.py               # InMemoryStorage test double — tests write nothing to disk
│   ├── unit/                              # per-module unit tests
│   │   ├── test_seed_isolation.py         # guard: nothing outside seed/ imports or points into seed/
│   │   ├── test_schema_partitioning.py    # every table carries the project schema; no unqualified raw SQL
│   │   └── ...
│   ├── integration/                       # cross-service + DB-backed tests
│   └── fixtures/                          # sample PDF/DOCX; legacy_playbook_rows.py (the 29 legacy rules, for the 011 backfill test)
└── app/
    ├── main.py                            # app factory; AUTO-DISCOVERS routers from api/routes/ (no per-task edits); startup (load embedding model, ping DB)
    ├── api/
    │   ├── deps.py                        # FastAPI dependencies (db session, service providers)
    │   ├── errors.py                      # error envelope + exception handlers
    │   └── routes/
    │       ├── documents.py               # S1
    │       ├── repository.py              # S7
    │       ├── playbooks.py               # S6
    │       ├── analysis.py                # S2
    │       ├── redlines.py                # S3
    │       ├── drafting.py                # S4
    │       ├── intelligence.py            # S5
    │       ├── obligations.py             # S8
    │       ├── analytics.py               # S9
    │       ├── review.py                  # Review Pipeline + Autonomous Trigger
    │       ├── versions.py                # Version Comparison
    │       └── health.py
    ├── core/
    │   ├── config.py                      # pydantic-settings Settings (env): project_namespace, db_schema, object_storage_prefix; storage settings required
    │   ├── namespace.py                   # schema helpers, project object list, assert_namespace() write guard
    │   ├── logging.py
    │   ├── llm/
    │   │   ├── gateway.py                 # THE LLM gateway (FR-6): call_structured/call_text/call_batch
    │   │   ├── registry.py                # per-task → model tier mapping (Tech_Stack §4.2)
    │   │   ├── schemas/                    # Pydantic LLM output schemas — ONE module per service (parallel-safe; not a single shared file)
    │   │   │   ├── analysis.py             #   e.g. ClauseAnalysisOut, DeviationOut; [planned] per-rule position match, parameter values, semantic red-line answers
    │   │   │   ├── redline.py              #   RedlineOut
    │   │   │   ├── search.py               #   SmartSearchFilters
    │   │   │   ├── playbook.py             #   PlaybookBootstrapOut
    │   │   │   ├── obligation.py           #   ObligationOut, RenewalComplianceOut
    │   │   │   └── ...                      #   one per LLM-using service
    │   │   └── prompts/                    # versioned prompt templates (one file per task)
    │   │       ├── analysis_own_paper.md
    │   │       ├── analysis_counterparty.md
    │   │       ├── redline_generate.md
    │   │       ├── redline_refine.md
    │   │       ├── drafting_rewrite.md
    │   │       ├── drafting_precedent.md
    │   │       ├── drafting_memo.md
    │   │       ├── summarize.md
    │   │       ├── summarize_redlines.md
    │   │       ├── qa_answer.md
    │   │       ├── easy_prompt.md
    │   │       ├── research_synthesize.md
    │   │       ├── smart_search_filters.md
    │   │       ├── playbook_bootstrap.md
    │   │       ├── contract_type_classify.md   # [planned] fast-tier contract-type classification
    │   │       ├── obligation_extract.md
    │   │       ├── renewal_compliance.md
    │   │       └── version_semantic_summary.md
    │   ├── embeddings.py                   # sentence-transformers wrapper (Tech_Stack §5)
    │   ├── storage.py                      # S3-compatible backend only; adds the project prefix to every key; no local fallback
    │   └── diff/
    │       ├── aligner.py                  # clause-id alignment
    │       └── differ.py                   # char-level diff → tracked changes (shared S3 + Version Comparison)
    ├── db/
    │   ├── base.py                         # SQLAlchemy Base with MetaData(schema=<db_schema>), engine, session factory
    │   ├── models/                         # one file per table group (Data_Model.md)
    │   │   ├── contract.py                 # contract, contract_metadata, contract_version, party
    │   │   ├── clause.py                   # clause, clause_embedding
    │   │   ├── analysis.py                 # flag, risk_score
    │   │   ├── redline.py
    │   │   ├── playbook.py                 # playbook, playbook_version, playbook_change_log, playbook_rule, rule_position, rule_parameter, red_line, rule_objection, rule_dependency, rule_test_case
    │   │   ├── taxonomy.py                 # agreement_type, clause_family, clause_issue, context_dimension
    │   │   ├── authority.py                # approver_role, escalation_policy
    │   │   ├── exception.py                # playbook_exception
    │   │   ├── nms.py                      # decision_event (+ pattern view mapping)
    │   │   ├── obligation.py               # obligation, alert
    │   │   ├── review_run.py               # review_run
    │   │   └── qa_cache.py                 # qa_cache
    │   ├── repositories/                   # data-access objects per aggregate
    │   │   ├── contract_repo.py
    │   │   ├── clause_repo.py
    │   │   ├── analysis_repo.py
    │   │   ├── redline_repo.py
    │   │   ├── playbook_repo.py            # playbooks, rules, versions (create/copy/publish), change log, child CRUD, get_rules_with_children, upsert-by-key helpers
    │   │   ├── taxonomy_repo.py            # agreement types, clause families, clause issues, context dimensions
    │   │   ├── authority_repo.py           # approver roles, escalation policies
    │   │   ├── nms_repo.py
    │   │   ├── obligation_repo.py
    │   │   ├── review_run_repo.py
    │   │   ├── qa_cache_repo.py
    │   │   └── search_repo.py              # full-text + vector + faceted queries
    │   └── views.sql                       # S9 analytics views + counterparty_pattern view (schema-qualified)
    ├── schemas/                            # Pydantic API + DTO models (Data_Model.md §12)
    │   ├── contract.py
    │   ├── clause.py
    │   ├── analysis.py
    │   ├── redline.py
    │   ├── playbook.py                     # CRUD models + responses for every playbook entity + ResolvedRule
    │   ├── obligation.py
    │   ├── review.py
    │   └── common.py                       # pagination, error envelope
    ├── services/
    │   ├── document_processing/
    │   │   ├── service.py                  # public: process(file, paper_origin) -> ProcessedContract
    │   │   ├── parsers.py                  # pdfplumber / python-docx
    │   │   ├── segmentation.py             # heading detection + boundaries
    │   │   ├── clause_types.py             # synonym/fuzzy normalizer; synonyms load from clause_family into a process-wide cache at startup (task 5.5; the in-code _SYNONYMS dict is gone)
    │   │   └── extraction.py               # NER + regex metadata + counterpartyId
    │   ├── contract_analysis/
    │   │   ├── service.py                  # public: analyze(contract_id) -> AnalysisResult
    │   │   ├── layer1_structural.py        # missing clauses + prohibited terms (deterministic); [planned] phrase/regex red lines with negation guard
    │   │   ├── rule_matcher.py             # clause↔rule matcher
    │   │   ├── layer2_content.py           # batched LLM (via gateway); [planned] per-rule extraction
    │   │   ├── evaluator.py                # [planned] pure functions: zone_for_parameter, evaluate_finding — the only place a zone is assigned
    │   │   └── scoring.py                  # severity-weighted risk (weights from playbook); [planned] normalised 0–1, WEIGHTS_VERSION v2
    │   ├── redline/
    │   │   ├── service.py                  # public: generate(contract_id, stance) + refine + toggle
    │   │   ├── stance.py                   # deterministic stance filter + NMS stance context
    │   │   └── render.py                   # uses core/diff to turn replacement text -> tracked changes
    │   ├── drafting/
    │   │   ├── service.py                  # cascade orchestration
    │   │   └── frequency_tracker.py        # deterministic last-N scoped query
    │   ├── intelligence/
    │   │   ├── service.py
    │   │   └── navigation.py               # deterministic index
    │   ├── playbook/
    │   │   ├── service.py                  # CRUD (PATCH uses exclude_unset, so null clears a field)
    │   │   ├── routing.py                  # resolve; today identity match on practice area; [planned] base + agreement + overlays merged by rule_key, matches(condition, context)
    │   │   ├── bootstrap.py                # batch LLM mining of preferred language + variants; [planned] writes positions into a draft version
    │   │   └── testing.py                  # [planned] rule test-case runner (deterministic and model modes)
    │   ├── repository/
    │   │   ├── service.py                  # store/version/search facade
    │   │   ├── fulltext.py                 # tsvector queries
    │   │   ├── vector.py                   # pgvector queries (embedding on write)
    │   │   └── smart_search.py             # LLM NL->filters + execute
    │   ├── obligations/
    │   │   ├── service.py                  # extract + compliance
    │   │   └── monitor.py                  # deterministic daily pass
    │   └── analytics/
    │       └── service.py                  # reads over views.sql
    └── workflows/
        ├── review_pipeline.py             # code-orchestrated S1→S6→S2→S3
        ├── gate.py                        # deterministic gate; today two outcomes on score thresholds; [planned] three-zone gate with approver routing
        └── version_comparison.py          # fetch versions -> align -> diff (uses core/diff)
```

## 3. Where each kind of thing goes

| Kind | Location |
|---|---|
| An HTTP endpoint | `app/api/routes/<service>.py` → calls a service |
| Deterministic business logic | `app/services/<service>/*.py` |
| An LLM call | a task in `core/llm/` (schema in `schemas/<service>.py`, prompt in `prompts/`, invoked via `gateway.py`) |
| A DB table | `app/db/models/<group>.py` + a repository in `app/db/repositories/`. Do not set a schema on the table; it inherits the project schema from `Base.metadata` |
| Reference data the application needs to run | Literal rows in a migration (agreement types, clause families) |
| Company or demonstration content | `backend/seed/<category>/data/` — never under `app/`, `scripts/` or `tests/` |
| Seed loaders, validators, reports and their tests | `backend/seed/` |
| Operational scripts (cron entrypoint, partition check, schema move) | `backend/scripts/` |
| Hand-written SQL | Names the schema explicitly, built from `settings.db_schema` |
| Cross-service orchestration | `app/workflows/` |
| Shared engines (diff, embeddings, storage) | `app/core/` |
| API/DTO shapes | `app/schemas/` |

## 4. Conventions

- **Service public interface:** each `services/<s>/service.py` exposes one class (e.g. `DocumentProcessingService`) or module-level functions; routers/workflows depend only on that. Internal helpers stay private to the package.
- **No cross-service imports of internals.** S3 needing S7's diff engine uses `core/diff` (shared), not `services/repository` internals. S2 needing playbook data calls `S6.resolve()` or reads via a repository.
- **LLM calls only via the gateway.** Grep test in CI: `import anthropic` may appear only in `core/llm/`.
- **Determinism guard:** deterministic modules must not import the gateway. S1 and S9 packages never import `core/llm`.
- **Offsets & clause-type are sacred:** never regenerate `char_start/end` or `clause_type` downstream; carry them.
- **Prompts are files, versioned:** editing a prompt = editing its `.md` template; keep a `# version:` header and keep the cached prefix byte-stable for prompt caching.
- **Repositories return domain/ORM objects, routers return Pydantic schemas.** Convert at the service boundary.
- **Namespace rules.** Migrations do not name a schema in `op.create_table`; `migrations/env.py` sets the search path for the migration transaction. Never create, drop or alter anything in `public`, and never touch the `vector` extension. Storage callers pass logical keys (`contracts/{id}/{filename}`); the backend adds the prefix. Every script that writes data calls `assert_namespace()` first.
- **No local data.** No SQLite, local Postgres, Docker database, filesystem storage backend or browser storage. Unit tests use mocked sessions, a mocked S3 client and the `InMemoryStorage` double.
- **Seed isolation guard:** nothing under `app/`, `migrations/`, `scripts/` or `tests/` may contain `import seed`, `from seed` or a path into `seed/`. Enforced by `tests/unit/test_seed_isolation.py` and a CI step.
- **Zones come from the evaluator.** Model output is extraction only; `contract_analysis/evaluator.py` is the single place that turns it into green, yellow or red.
- **Published versions are immutable.** Services and loaders write rule data only to a draft version.
- **Tests mirror the tree:** `tests/unit/services/contract_analysis/test_scoring.py` etc. Deterministic modules get determinism tests (same input → same output). LLM-touching code is tested against a **fake gateway** (fixture) returning canned structured outputs — no live API calls in tests.
- **Async:** FastAPI routes are `async`; DB access can be sync via a threadpool or async SQLAlchemy — pick one and be consistent (async SQLAlchemy recommended). The embedding model call is CPU-bound — run in a threadpool executor.
- **Parallel-safe by construction (no single-file hotspots).** Because tasks may be built by separate agents concurrently, avoid files that every task must edit:
  - **Routers auto-discover.** `main.py` iterates `app/api/routes/` and includes each module's `router`. Adding an endpoint = adding one route file; **never** edit `main.py` per task.
  - **LLM schemas are per-service** (`core/llm/schemas/<service>.py`), never one shared `schemas.py`.
  - **Migrations are serialized, not parallel-authored.** Autogenerating two Alembic revisions in parallel branches the `down_revision` chain and requires a manual `alembic merge`. Rule: **all table DDL is created up front** in the Phase 0–1 migrations (T-003 owns the initial schema; the few later table-adding tasks either extend that migration set serially or are run one-at-a-time). Later tasks that "add a model" add **views/seed/data only**, not new migration heads, unless explicitly serialized. If you must add a migration, set `down_revision` to the current head and never run two such tasks concurrently.

## 5. Local run

`backend/README.md` documents: create venv, install deps, `cp .env.example .env` + fill (database URL and all four object-storage values are required — there is no local storage mode), `alembic upgrade head`, `uvicorn app.main:app --reload`. `GET /api/health` should return 200 with DB, embedding-model and storage status, plus the project schema name and whether it exists.

Seeding is optional demonstration data, not a setup step. `backend/README.md` documents the current loader (`python -m seed.playbooks.load [--dry-run]`).

Application tests: `cd backend && .venv/bin/python -m pytest -q` (collects `tests/` only).

## 6. Seed folder

Everything to do with seeding lives in `backend/seed/`. It sits under `backend/` because its loaders use the application's models and settings and run in the same Python environment, but it is not part of the application: with the folder deleted the application still starts, migrates, passes its suite and serves every feature.

```
backend/seed/
├── README.md                     # categories, commands, isolation rules
├── common/                       # seed-only helpers: yaml_loader.py, db.py (seed_session + namespace guard), cli.py (--dry-run), paths.py, errors.py
├── playbooks/                    # category: playbooks
│   ├── models.py                 # Pydantic models for the seed files (unknown keys forbidden)
│   ├── validate.py               # python -m seed.playbooks.validate [dir] — models + cross-checks, no database
│   ├── report.py                 # python -m seed.playbooks.report [dir] — coverage against the content targets
│   ├── load.py                   # python -m seed.playbooks.load [dir] [--dry-run] [--only <key>]
│   └── data/halcyon/
│       ├── company_profile.md  authoring_guide.md  REVIEW.md
│       ├── taxonomy.yaml         # expected family keys + clause issues
│       ├── authority.yaml        # context dimensions, approver roles, global red lines, escalation policies
│       ├── playbooks/<name>/     # playbook.yaml + one or more rules files, per playbook (7 playbooks)
│       └── versions/             # full 1.1 rule sets + change lists (saas_msa_vendor, dpa_processor)
├── contracts/                    # category: synthetic contracts — [planned] build.py, data/halcyon/{source,docx,expected.yaml}
├── history/                      # category: negotiation history — [planned] models.py, load.py, data/halcyon/decisions.yaml
└── tests/                        # seed tests only: pytest seed/tests (not in the application's testpaths)
```

A new seed category is another sub-folder with the same shape: code at the top, content under `data/<dataset>/`.

**Isolation rules.**

| # | Rule |
|---|---|
| 1 | Dependencies run one way. Seed code may import from `app`. Nothing in `app`, `migrations`, `scripts` or the application tests imports from `seed`, reads its files or calls its commands |
| 2 | No seed code, seed content or seed test exists outside `backend/seed/` |
| 3 | Seed tests are not part of the application suite. The application suite passes with the folder absent |
| 4 | Libraries only seed code needs go in the `seed` dependency group in `pyproject.toml` (`pyyaml` is the first) |
| 5 | Data the application needs in order to run is reference data and comes from migrations, not from seed |
| 6 | Every feature works with no seed data loaded |
| 7 | Product features are not seed. The playbook bootstrap, the rule test runner and the publish flow stay in `app` and never read seed files |
| 8 | An automated guard in the application suite and in CI enforces rule 1 |

**Loader behaviour** (`seed/playbooks/load.py`): writes issues, context dimensions, roles, escalation policies, global red lines, playbooks, versions, rules and children, then change logs; upserts by stable key; one transaction per playbook; never modifies a published version (a changed file for a published version is an error asking for a new version file); archives, never deletes, playbooks whose key is not in the seed directory; stops with a clear error if an agreement type or clause family is missing, naming the migration that provides it.

**Seed content today** (from `python -m seed.playbooks.report`, 2026-11-16): 7 playbooks, 9 versions, 130 rules in force, 521 positions, 139 parameters, 158 red lines (12 global), 260 objections, 144 dependencies, 790 test cases, 98 clause issues, 5 context dimensions, 9 approver roles, 56 escalation policies, 23 change-log entries. The validator reports 0 errors.
