# Tech Stack & External Dependencies — Precedent Backend

This document is authoritative for every technology choice and every external-service integration convention. When a task in Implementation_Plan_Backend.md says "use the LLM gateway" or "store the embedding," the mechanics are defined here.

## 1. Language & framework

- **Python 3.12+**, **FastAPI** for the HTTP layer, **Uvicorn** ASGI server.
- **Pydantic v2** for all request/response models, LLM structured outputs, and domain models.
- **SQLAlchemy 2.x** (typed, `Mapped[...]`) ORM + **Alembic** for migrations.
- **pytest** for tests; **ruff** for lint/format; **mypy** for type checking.
- Dependency management: **uv** (preferred) or pip + `requirements.txt`. Pin versions.

Rationale: the deterministic-first design leans heavily on regex and pattern heuristics for everything downstream of ingestion. Document parsing itself (PDF/DOCX) is delegated to Extend AI (§6); the Anthropic SDK, the Extend client and sentence-transformers are all first-class in Python.

## 2. Database — single Neon Postgres

**One** managed Postgres instance (Neon free tier) holds everything:

- Relational metadata (contracts, clauses, playbooks, obligations, versions, NMS event log).
- **Full-text search** via native `tsvector` + GIN indexes (no Elasticsearch/Typesense).
- **Vector search** via the **`pgvector`** extension (no separate Qdrant at portfolio scale; the schema is written so Qdrant can be swapped in later if the corpus grows).
- **Analytics** via SQL views / materialized views (no separate analytics DB).

Connection via `DATABASE_URL` env var. Use a connection pool (SQLAlchemy engine with `pool_pre_ping=True`). Neon suspends idle compute — handle cold-start reconnects.

`pgvector` is enabled with `CREATE EXTENSION IF NOT EXISTS vector;` in the first Alembic migration.

### 2.1 Project schema on a shared database

The Neon account is shared with other projects, and this project's table names are generic (`contract`, `party`, `flag`), so nothing of this project lives in `public`.

- All tables, views and `alembic_version` live in the schema named by `DB_SCHEMA`, which defaults to `PROJECT_NAMESPACE` (`precedent`). The setting must match `^[a-z][a-z0-9_]*$` and must not be `public`.
- `Base` is declared with `MetaData(schema=<db_schema>)`, so every model is schema-qualified in generated SQL.
- The connection goes through Neon's **pooled** endpoint, where a session-level `SET` does not reliably persist between transactions. Runtime code therefore never relies on a session search path.
- Alembic: `migrations/env.py` creates the schema if needed, sets `version_table_schema` and `include_schemas=True`, and runs `SET LOCAL search_path TO <schema>, public` inside the migration transaction. Migrations do not name a schema; `public` stays on the path so the `vector` type resolves.
- Hand-written SQL (the NMS queries, the analytics view queries and the view definitions) names the schema explicitly, built from the setting.
- The `vector` extension stays in `public` and is shared. This project never drops or upgrades it.
- `scripts/check_partition.py` is a read-only check that nothing of this project sits outside its namespace; `assert_namespace()` in `app/core/namespace.py` guards every data-writing script and seed loader.
- No local database of any kind: no SQLite, no local Postgres, no Docker database. Unit tests and CI use a placeholder URL and mocked sessions.

## 3. Object storage — source of truth for documents

Original uploaded files (PDF/DOCX) and generated artifacts are stored in an S3-compatible object store on a free tier:

- **Recommended: Cloudflare R2** (generous free tier, S3 API) or **Supabase Storage**.
- Accessed via `boto3` (S3 client) against the R2 endpoint, or the Supabase client.
- Config: `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_ACCESS_KEY`, `OBJECT_STORAGE_SECRET_KEY` env vars.
- A thin `storage` module wraps put/get/presign; no service touches boto3 directly.
- **Cloud storage is required.** There is one backend, the S3-compatible one, and no filesystem fallback, for development or otherwise. All four `OBJECT_STORAGE_*` settings are required; the application fails at startup when any is missing or blank.
- **Project prefix.** The bucket may be shared with other projects. The backend prepends `{OBJECT_STORAGE_PREFIX}/` (default: the namespace, `precedent/`) to every key on put, get and presign. Callers pass logical keys such as `contracts/{id}/{filename}`, and `object_key` columns store them unprefixed. Absolute keys and keys containing `..` are rejected.
- Files in transit (an upload being parsed) stay in memory. If a library needs a real file it gets a temporary file deleted in the same request.
- Tests use a mocked boto3 client and an `InMemoryStorage` double; nothing is written to disk.

Postgres stores the object key + metadata; the object store holds the bytes. This split is the "single source of truth" from Architecture.md.

## 4. LLM integration — the gateway (FR-6)

**Provider: Anthropic Claude**, via the official `anthropic` Python SDK. **No service imports `anthropic` directly** — all model calls go through `backend/app/core/llm/` (the LLM gateway).

### 4.1 Client
```python
import anthropic
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
```
Config: `ANTHROPIC_API_KEY` env var.

### 4.2 Models & per-task tiering
Model IDs (exact strings — Opus and Sonnet have no date suffix; Haiku 4.5 requires one):

| Tier | Model ID | Use for |
|---|---|---|
| Most capable | `claude-opus-4-8` | Playbook bootstrap (S6), redline generation (S3), obligation extraction (S8) — reasoning-critical |
| Balanced (cost/quality) | `claude-sonnet-4-6` | Contract analysis (S2), summarization/Q&A (S5), drafting (S4) |
| Cheapest/fastest | `claude-haiku-4-5-20251001` | Smart Search NL→filter (S7), Easy Prompt (S5), contract-type classification at upload (S1, only when the type is not supplied), simple classification |

The gateway exposes a **per-task model registry**: each logical LLM task (e.g. `redline.generate`, `analysis.own_paper`, `search.nl_to_filter`) maps to a model tier via config, so the whole system's cost/quality can be tuned from one place and overridden by env (`LLM_TIER_OVERRIDE`). Default the reasoning-critical tasks to `claude-opus-4-8`; the rest to `claude-sonnet-4-6`; trivial translation to `claude-haiku-4-5-20251001`. This is a portfolio project — document the tiering so cost is a visible, deliberate choice.

### 4.3 Structured output (FR-7)
All extraction/flagging/redline calls use **structured outputs** with Pydantic schemas — never free-text parsing:
```python
resp = client.messages.parse(
    model=model_id,
    max_tokens=16000,
    messages=[{"role": "user", "content": prompt}],
    output_format=MyPydanticSchema,   # validated automatically
)
result = resp.parsed_output           # a MyPydanticSchema instance (or None on failure)
```
If `parsed_output` is `None` or `stop_reason == "refusal"`, raise a gateway error; callers must not proceed with malformed data.

### 4.4 Thinking & effort
Claude 4.x uses **adaptive thinking**, not `budget_tokens`. For reasoning-heavy tasks:
```python
thinking={"type": "adaptive"},
output_config={"effort": "high"},   # low | medium | high | max
```
Do **not** send `temperature`, `top_p`, `top_k`, or `budget_tokens` to Opus 4.8 / Sonnet 4.6 — these parameters are unsupported and will cause a 400 error. Follow the SDK conventions. For determinism-sensitive framing, rely on fixed `effort` + tight prompts, and treat outputs as non-deterministic regardless (FR-8).

### 4.5 Prompt caching (cost)
Reused context — the **resolved playbook rules** injected into S2 extraction and per-clause S3 calls, or the **contract text** reused across Q&A turns — should be cached:
```python
system=[{"type": "text", "text": stable_playbook_context,
         "cache_control": {"type": "ephemeral"}}]
```
Keep the cached prefix byte-stable (no timestamps/UUIDs in it). A resolved rule set is stable for a given set of pinned playbook versions, because published versions are immutable; serialise rules in a deterministic order (by `rule_key`). Verify hits via `usage.cache_read_input_tokens`.

### 4.6 Batching (cost)
The S6 playbook bootstrap processes a corpus of agreements — use the **Message Batches API** (50% cheaper, async) for that job rather than N synchronous calls.

### 4.6.1 What the model does and does not decide in playbook review

- S2 Layer 2 is **extraction**: per rule, which position the clause matches, parameter values with a verbatim quote, and a yes/no with a quote for each `semantic` red line. One call per contract; split into clause batches if the prompt exceeds the configured size.
- The zone (green, yellow, red), the score and the gate decision are computed by deterministic code from that output (FR-8, FR-9).
- S3 adapts the playbook's ladder language to the contract's defined terms; it does not invent positions.
- The rule test runner's default mode calls the model once per test case that needs extraction, so it is cost-bearing: it prints the call count and requires an explicit confirmation. Its deterministic mode makes no model call.

### 4.7 Gateway surface
`backend/app/core/llm/gateway.py` exposes typed helpers, e.g.:
- `call_structured(task: str, prompt: str, schema: type[BaseModel], *, cache_prefix: str | None = None) -> BaseModel`
- `call_text(task: str, prompt: str, *, effort: str = "high") -> str`
- `call_batch(task: str, items: list[BatchItem], schema) -> list[BaseModel]`
It handles model selection (per-task registry), retries (SDK auto-retries 429/5xx), refusal handling, and usage logging. Prompts live in `backend/app/core/llm/prompts/` as versioned templates, not inline strings.

## 5. Embeddings — local, deterministic, free

Anthropic has **no embeddings endpoint**. pgvector needs vectors from somewhere. Use a **local sentence-transformers model** — free, runs in-process, deterministic (same input → same vector), consistent with the deterministic-first thesis:

- Model: **`BAAI/bge-small-en-v1.5`** (384-dim) or **`all-MiniLM-L6-v2`** (384-dim). Pick one; keep the dimension fixed across the codebase.
- Library: `sentence-transformers`. Load once at startup (module singleton).
- Embedding is computed **on write** at S7 ingest (see Architecture.md §C4), stored in a `vector(384)` column, and queried with pgvector cosine distance.
- Wrapped by `backend/app/core/embeddings.py`; no service calls sentence-transformers directly.

Note: on free-tier compute, model load adds startup time and memory — acceptable for a portfolio project. If it strains the host, the embeddings module can fall back to a hosted embedding API behind the same interface, but default to local.

## 6. Document processing (Extend AI + our own code, S1)

PDF/DOCX parsing, NER-based party/date extraction and the 34 regex field extractors described in earlier revisions of this document are **removed**. Document processing is now built on **Extend AI** (`https://api.extend.ai`, Light tier): **Parse** rebuilds canonical text (paragraphs, tables, headers/footers, page numbers) from the raw file, and **Extract** returns structured fields with citations and the ordered top-level section list (number, title, family), from one JSON schema generated from our field registry. Both file types (and scanned PDFs, via Extend's OCR) go through the same client.

- **`core/extend/client.py`:** the only module that calls Extend. Built on `httpx` (already a dependency; no Extend SDK is added). Methods: `upload`, `extract` (creates the run, polls to a final state), `parse_output` (fetches Parse blocks by `parseRunId`, no extra charge), `parse` (a standalone Parse-only run for the text-only path used by `store_version`). Errors map to typed exceptions (`ExtendRunFailed`, `ExtendTimeout`, `ExtendUnavailable`, `ExtendAuthError`); 429 and 5xx are retried with backoff. A CI guard restricts the string `api.extend.ai` to this module and restricts the import of `core/extend` to `document_processing/`, the same pattern as the `core/llm` guard.
- **Canonical text, segmentation, clause typing:** all ours, over Extend's output — `document_processing/canonical.py`, `sections.py`, `clause_typing.py`. Extend's clause text is never used for clause boundaries or stored text, only its section list (number/title/family) as a hint for where to cut; character offsets are computed by our own code against the canonical text we build, so they are exact by construction, never a model's byte-for-byte guess.
- **Clause typing** keeps a synonym/fuzzy dictionary (`rapidfuzz` for fuzzy matching, `token_sort_ratio >= 80`), but now as the *fallback*: Extract's family wins first when it is a valid `clause_family` key, then the dictionary, then `other`. The vocabulary is the `clause_family` table (29 families plus `preamble` and `signature_block`), cached at startup.
- **Determinism:** Extend is a model behind an API, so document processing no longer promises bit-identical output for identical input. The replacement rule (`document_processing_plan.md` §3.6): each file version is processed once, with pinned Extend processor versions (`extraction_light` and `parse_light`, both pinned), and the raw Parse/Extract responses are stored in the bucket; nothing downstream regenerates text or offsets. Tests replay recorded Parse/Extract responses — no network call in CI.
- **Deal context:** `regimes` (`hipaa`, `gdpr`) by deterministic keyword rules; `deal_value_band` from the band boundaries in `context_dimension`. No LLM, no Extend.
- **New secret:** `EXTEND_API_KEY`, required for any upload; ingest fails with a clear, retryable status if it is unset or Extend is unavailable.

## 7. Diff engine (deterministic, shared by S3 + Version Comparison)

- Character-level diff via Python `difflib` (or `diff-match-patch` for word-level tracked changes).
- Clauses aligned by stable S1 clause id **before** diffing (robust to insertion/deletion/reorder).
- Lives in `backend/app/core/diff/`; reused by S3 (render redline tracked changes from LLM-produced replacement text) and the Version Comparison workflow.

## 8. Scheduled jobs (S8)

- A **single daily** job (deadline + renewal window checks). On free-tier hosts:
  - **Render Cron Job** (free) or **GitHub Actions scheduled workflow** hitting an internal endpoint, or
  - `APScheduler` in-process if the host stays warm.
- The job logic is deterministic; it may trigger LLM calls (renewal rec + compliance) via the gateway.

## 9. Deployment targets (free tier)

| Concern | Service | Notes |
|---|---|---|
| API host | **Render** (free web service) or Fly.io | FastAPI/Uvicorn; note free hosts sleep when idle |
| Database | **Neon** Postgres + pgvector | `DATABASE_URL`; project schema, not `public` |
| Object storage | **Cloudflare R2** / Supabase Storage | S3-compatible; required in every environment; keys under the project prefix |
| Cron | Render Cron / GitHub Actions | daily monitor |
| Frontend (later) | Vercel | out of scope now |

Everything is 12-factor: config from env, no secrets in code, stateless app processes, DB/object-store as backing services.

## 10. Configuration & secrets

All via environment (loaded with `pydantic-settings` into a typed `Settings` object in `backend/app/core/config.py`):

```
DATABASE_URL=                 # required
ANTHROPIC_API_KEY=
EXTEND_API_KEY=                # required for any document upload (S1 ingest)
OWN_ORG_NAMES=                 # comma-separated names our organization signs under (S1 party-role matching)
PROJECT_NAMESPACE=precedent   # drives the Postgres schema and the object-key prefix
DB_SCHEMA=                    # optional override; defaults to PROJECT_NAMESPACE; never "public"
OBJECT_STORAGE_PREFIX=        # optional override; defaults to PROJECT_NAMESPACE
OBJECT_STORAGE_ENDPOINT=      # required
OBJECT_STORAGE_BUCKET=        # required
OBJECT_STORAGE_ACCESS_KEY=    # required
OBJECT_STORAGE_SECRET_KEY=    # required
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
LLM_TIER_OVERRIDE=            # optional: force all tasks to one model for cost
ENV=dev|prod
```

No auth secrets (no auth). A `.env.example` documents every variable. The application refuses to start if the database URL or any of the four object-storage settings is missing.

## 11. Dependency summary

Core: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector`, `anthropic`, `httpx` (also the Extend client), `sentence-transformers`, `rapidfuzz`, `diff-match-patch`, `boto3`. Dev: `pytest`, `pytest-asyncio`, `httpx` (test client), `ruff`, `mypy`; `python-docx` (the fixture generator). Seed (separate `seed` dependency group, not an application dependency; install with `uv sync --group seed`): `pyyaml`, `python-docx` (the corpus builder).

`pdfplumber`, `spacy` and `en_core_web_sm` are **removed** — they were the old local PDF parser and NER engine, replaced by Extend AI (above). `python-docx` is no longer a runtime dependency of the application; it moved to the `seed` and `dev` groups, which still use it to build and inspect DOCX fixtures.
