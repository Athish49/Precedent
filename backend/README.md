# Precedent — Backend

Python + FastAPI backend for the Precedent contract-intelligence platform.

**Before writing any code, read `../development_docs/`** — start with `00_README.md`, then build from `Implementation_Plan.md` (task by task). This directory's structure is defined in `../development_docs/Backend_Structure.md`.

## Stack
Python 3.12 · FastAPI · SQLAlchemy 2 + Alembic · Neon Postgres (+ pgvector) · Anthropic Claude (via the LLM gateway in `app/core/llm/`) · sentence-transformers embeddings · object storage (R2/S3). See `../development_docs/Tech_Stack.md`.

## Local run (target state — implemented across Phase 0–1 tasks)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: uv sync
cp .env.example .env                      # fill in DATABASE_URL, ANTHROPIC_API_KEY, object-storage keys
alembic upgrade head
python scripts/seed_playbooks.py
uvicorn app.main:app --reload
# GET http://localhost:8000/api/health  -> {"status":"ok", ...}
```

## Layout
`app/api` (thin routers) · `app/services/{document_processing,contract_analysis,redline,drafting,intelligence,playbook,repository,obligations,analytics}` · `app/core` (config, llm gateway, embeddings, storage, diff) · `app/db` (models, repositories, views) · `app/schemas` (Pydantic) · `app/workflows` (review pipeline, gate, version comparison) · `migrations` · `scripts` · `tests`.

## Rules
- LLM calls only through `app/core/llm/` — no service imports `anthropic` directly.
- `document_processing` (S1) and `analytics` (S9) never import `core/llm` (they are deterministic).
- Never regenerate `char_start`/`char_end` or `clause_type` downstream — carry them from S1.
