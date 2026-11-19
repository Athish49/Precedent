# Precedent — Backend

Python + FastAPI backend for the Precedent contract-intelligence platform.

**Before writing any code, read `../development_docs/`** — start with `00_README.md`, then build from `Implementation_Plan_Backend.md` (task by task). This directory's structure is defined in `../development_docs/Backend_Structure.md`.

---

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2 (async) + Alembic · Neon Postgres + pgvector · Anthropic Claude (via `app/core/llm/` gateway) · Extend AI (via `app/core/extend/` client — document parsing + field extraction, replacing the old local `pdfplumber`/`python-docx`/spaCy pipeline) · sentence-transformers (bge-small-en-v1.5, 384-dim) · Object storage (Cloudflare R2 or any S3-compatible bucket; required, no local mode). See `../development_docs/Tech_Stack.md`.

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
| `EXTEND_API_KEY` | Yes | Extend AI key. Required for S1 (document processing) ingest — a Parse + Extract call runs on every upload. Never log this key |
| `OWN_ORG_NAMES` | No | Comma-separated names the organization signs under, used to tell our party apart from the counterparty at ingest. Defaults to empty, in which case no party role is guessed |
| `PROJECT_NAMESPACE` | No | Namespace for everything this project owns on shared infrastructure. Defaults to `precedent` |
| `DB_SCHEMA` | No | Postgres schema. Defaults to the namespace. Must match `^[a-z][a-z0-9_]*$` and must not be `public` |
| `OBJECT_STORAGE_PREFIX` | No | Key prefix inside the bucket. Defaults to the namespace |
| `OBJECT_STORAGE_ENDPOINT` | Yes | S3-compatible endpoint, e.g. `https://<account-id>.r2.cloudflarestorage.com` |
| `OBJECT_STORAGE_BUCKET` | Yes | Bucket name |
| `OBJECT_STORAGE_ACCESS_KEY` | Yes | Access key ID |
| `OBJECT_STORAGE_SECRET_KEY` | Yes | Secret access key |
| `EMBEDDING_MODEL` | No | Defaults to `BAAI/bge-small-en-v1.5` |
| `LLM_TIER_OVERRIDE` | No | Force a single model for all LLM calls (e.g. `claude-haiku-4-5-20251001` during dev) |
| `ENV` | No | `dev` (DEBUG logging) or `prod` (INFO logging). Defaults to `dev`. |

**Cloud storage is required.** There is no local development mode for storage: the application has one storage backend, the S3-compatible one, and refuses to start if any of the four `OBJECT_STORAGE_*` values is missing or blank. Nothing is written to the local filesystem.

**Shared accounts.** The database and the storage account are shared with other projects. `PROJECT_NAMESPACE` keeps this project's data apart: the storage backend prepends `<prefix>/` to every object key (callers and the `object_key` columns use logical keys such as `contracts/{id}/{filename}`), and the same name is the project's Postgres schema.

Tests need no cloud access. `tests/conftest.py` supplies placeholder storage settings and replaces the storage backend with the in-memory double in `tests/in_memory_storage.py`.

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Seed playbooks (optional)

The application works with no playbook data loaded: every feature handles
empty playbook, role and policy tables without error. Seeding only loads
synthetic demonstration content (Halcyon Care, Inc., a fictional company —
see `seed/README.md`), which is useful for trying the product end to end but
is never required to start or run the application.

```bash
cd backend
.venv/bin/python -m seed.playbooks.load --dry-run   # validate and preview counts, no database writes
.venv/bin/python -m seed.playbooks.load              # load it for real
```

See `seed/README.md` for the full set of seed commands (validate, load,
report) and the isolation rules that keep `backend/seed/` deletable without
affecting the application.

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

Migration files live in `migrations/versions/`. They are serialized (001–015); do not create parallel branches.

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
│   │   ├── extend/              # Extend AI client (S1 ingest): upload, Extract (poll), fetch Parse blocks
│   │   ├── llm/                 # Gateway, registry, schemas, prompts
│   │   └── storage.py           # S3/R2 backend (cloud only), project key prefix
│   ├── db/
│   │   ├── base.py              # Engine, session factory, Base
│   │   ├── models/              # SQLAlchemy ORM models
│   │   └── repositories/        # Async query functions
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic (one dir per service)
│   │   ├── document_processing/ # S1: Extend Parse+Extract, then our own canonical text/segmentation/typing/field mapping (ingest.py). The old pipeline (parsers.py/segmentation.py/clause_types.py/extraction.py/service.py) has been deleted.
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
├── migrations/                  # Alembic migration chain (001–015)
├── scripts/                     # Operational scripts only (not seed code)
│   └── run_monitor.py           # Cron entrypoint: daily obligation monitor
├── seed/                        # Optional demonstration data + its loaders; see seed/README.md
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
- **S9 is LLM-free; S1 is not, but it's not our LLM gateway either.** `analytics` is deterministic and never imports `core/llm`. `document_processing` also never imports `core/llm` — but it does call Extend AI (`core/extend/`) on every upload for Parse and Extract, which is a model behind an API. The commitment is not "no model calls" but that each file version is processed once, with pinned Extend processor versions, and the raw responses are stored; nothing downstream regenerates text or offsets. Only `document_processing/` imports `core/extend`, and the string `api.extend.ai` appears only inside `core/extend/` — both guarded in CI the same way as the `core/llm` guard.
- **Char offsets are sacred:** `char_start`/`char_end` and `clause_type` are computed once in S1 and carried downstream — never recomputed.
- **Session discipline:** Services `flush()`; routes `commit()`.
- **Router auto-discovery:** `main.py` discovers all routers via `pkgutil.iter_modules` on `app/api/routes/` — drop a file with a `router` attribute to register it; no edits to `main.py` needed.
