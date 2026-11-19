# Implementation Plan — Precedent Backend

## Document reading order

Read these docs in order before building. Each one is a prerequisite for the next:

1. **PRD.md** — vision, feature suites, functional requirements, scope boundaries, success criteria.
2. **Architecture.md** — the 9 services + cross-cutting workflows as diagrams, with per-service purpose and integrations.
3. **Tech_Stack.md** — chosen technologies, LLM gateway, embeddings, deployment targets, and conventions.
4. **Data_Model.md** — the single Neon Postgres schema: tables, columns, relationships, Pydantic models.
5. **API_Spec.md** — every REST endpoint, grouped by service, with request/response shapes.
6. **Backend_Structure.md** — the folder/file layout inside `backend/`, module conventions, where each kind of code lives.
7. **This file (Implementation_Plan_Backend.md)** — the granular, dependency-ordered task backlog. Pick any task whose dependencies are met and execute it.

---

This is the build backlog. It is written so you can **pick any task whose dependencies are done and execute it without further context**, resume after a cleared session, or run **multiple tasks in parallel** (across agents) when their dependencies don't overlap.

## How to use this plan

- **Each task is self-contained.** It names its service, dependencies (by task ID), the files it creates/changes (paths from Backend_Structure.md), a spec of what to build (grounded in the other docs), and acceptance criteria.
- **To start work:** find the lowest-numbered task whose dependencies are all `[x]` done, or any unblocked task in a phase you want to parallelize. Read the referenced sections of PRD/Architecture/Tech_Stack/Data_Model/API_Spec, then build.
- **To parallelize:** tasks with disjoint file sets and satisfied dependencies can run simultaneously. Phases are ordered, but within a phase many tasks are independent (noted).
- **Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done. Update the checkbox when you finish. Keep this file as the shared source of truth of progress.
- **Definition of done for every task:** code + unit tests pass, `ruff` + `mypy` clean, and (if it adds an endpoint) it's registered and returns the documented shape. Deterministic modules include a determinism test.
- **Never** call the Anthropic SDK outside `core/llm/`. **Never** regenerate `char_start/end` or `clause_type` downstream.

### Parallel execution (avoiding hotspot collisions)

The plan advertises parallelizable tracks. To make concurrent agents actually safe, the codebase avoids single-file hotspots (see Backend_Structure §4 "Parallel-safe by construction"). Three rules bind here:

1. **Routers auto-discover** — API tasks add a route file under `app/api/routes/`; **no task edits `main.py`**. "Register router" below means "drop the file; it is auto-included."
2. **LLM schemas are per-service** (`core/llm/schemas/<service>.py`), so schema-adding tasks never touch a shared file.
3. **Migrations are serialized, not parallel-authored.** The migration-creating tasks are **T-003, T-035, T-045, T-080, T-084**. Do **not** run these concurrently — parallel Alembic autogenerate branches the revision chain. Either run them one at a time (each sets `down_revision` to the current head) or fold their table DDL into T-003's initial schema. All *other* tasks add views/seed/data/models-without-migration and are freely parallel.

Everything else with disjoint file sets and satisfied dependencies is parallel-safe.

Task ID format: `T-0XX`. Dependencies list is exhaustive (transitive deps not repeated).

---

## Phase 0 — Foundations (must be first)

- [ ] **T-001 · Repo scaffolding & tooling** · deps: none
  - Create the `backend/` tree skeleton per Backend_Structure.md §2 (empty packages with `__init__.py`, `app/main.py` app factory, `app/api/routes/health.py` returning `{status:"ok"}`).
  - `pyproject.toml`/`requirements.txt` with deps (Tech_Stack §11), `ruff`+`mypy`+`pytest` config, `tests/conftest.py` stub, `backend/README.md` skeleton.
  - **Accept:** `uvicorn app.main:app` boots; `GET /api/health` → 200; `ruff`/`mypy`/`pytest` run clean on the empty tree.

- [ ] **T-002 · Settings & config** · deps: T-001
  - `app/core/config.py` (`pydantic-settings` typed `Settings`), `.env.example` with every var (Tech_Stack §10). `app/core/logging.py`.
  - **Accept:** Settings loads from env; missing required var raises a clear error; `.env.example` documents all vars.

- [ ] **T-003 · DB base, engine, first migration** · deps: T-002
  - `app/db/base.py` (async SQLAlchemy engine from `DATABASE_URL`, session factory, `Base`). Alembic init under `migrations/`.
  - First migration: `CREATE EXTENSION IF NOT EXISTS vector;` + tables `party`, `contract`, `contract_metadata`, `clause`, `contract_version`, `clause_embedding` (Data_Model §2–3) with indexes (full-text GIN, pgvector HNSW).
  - `app/db/models/contract.py`, `clause.py` ORM classes for these tables.
  - **Accept:** `alembic upgrade head` builds the schema on a Neon/local Postgres; models import cleanly; health check pings DB.

---

## Phase 1 — Shared infrastructure (mostly parallel after T-003)

- [ ] **T-010 · Object storage wrapper** · deps: T-002
  - `app/core/storage.py`: interface `put(key, bytes)`, `get(key)`, `presign(key)`; S3/R2 impl (boto3) + filesystem impl (dev), selected by env.
  - **Accept:** round-trip put/get works against local fs and (if configured) R2; no other module imports boto3.

- [ ] **T-011 · Embeddings module** · deps: T-002
  - `app/core/embeddings.py`: load sentence-transformers model (`EMBEDDING_MODEL`, default `bge-small-en-v1.5`, 384-dim) as a singleton; `embed(texts) -> list[vector]`; runs in threadpool. (Tech_Stack §5.)
  - **Accept:** deterministic — same input → identical vector; dimension is 384 everywhere.

- [ ] **T-012 · LLM gateway core** · deps: T-002
  - `app/core/llm/gateway.py` (`call_structured`, `call_text`), `registry.py` (task→model tier, env override), `schemas/` directory (empty package, one module per service added by later tasks), `prompts/` dir. Anthropic client init; structured output via `messages.parse()` + Pydantic; refusal/`None` → raise `LLMError`; usage logging; prompt-cache support for a `cache_prefix`. (Tech_Stack §4.)
  - **Fake gateway** for tests: `tests/conftest.py` fixture returning canned schema instances (no network).
  - **Accept:** a sample `call_structured` against a trivial schema returns a validated object with the fake gateway; `import anthropic` appears only in `core/llm/`.

- [ ] **T-013 · LLM batch helper** · deps: T-012
  - `call_batch` in gateway using the Message Batches API (poll to completion, key by custom_id). (Tech_Stack §4.6.)
  - **Accept:** batched structured calls return validated objects keyed to inputs (tested with fake gateway).

- [ ] **T-014 · Shared diff engine** · deps: T-001
  - `app/core/diff/aligner.py` (align clause lists by stable `clause_id`, robust to insert/delete/reorder) + `differ.py` (char-level diff → tracked-changes change set with offsets). (Tech_Stack §7.)
  - **Accept:** determinism tests; reordered/inserted clauses produce localized changes, not one giant delta.

- [ ] **T-015 · Error envelope & common schemas** · deps: T-001
  - `app/api/errors.py` (envelope `{error:{code,message,detail}}` + FastAPI exception handlers), `app/schemas/common.py` (pagination, error models).
  - **Accept:** raised domain errors render the envelope with correct status codes.

---

## Phase 2 — S1 Document Processing (foundation for all review features)

**Superseded (2026-11-18).** T-020 through T-025 described the original local-parsing design (`pdfplumber`/`python-docx` parsing, spaCy NER + regex metadata, a synchronous `process()` call) and are no longer the plan. That design is replaced end to end by `document_processing_plan.md` (Extend AI Parse + Extract, our own canonical-text builder/segmenter/clause typer/field mapper, async ingest with `202` + polling, the schema in plan §7). The task breakdown that actually ran is `document_processing_implementation.md` phases 0–3 (tasks 0.1–0.3, 1.1–1.3, 2.1–2.9, 3.1–3.6), which is done as of this writing; phase 5 (deleting the five files these tasks named) has not yet run. Do not pick up T-020 to T-025 as written below; they are kept only for history.

- [ ] ~~**T-020 · Parsers** · deps: T-003~~ — superseded, see above.
  - `services/document_processing/parsers.py`: `pdfplumber` (text + font/bold/coords/whitespace) and `python-docx` (heading styles + numbering) → a common `canonical_text` + structure signal. Digital PDFs only. (Architecture Diagram 2; Tech_Stack §6.)
  - **Accept:** both formats yield identical canonical-text contract for the same logical doc; offsets are into canonical text.

- [ ] ~~**T-021 · Segmentation** · deps: T-020~~ — superseded, see above.
  - `segmentation.py`: multi-scheme heading detection (decimal `1.1`, alpha `(a)`, roman `iv.`, ALL CAPS, bold) with blank-line fallback; clause boundaries → clause array with `char_start/char_end`.
  - **Accept:** determinism test; unstructured letter agreements fall back gracefully.

- [ ] ~~**T-022 · Clause-type normalizer** · deps: T-021~~ — superseded, see above.
  - `clause_types.py`: synonym/fuzzy dictionary (`rapidfuzz`) mapping heading text → canonical `clause_type` (e.g. "Hold Harmless"→`indemnification`). No LLM. Vocabulary aligned with S6 taxonomy.
  - **Accept:** covers a documented set of canonical types; deterministic; unknown headings map to `other`.

- [ ] ~~**T-023 · Metadata extraction + counterparty** · deps: T-020~~ — superseded, see above.
  - `extraction.py`: spaCy NER (PERSON/ORG) + regex (dates, financials, governing law, notice blocks) → the ~50-field metadata object; normalized `counterparty_id` (upsert `party` with dedupe). No LLM.
  - **Accept:** promoted fields + `extracted` jsonb populated; party dedupe ("Acme Inc."≈"Acme, Inc.").

- [ ] ~~**T-024 · S1 service + persistence** · deps: T-021, T-022, T-023, T-010~~ — superseded, see above.
  - `service.py::process(file, paper_origin) -> ProcessedContract`: parse → segment → type → extract → put bytes to storage → persist `contract`, `clause[]`, `contract_metadata`, `party`. Emits the `ProcessedContract` DTO.
  - **Accept:** SC-1 — a PDF/DOCX processes end-to-end with zero LLM calls; rows persisted; offsets preserved.

- [ ] ~~**T-025 · S1 API** · deps: T-024, T-015~~ — superseded, see above.
  - `api/routes/documents.py`: the four S1 endpoints (API_Spec §S1). Register router.
  - **Accept:** upload returns `ProcessedContract`; clause/text/metadata GETs work; tests via fixtures.

---

## Phase 3 — S7 Repository/Search + S6 Playbook (parallelizable: S7 track and S6 track are independent)

### S7 track
- [ ] **T-030 · Repositories (contract/clause/search)** · deps: T-003
  - `db/repositories/contract_repo.py`, `clause_repo.py`, `search_repo.py` (faceted filter + `tsvector` full-text).
  - **Accept:** faceted list + keyword search return correct rows; determinism.

- [ ] **T-031 · Vector: embed-on-write + precedent search** · deps: T-024, T-011, T-030
  - The embedding code lives in **S7** (`services/repository/vector.py`) — S1 ingest *calls* it; the embedding logic is not placed in the S1 package. `vector.py` computes + stores `clause_embedding` (via `core/embeddings`) at ingest, and does pgvector cosine search optionally scoped by `clause_type`. Expose `/api/repository/precedent-search`.
  - **Accept:** embeddings written at ingest; ANN search returns nearest clauses.

- [ ] **T-032 · Versioning** · deps: T-003, T-010
  - `services/repository/service.py` version store/list + parent-child (`contract_version`). Endpoints in API_Spec §S7.
  - **Accept:** store new version increments number, links parent; list returns lineage.

- [ ] **T-033 · Smart Search** · deps: T-030, T-031, T-012
  - `smart_search.py`: one LLM call (schema `SmartSearchFilters` in `core/llm/schemas.py`, prompt `smart_search_filters.md`) → structured filters + optional semantic query; execute faceted + (if present) vector; merge deterministically.
  - **Accept:** "auto-renew + 30-day notice" → facets; "contracts about IP indemnification" → semantic; single LLM call.

- [ ] **T-034 · S7 API** · deps: T-030, T-031, T-032, T-033, T-015
  - `api/routes/repository.py` — all §S7 endpoints. Register.
  - **Accept:** endpoints return documented shapes; tests.

### S6 track
- [ ] **T-035 · Playbook models + repo** · deps: T-003
  - `db/models/playbook.py` (`playbook`, `playbook_rule`) + migration; `db/repositories/playbook_repo.py`.
  - **Accept:** schema migrates; repo CRUD works.

- [ ] **T-036 · S6 CRUD service + routes** · deps: T-035, T-015
  - `services/playbook/service.py` CRUD; `api/routes/playbooks.py` CRUD endpoints (API_Spec §S6).
  - **Accept:** self-service CRUD over playbooks/rules works.

- [ ] **T-037 · Routing & resolve** · deps: T-036
  - `routing.py`: practice-area routing selecting **all** applicable rule-sets merged by precedence; `resolve(contract_type)`; `/api/playbooks/resolve`. Deterministic.
  - **Accept:** overlapping regimes (SaaS+GDPR+HIPAA) merge by precedence into one type-keyed rule set.

- [ ] **T-038 · Bootstrap (batch LLM)** · deps: T-037, T-013, T-031
  - `bootstrap.py`: batch LLM over a corpus (schema `PlaybookBootstrapOut`, prompt `playbook_bootstrap.md`) → seed **preferred language + acceptable variations only**; `/api/playbooks/bootstrap`. Prohibited terms come from seed, not this job.
  - **Accept:** SC-3 (bootstrap half) — corpus yields rules; prohibited terms not mined from executed contracts.

- [ ] **T-039 · Seed playbooks** · deps: T-035
  - `scripts/seed_playbooks.py`: pre-built templates (NDA, DPA, SaaS MSA, HIPAA, GDPR) with default prohibited terms + base rules + risk weights.
  - **Accept:** running the script populates baseline playbooks used by S2/S3.

---

## Phase 4 — S2 Analysis + S3 Redline (core review)

- [ ] **T-040 · S2 Layer 1 structural** · deps: T-024, T-037
  - `services/contract_analysis/layer1_structural.py`: missing-clause (clause-type list vs required) + prohibited-term (vs playbook prohibited) — deterministic.
  - **Accept:** missing/prohibited flags produced with no LLM.

- [ ] **T-041 · Clause↔rule matcher** · deps: T-040
  - `rule_matcher.py`: attach the type-matching playbook rule(s) to each clause (deterministic) to shrink LLM prompts.
  - **Accept:** each clause carries only its relevant rule(s).

- [ ] **T-042 · S2 Layer 2 content (LLM)** · deps: T-041, T-012
  - `layer2_content.py`: batched LLM call, mode by `paper_origin` (own → non-standard/high-risk/vague + confirm inconsistent; counterparty → deviation vs preferred **plus** high-risk/vague). Schemas + prompts `analysis_own_paper.md`/`analysis_counterparty.md`. Regex pre-filter for inconsistent-term candidates.
  - **Accept:** counterparty path also flags dangerous-but-not-in-playbook language; 1 batched call per contract.

- [ ] **T-043 · S2 scoring** · deps: T-042, T-039
  - `scoring.py`: severity-weighted risk from flags using weights from playbook config; persist `risk_score` incl. `max_clause_severity`. (FR-4.)
  - **Accept:** severity-weighted (not averaged); weights sourced from S6; `max_clause_severity` recorded for the gate.

- [ ] **T-044 · S2 service + persistence + API** · deps: T-043, T-030, T-015
  - `service.py::analyze()` wiring; persist `flag`; `api/routes/analysis.py` (§S2).
  - **Accept:** analysis endpoint returns `AnalysisResult`; flags carry citations; tests with fake gateway.

- [ ] **T-045 · NMS models + repo + pattern view** · deps: T-003
  - `db/models/nms.py` (`decision_event`) + migration; `nms_repo.py`; `counterparty_pattern` SQL view (Data_Model §7).
  - **Accept:** append-only writes; pattern view returns accept-rate + last-closed text per (counterparty, clause_type).

- [ ] **T-046 · S3 stance filter + NMS context** · deps: T-045, T-044
  - `services/redline/stance.py`: deterministic stance-mode filter (Light/Balanced/Firm) + deterministic NMS stance context (accept/reject stats × stance).
  - **Accept:** correct clauses queued per stance; NMS context assembled deterministically.

- [ ] **T-047 · S3 main LLM call** · deps: T-046, T-012
  - Bundled structured call (schema `RedlineOut`: replacement text + 2–3 alternatives + explanation + counterparty comment; prompt `redline_generate.md`), stance baked in, playbook preferred language + NMS context injected (cache the playbook prefix).
  - **Accept:** one LLM call per clause (or batched for low-risk); no stance-recommendation second call.

- [ ] **T-048 · S3 render (diff) + non-interference** · deps: T-047, T-014
  - `render.py`: turn `replacement_text` into surgical `tracked_changes` via `core/diff`; non-interference check (changed spans ⊆ flagged set). No 4-dim self-grade.
  - **Accept:** tracked changes are character-accurate; non-interference asserted deterministically.

- [ ] **T-049 · S3 rationale + persistence + NMS write** · deps: T-048, T-045
  - Assemble deterministic `rationale` (playbook position + LLM output, no extra call); persist `redline`; write `decision_event` (outcome pending).
  - **Accept:** redline row complete; NMS event created.

- [ ] **T-050 · S3 fallback/refine/decision** · deps: T-049
  - Deterministic fallback toggle (swap → re-diff); multi-pass refine (LLM `redline_refine.md` → re-diff); decision endpoint (updates status + appends NMS outcome + final_text).
  - **Accept:** toggle/refine/decision behave per API_Spec §S3.

- [ ] **T-051 · S3 API** · deps: T-049, T-050, T-015
  - `api/routes/redlines.py` (§S3). Register.
  - **Accept:** SC-2 (redline half) — flagged clauses → redlines with rationale + citations.

---

## Phase 5 — Orchestration (Review Pipeline + Gate)

- [ ] **T-060 · Review pipeline** · deps: T-024, T-037, T-044, T-051
  - `workflows/review_pipeline.py`: code-orchestrated S1(parse) ∥ S6(fetch) → S2 → S3. Concurrency for S1/S6. No LLM controls flow.
  - **Accept:** running the pipeline on a contract produces flags + redlines in order.

- [ ] **T-061 · Threshold gate** · deps: T-060, T-045
  - `workflows/gate.py`: deterministic hard-stops (any prohibited/missing flag, non-interference failure, or `max_clause_severity` high → escalate) else auto-apply if aggregate + max below threshold. Persist `review_run` with `gate_reason`. (FR-5.)
  - **Accept:** a single toxic clause forces escalation even with low average; decision + reason recorded.

- [ ] **T-062 · Review API** · deps: T-061, T-015
  - `api/routes/review.py`: `/run`, `/runs/{id}`, `/webhook` (§Review). Webhook enqueues a run (the autonomous trigger).
  - **Accept:** SC-2 — end-to-end review returns gate decision + redlines/escalation; tests.

---

## Phase 6 — S4 Drafting + S5 Intelligence (parallelizable tracks)

### S4 track
- [ ] **T-070 · Frequency tracker** · deps: T-030
  - `services/drafting/frequency_tracker.py`: deterministic metadata-scoped last-N aggregation over S7 (most common version of a clause type for this deal context), threshold + unscoped fallback.
  - **Accept:** returns the most common relevant clause version; deterministic.

- [ ] **T-071 · S4 cascade service** · deps: T-070, T-037, T-031, T-012
  - `service.py`: branch on mode first; single-clause cascade (playbook → frequency → LLM rewrite/novel); document (template engine + optional on-demand polish); precedent (vector → style-matched LLM `drafting_precedent.md`); memo (`drafting_memo.md`). Schemas/prompts as needed.
  - **Accept:** LLM only when playbook+frequency miss; source tag returned.

- [ ] **T-072 · S4 API** · deps: T-071, T-015
  - `api/routes/drafting.py` (§S4).
  - **Accept:** endpoints return drafted text + source; tests.

### S5 track
- [ ] **T-073 · S5 navigation** · deps: T-024
  - `services/intelligence/navigation.py`: deterministic clause-navigation index from clause types.
  - **Accept:** no LLM; index links clause types → clauses.

- [ ] **T-074 · S5 summaries** · deps: T-044, T-012
  - Risk-aware summarize (grounded on S1 metadata + S2 flags; prompt `summarize.md`) + redline-thread summarize (`summarize_redlines.md`).
  - **Accept:** summary highlights risk (e.g. uncapped indemnity); one LLM call each.

- [ ] **T-075 · S5 Q&A** · deps: T-024, T-012
  - Q&A: load S1 clause array as context (no vector), LLM answer + char-level citations (`qa_answer.md`); persist `qa_cache` (unique per contract+question).
  - **Accept:** SC-4 — cited answer over current doc without a vector index; cached.

- [ ] **T-076 · S5 easy-prompt/research + API** · deps: T-075, T-074, T-073, T-015
  - Easy Prompt (`easy_prompt.md`) returning `{structured_prompt, route}`; Chat2 Research (web search + `research_synthesize.md`); `api/routes/intelligence.py` (§S5).
  - **Accept:** easy-prompt routes downstream (doesn't dead-end); research returns cited answer; tests.

---

## Phase 7 — S8 Obligations + S9 Analytics (parallelizable tracks)

### S8 track
- [ ] **T-080 · Obligation extraction** · deps: T-024, T-012
  - `db/models/obligation.py` (`obligation`, `alert`) + migration; `service.py::extract()` LLM grounded on S1 metadata (schema `ObligationOut`, prompt `obligation_extract.md`) → persist obligations with citations.
  - **Accept:** SC-5 (extract half) — obligations with owner/deadline/deliverable + offsets.

- [ ] **T-081 · Monitor (daily pass)** · deps: T-080
  - `monitor.py`: single deterministic pass (deadline within threshold + renewal window 30–90d) → `alert`; `scripts/run_monitor.py` entrypoint for cron.
  - **Accept:** one pass fires deadline + renewal alerts deterministically.

- [ ] **T-082 · Renewal-rec + compliance** · deps: T-081, T-042
  - Bundled LLM (renewal recommendation + compliance verification in one call, reusing S2 deviation rubric; prompt `renewal_compliance.md`); on-demand compliance endpoint.
  - **Accept:** renewal path is one bundled LLM call; on-demand compliance returns pass/fail + issues.

- [ ] **T-083 · S8 API** · deps: T-082, T-015
  - `api/routes/obligations.py` (§S8).
  - **Accept:** SC-5 — extract/monitor/compliance/alerts endpoints; tests.

### S9 track
- [ ] **T-084 · Analytics views** · deps: T-044, T-080
  - `db/views.sql` + migration: `v_contract_intelligence`, `v_portfolio_risk` (severity-weighted, not average), `v_contract_value`, `v_tabular_review` (+ qa_cache columns), `v_renewal_dashboard`.
  - **Accept:** views return correct roll-ups; portfolio risk is severity-weighted.

- [ ] **T-085 · S9 service + API** · deps: T-084, T-015
  - `services/analytics/service.py` reads over views; `api/routes/analytics.py` (§S9). No LLM (guard: S9 never imports `core/llm`).
  - **Accept:** SC-6 — all analytics endpoints; determinism.

---

## Phase 8 — Cross-cutting & closeout

- [ ] **T-090 · Version comparison workflow + API** · deps: T-032, T-014
  - `workflows/version_comparison.py`: fetch two versions → align by clause id → char diff → change set; `api/routes/versions.py` `/diff`.
  - **Accept:** SC-7 — clause-aligned tracked changes; same diff engine as S3.

- [ ] **T-091 · Version semantic summary (optional LLM)** · deps: T-090, T-012
  - `/diff/summary`: optional LLM semantic-change summary (`version_semantic_summary.md`) over the change set.
  - **Accept:** on-demand; not on the default diff path.

- [ ] **T-092 · Integration & determinism tests** · deps: all service phases
  - `tests/integration/`: end-to-end review (upload → review/run → gate → redlines); determinism tests for S1 (same doc → same clauses/offsets) and S9 (same data → same rollups). Fake gateway for LLM steps.
  - **Accept:** SC-8 — suite green; deterministic services proven stable.

- [ ] **T-093 · CI guards** · deps: T-001
  - CI runs `ruff`, `mypy`, `pytest`, plus a grep guard asserting `import anthropic` appears only under `app/core/llm/` and that `app/services/document_processing` and `app/services/analytics` never import `core/llm`.
  - **Accept:** guards fail the build on violation.

- [ ] **T-094 · Run docs & health** · deps: T-002, T-011, T-003
  - Finalize `backend/README.md` (local run steps, Backend_Structure §5), `.env.example` completeness, and `GET /api/health` reporting DB + embedding-model + storage status.
  - **Accept:** a fresh clone can be brought up from README alone.

---

## Dependency quick-map (for parallelization)

- **Critical path:** T-001 → T-002 → T-003 → T-020..T-024 (S1, superseded — see Phase 2 note; the equivalent foundation is `document_processing_implementation.md` phases 0–3) → then S7/S6 → S2 → S3 → Review Pipeline.
- **Independent early tracks (after T-003):** T-010, T-011, T-012, T-014, T-015 can all proceed in parallel.
- **Independent mid tracks:** S6 (T-035–T-039) is independent of S7 (T-030–T-034); S4 (T-070–T-072) independent of S5 (T-073–T-076); S8 (T-080–T-083) independent of S9 (T-084–T-085).
- **Convergence points:** Review Pipeline (T-060) needs S1+S6+S2+S3; Analytics views (T-084) need S2+S8.

Every task above traces to a PRD success criterion or functional requirement and to an Architecture diagram — when in doubt, re-read that service's section before building.
