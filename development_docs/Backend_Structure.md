# Backend Structure & Conventions — Precedent

## Repository root layout

```
precedent/
├── development_docs/     ← PRD, Architecture, specs, plan (this folder)
├── backend/              ← all backend code (see §2 below)
├── frontend/             ← reserved; built later, out of scope for now
└── (assorted source list files — reference material, do not treat as spec)
```

All backend code lives under `backend/`. The layout is organized so every service, workflow, shared component, API route, and test is easy to locate. This document is the map; Implementation_Plan_Backend.md tasks reference these paths directly.

## 1. Guiding principles

- **Service-oriented modules.** Each of S1–S9 is a self-contained package under `app/services/`, exposing a small public interface (a service class or module functions). Services depend on shared `core/` utilities and the data layer, never on each other's internals — cross-service needs go through the other service's public interface or the DB.
- **Thin API, fat services.** Routers in `app/api/` do validation + call one service method + shape the response. Business logic lives in services, never in routers.
- **Deterministic vs LLM separation is visible in the tree.** Deterministic logic sits in plain modules; every LLM call is a task in `core/llm/` with a Pydantic schema and a versioned prompt template. You can audit "where does the system use an LLM?" by listing `core/llm/prompts/`.
- **One DB layer.** All persistence goes through `app/db/` (SQLAlchemy models + repositories). Services use repositories, not raw sessions scattered around.
- **Config and clients are singletons in `core/`.** LLM gateway, embeddings, object storage, settings — one place each.

## 2. Directory tree

```
backend/
├── pyproject.toml / requirements.txt      # deps (Tech_Stack §11)
├── .env.example                           # every env var (Tech_Stack §10)
├── alembic.ini
├── README.md                              # how to run locally
├── migrations/                            # Alembic migrations + env.py
│   └── versions/
├── scripts/
│   ├── seed_playbooks.py                  # pre-built playbook templates (NDA/DPA/SaaS/HIPAA/GDPR)
│   └── run_monitor.py                     # entrypoint the cron hits (S8 daily pass)
├── tests/
│   ├── conftest.py                        # fixtures: test DB, sample contracts, fake LLM gateway
│   ├── unit/                              # per-module unit tests (mirrors app/ tree)
│   ├── integration/                       # cross-service + DB-backed tests
│   └── fixtures/                          # sample PDF/DOCX, sample playbooks
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
    │   ├── config.py                      # pydantic-settings Settings (env)
    │   ├── logging.py
    │   ├── llm/
    │   │   ├── gateway.py                 # THE LLM gateway (FR-6): call_structured/call_text/call_batch
    │   │   ├── registry.py                # per-task → model tier mapping (Tech_Stack §4.2)
    │   │   ├── schemas/                    # Pydantic LLM output schemas — ONE module per service (parallel-safe; not a single shared file)
    │   │   │   ├── analysis.py             #   e.g. ClauseAnalysisOut, DeviationOut
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
    │   │       ├── obligation_extract.md
    │   │       ├── renewal_compliance.md
    │   │       └── version_semantic_summary.md
    │   ├── embeddings.py                   # sentence-transformers wrapper (Tech_Stack §5)
    │   ├── storage.py                      # object storage wrapper (Tech_Stack §3)
    │   └── diff/
    │       ├── aligner.py                  # clause-id alignment
    │       └── differ.py                   # char-level diff → tracked changes (shared S3 + Version Comparison)
    ├── db/
    │   ├── base.py                         # SQLAlchemy Base, engine, session factory
    │   ├── models/                         # one file per table group (Data_Model.md)
    │   │   ├── contract.py                 # contract, contract_metadata, contract_version, party
    │   │   ├── clause.py                   # clause, clause_embedding
    │   │   ├── analysis.py                 # flag, risk_score
    │   │   ├── redline.py
    │   │   ├── playbook.py                 # playbook, playbook_rule
    │   │   ├── nms.py                      # decision_event (+ pattern view mapping)
    │   │   ├── obligation.py               # obligation, alert
    │   │   ├── review.py                   # review_run
    │   │   └── qa.py                       # qa_cache
    │   ├── repositories/                   # data-access objects per aggregate
    │   │   ├── contract_repo.py
    │   │   ├── clause_repo.py
    │   │   ├── analysis_repo.py
    │   │   ├── redline_repo.py
    │   │   ├── playbook_repo.py
    │   │   ├── nms_repo.py
    │   │   ├── obligation_repo.py
    │   │   ├── review_repo.py
    │   │   └── search_repo.py              # full-text + vector + faceted queries
    │   └── views.sql                       # S9 analytics views + counterparty_pattern view
    ├── schemas/                            # Pydantic API + DTO models (Data_Model.md §12)
    │   ├── contract.py
    │   ├── clause.py
    │   ├── analysis.py
    │   ├── redline.py
    │   ├── playbook.py
    │   ├── obligation.py
    │   ├── review.py
    │   └── common.py                       # pagination, error envelope
    ├── services/
    │   ├── document_processing/
    │   │   ├── service.py                  # public: process(file, paper_origin) -> ProcessedContract
    │   │   ├── parsers.py                  # pdfplumber / python-docx
    │   │   ├── segmentation.py             # heading detection + boundaries
    │   │   ├── clause_types.py             # synonym/fuzzy normalizer
    │   │   └── extraction.py               # NER + regex metadata + counterpartyId
    │   ├── contract_analysis/
    │   │   ├── service.py                  # public: analyze(contract_id) -> AnalysisResult
    │   │   ├── layer1_structural.py        # missing/prohibited (deterministic)
    │   │   ├── rule_matcher.py             # clause↔rule matcher
    │   │   ├── layer2_content.py           # batched LLM (via gateway)
    │   │   └── scoring.py                  # severity-weighted risk (weights from playbook)
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
    │   │   ├── service.py                  # CRUD + resolve (merge applicable)
    │   │   ├── routing.py                  # practice-area routing + precedence merge
    │   │   └── bootstrap.py                # one-time batch LLM seed
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
        ├── gate.py                        # deterministic threshold gate + hard-stops
        └── version_comparison.py          # fetch versions -> align -> diff (uses core/diff)
```

## 3. Where each kind of thing goes

| Kind | Location |
|---|---|
| An HTTP endpoint | `app/api/routes/<service>.py` → calls a service |
| Deterministic business logic | `app/services/<service>/*.py` |
| An LLM call | a task in `core/llm/` (schema in `schemas/<service>.py`, prompt in `prompts/`, invoked via `gateway.py`) |
| A DB table | `app/db/models/<group>.py` + a repository in `app/db/repositories/` |
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
- **Tests mirror the tree:** `tests/unit/services/contract_analysis/test_scoring.py` etc. Deterministic modules get determinism tests (same input → same output). LLM-touching code is tested against a **fake gateway** (fixture) returning canned structured outputs — no live API calls in tests.
- **Async:** FastAPI routes are `async`; DB access can be sync via a threadpool or async SQLAlchemy — pick one and be consistent (async SQLAlchemy recommended). The embedding model call is CPU-bound — run in a threadpool executor.
- **Parallel-safe by construction (no single-file hotspots).** Because tasks may be built by separate agents concurrently, avoid files that every task must edit:
  - **Routers auto-discover.** `main.py` iterates `app/api/routes/` and includes each module's `router`. Adding an endpoint = adding one route file; **never** edit `main.py` per task.
  - **LLM schemas are per-service** (`core/llm/schemas/<service>.py`), never one shared `schemas.py`.
  - **Migrations are serialized, not parallel-authored.** Autogenerating two Alembic revisions in parallel branches the `down_revision` chain and requires a manual `alembic merge`. Rule: **all table DDL is created up front** in the Phase 0–1 migrations (T-003 owns the initial schema; the few later table-adding tasks either extend that migration set serially or are run one-at-a-time). Later tasks that "add a model" add **views/seed/data only**, not new migration heads, unless explicitly serialized. If you must add a migration, set `down_revision` to the current head and never run two such tasks concurrently.

## 5. Local run

`backend/README.md` documents: create venv, install deps, `cp .env.example .env` + fill, `alembic upgrade head`, `python scripts/seed_playbooks.py`, `uvicorn app.main:app --reload`. `GET /api/health` should return 200 with DB + embedding-model status.
