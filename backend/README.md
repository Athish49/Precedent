# Precedent — Backend

Python + FastAPI backend for the Precedent contract-intelligence platform.

**Before writing any code, read `../development_docs/`** — start with `00_README.md`, then build from `Implementation_Plan_Backend.md` (task by task). This directory's structure is defined in `../development_docs/Backend_Structure.md`.

---

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2 (async) + Alembic · Neon Postgres + pgvector · Anthropic Claude (via `app/core/llm/` gateway) · sentence-transformers (bge-small-en-v1.5, 384-dim) · Object storage (Cloudflare R2 or local filesystem). See `../development_docs/Tech_Stack.md`.

---

## Local setup

### 1. Clone & create virtualenv

```bash
git clone <repo-url>
cd backend
python3.13 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Neon Postgres — `postgresql+psycopg://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require` |
| `ANTHROPIC_API_KEY` | Yes | `sk-ant-…` |
| `OBJECT_STORAGE_ENDPOINT` | No | Omit to use local filesystem storage (dev only) |
| `OBJECT_STORAGE_BUCKET` | No | Required if endpoint set |
| `OBJECT_STORAGE_ACCESS_KEY` | No | Required if endpoint set |
| `OBJECT_STORAGE_SECRET_KEY` | No | Required if endpoint set |
| `EMBEDDING_MODEL` | No | Defaults to `BAAI/bge-small-en-v1.5` |
| `LLM_TIER_OVERRIDE` | No | Force a single model for all LLM calls (e.g. `claude-haiku-4-5-20251001` during dev) |
| `ENV` | No | `dev` (DEBUG logging) or `prod` (INFO logging). Defaults to `dev`. |

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Seed playbooks

```bash
python scripts/seed_playbooks.py
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","db":true,"embedding_model":true,"storage":true}
```

---

## Running tests

```bash
pytest                        # all tests
pytest tests/unit/            # unit tests only
pytest tests/integration/     # integration tests only
pytest -q --tb=short          # quiet mode
```

---

## Linting & type checking

```bash
ruff check app tests          # lint
ruff check --fix app tests    # auto-fix safe issues
mypy app                      # type check
```

---

## Database migrations

```bash
alembic upgrade head          # apply all migrations
alembic downgrade -1          # roll back one migration
alembic revision --autogenerate -m "description"   # generate new migration
```

Migration files live in `migrations/versions/`. They are serialized (001–009); do not create parallel branches.

---

## Directory structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app factory; auto-discovers routers
│   ├── api/
│   │   ├── errors.py            # AppError + FastAPI error handlers
│   │   └── routes/              # One file per service (auto-registered)
│   ├── core/
│   │   ├── config.py            # Pydantic-settings Settings
│   │   ├── diff/                # Clause aligner + char-level differ
│   │   ├── embeddings.py        # sentence-transformers singleton
│   │   ├── llm/                 # Gateway, registry, schemas, prompts
│   │   └── storage.py           # S3/R2 + filesystem backends
│   ├── db/
│   │   ├── base.py              # Engine, session factory, Base
│   │   ├── models/              # SQLAlchemy ORM models
│   │   └── repositories/        # Async query functions
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic (one dir per service)
│   │   ├── document_processing/ # S1: parse, segment, extract metadata
│   │   ├── contract_analysis/   # S2: flag detection + risk scoring
│   │   ├── redline/             # S3: LLM redlines + render + persist
│   │   ├── playbook/            # S6: playbook rules + routing
│   │   ├── repository/          # S7: contract repo + vector search
│   │   ├── drafting/            # S4: clause/document drafting
│   │   ├── intelligence/        # S5: summarize, Q&A, navigation
│   │   ├── obligations/         # S8: extract, monitor, renewal
│   │   └── analytics/           # S9: SQL-view reads (no LLM)
│   └── workflows/               # Orchestration: review pipeline, gate, version diff
├── db/
│   └── views.sql                # Analytics views reference SQL (managed by migration 009)
├── migrations/                  # Alembic migration chain (001–009)
├── scripts/
│   ├── seed_playbooks.py        # Load default playbook rules
│   └── run_monitor.py           # Cron entrypoint: daily obligation monitor
├── tests/
│   ├── conftest.py              # Base fixtures (env, client, fake_llm)
│   ├── fake_llm.py              # FakeLLMGateway (no network)
│   ├── unit/                    # Per-service unit tests (~560 tests)
│   └── integration/             # E2E + determinism tests
└── pyproject.toml
```

---

## Architecture rules

- **LLM isolation:** All Anthropic calls go through `app/core/llm/gateway.py`. No service outside `app/core/llm/` imports `anthropic`.
- **S1 and S9 are LLM-free:** `document_processing` and `analytics` are deterministic — they never import `core/llm`.
- **Char offsets are sacred:** `char_start`/`char_end` and `clause_type` are computed once in S1 and carried downstream — never recomputed.
- **Session discipline:** Services `flush()`; routes `commit()`.
- **Router auto-discovery:** `main.py` discovers all routers via `pkgutil.iter_modules` on `app/api/routes/` — drop a file with a `router` attribute to register it; no edits to `main.py` needed.
