# API Specification — Precedent Backend

REST over HTTP (FastAPI). JSON in/out. No auth (Non-Goals). Base path `/api`. All IDs are UUIDs. Errors use a consistent envelope: `{"error": {"code": str, "message": str, "detail": any}}` with appropriate HTTP status. Endpoints are grouped by service; each maps to a router in `backend/app/api/routes/` (see Backend_Structure.md).

Notation: request/response bodies are described by their key fields; full shapes are the Pydantic models in Data_Model.md.

## Conventions
- `POST` for actions/creation, `GET` for reads, `PATCH` for partial updates, `DELETE` for removal.
- Long operations (processing, review pipeline, bootstrap) run synchronously for portfolio scale but return a `run_id` where a record is created; a `GET` fetches status/results.
- Pagination: `?limit=&offset=` on list endpoints; responses include `{items, total}`.

---

## S1 — Document Processing  `/api/documents`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | Upload + process a contract. Multipart file + `paper_origin` (own\|counterparty). Deterministic; returns the `ProcessedContract` (contract_id, clauses[], metadata, counterparty_id). Stores bytes in object storage, rows in DB. |
| `GET` | `/api/documents/{contract_id}` | Fetch contract record + metadata. |
| `GET` | `/api/documents/{contract_id}/clauses` | Clause array with `clause_type`, `char_start/end`, text. |
| `GET` | `/api/documents/{contract_id}/text` | Canonical text (for offset resolution / display). |

## S7 — Repository & Search  `/api/repository`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/repository/contracts` | Faceted list: filters `contract_type, counterparty_id, status, effective_date_from/to, value_min/max`. Deterministic. |
| `GET` | `/api/repository/search` | Query params `q` (keyword full-text) or `type=faceted`. Deterministic full-text (`tsvector`) + faceted. |
| `POST` | `/api/repository/smart-search` | Body `{query: str}`. One LLM call → `{filters, semantic_query?}`; executes faceted + optional vector search; returns merged results. |
| `GET` | `/api/repository/contracts/{id}/redline-history` | Prior positions per clause type (from S3/NMS decision log). |
| `GET` | `/api/repository/contracts/{id}/versions` | List versions (parent-child). |
| `POST` | `/api/repository/contracts/{id}/versions` | Store a new version (bytes + relation); increments version_number. |
| `GET` | `/api/repository/precedent-search` | Internal-ish: `?clause_type=&query=` → vector search over `clause_embedding` (used by S4). |

## S6 — Playbook & Rules  `/api/playbooks`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/playbooks` | List playbooks. |
| `POST` | `/api/playbooks` | Create playbook. |
| `GET` | `/api/playbooks/{id}` | Playbook + its rules. |
| `PATCH` | `/api/playbooks/{id}` | Update playbook. |
| `DELETE` | `/api/playbooks/{id}` | Delete. |
| `GET` | `/api/playbooks/{id}/rules` | Rules for a playbook. |
| `POST` | `/api/playbooks/{id}/rules` | Create rule (preferred/acceptable/prohibited/fallback/weight/required). |
| `PATCH` | `/api/playbooks/rules/{rule_id}` | Update rule (self-service CRUD). |
| `DELETE` | `/api/playbooks/rules/{rule_id}` | Delete rule. |
| `GET` | `/api/playbooks/resolve` | `?contract_type=` → all applicable playbooks merged by precedence (used by S2/S3). Deterministic. |
| `POST` | `/api/playbooks/bootstrap` | Body `{corpus: [contract_ids] or filter}`. One-time batch LLM job → seeds preferred language + acceptable variations. Prohibited terms come from template seed, not this job. Returns created rule count. |

## S2 — Contract Analysis  `/api/analysis`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analysis/{contract_id}` | Run analysis. Layer 1 (deterministic structural) + Layer 2 (batched LLM, paper-origin-aware). Returns `AnalysisResult` (flags[], risk). Persists `flag`, `risk_score`. |
| `GET` | `/api/analysis/{contract_id}` | Fetch stored flags + risk. |
| `GET` | `/api/analysis/{contract_id}/flags` | Flags only, filterable by `flag_type, severity`. |

## S3 — Redline & Suggestion  `/api/redlines`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/redlines/{contract_id}` | Generate redlines for flagged clauses. Body `{stance_mode}`. For each queued clause: NMS-context read → bundled LLM (replacement text + alternatives + explanation + comment) → deterministic diff → non-interference check. Persists `redline`, writes NMS `decision_event` (outcome pending). |
| `GET` | `/api/redlines/{contract_id}` | Fetch redlines. |
| `POST` | `/api/redlines/{redline_id}/toggle-fallback` | Deterministic swap preferred↔fallback; re-diffs. |
| `POST` | `/api/redlines/{redline_id}/refine` | Body `{instruction}`. Multi-pass refinement LLM call → re-diff. |
| `POST` | `/api/redlines/{redline_id}/decision` | Body `{outcome: accepted\|rejected, final_text?}`. Updates redline status + appends NMS outcome. |

## S4 — Drafting  `/api/drafting`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/drafting/clause` | Body `{clause_type, context, mode}`. Cascade: playbook lookup → frequency tracker (Service 7 last-N, metadata-scoped) → LLM (rewrite/novel). Returns drafted text + source (playbook\|frequency\|llm). |
| `POST` | `/api/drafting/document` | First-draft from template + variables (deterministic template engine; optional on-demand LLM polish). |
| `POST` | `/api/drafting/precedent` | Precedent-matched: vector search → style-matched LLM generation. |
| `POST` | `/api/drafting/memo` | Memo/action-letter drafting (LLM). |

## S5 — Document Intelligence  `/api/intelligence`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/intelligence/{contract_id}/summarize` | Risk-aware summary (grounded on S1 metadata + S2 flags). |
| `POST` | `/api/intelligence/{contract_id}/summarize-redlines` | Redline-thread summary. |
| `POST` | `/api/intelligence/{contract_id}/qa` | Body `{question}`. Loads clause array (no vector) → LLM answer + char-level citations. Caches to `qa_cache`. |
| `POST` | `/api/intelligence/{contract_id}/easy-prompt` | NL → structured legal prompt; returns `{structured_prompt, route: s3\|s4}` (caller then invokes S3/S4). |
| `POST` | `/api/intelligence/{contract_id}/research` | Chat2 Research: web search synthesized with contract context. |
| `GET` | `/api/intelligence/{contract_id}/navigation` | Deterministic clause-navigation index from clause types. |

## S8 — Obligation & Monitoring  `/api/obligations`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/obligations/{contract_id}/extract` | LLM obligation extraction (grounded on S1 metadata), once at ingest. Persists `obligation`. |
| `GET` | `/api/obligations/{contract_id}` | List obligations. |
| `POST` | `/api/obligations/monitor/run` | Trigger the daily monitor pass (also cron-driven). Deterministic deadline + renewal-window checks → alerts; renewal-window hits trigger bundled renewal-rec + compliance LLM call. |
| `POST` | `/api/obligations/{contract_id}/compliance-check` | On-demand compliance verification vs current playbook (reuses S2 deviation rubric). |
| `GET` | `/api/obligations/alerts` | List alerts (filter by type, acknowledged). |
| `POST` | `/api/obligations/alerts/{id}/ack` | Acknowledge. |

## S9 — Analytics  `/api/analytics`

Deterministic reads over SQL views. No LLM.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/analytics/intelligence` | Contract-intelligence dashboard. |
| `GET` | `/api/analytics/portfolio-risk` | Severity-weighted portfolio risk roll-up. |
| `GET` | `/api/analytics/contract-value` | Contract-value tracking. |
| `GET` | `/api/analytics/tabular` | Tabular review; `?columns=` may include NL question columns (served from `qa_cache`). |
| `GET` | `/api/analytics/renewals` | Renewal dashboard (dates + risk + recommendation). |

## Review Pipeline & Autonomous Trigger  `/api/review`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/review/run` | Body `{contract_id}` or multipart upload. Orchestrates S1→S6→S2→S3 (S1 parse + S6 fetch concurrent) → deterministic gate. Creates `review_run`; returns run_id + gate decision + redlines/escalation. |
| `GET` | `/api/review/runs/{run_id}` | Fetch run status + results. |
| `POST` | `/api/review/webhook` | Upload-event webhook entrypoint → enqueues a review run (the "autonomous" trigger). |

## Version Comparison  `/api/versions`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/versions/diff?contract_id=&v_a=&v_b=` | Fetch two versions → clause-align by id → char-level diff → change set (tracked changes). Deterministic. |
| `POST` | `/api/versions/diff/summary` | Body `{contract_id, v_a, v_b}`. Optional LLM semantic-change summary over the change set. |

## Health / ops

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness (DB ping, embedding model loaded). |

---

## Notes for implementers
- The **diff engine** behind `/api/versions/diff` and the redline `tracked_changes` field is the same shared component (Tech_Stack §7).
- The **frequency tracker** used by `/api/drafting/clause` is a deterministic last-N query exposed by S7 (`/api/repository/precedent-search` is the vector sibling; the frequency query is a separate metadata-scoped aggregation).
- `smart-search`, `qa`, `easy-prompt`, and `nl_to_filter` are the **only** endpoints where an LLM touches search/query translation; the actual retrieval is always deterministic.
- Endpoints that persist LLM output must validate it (FR-7) before writing.
