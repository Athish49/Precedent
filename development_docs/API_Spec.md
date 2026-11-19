# API Specification — Precedent Backend

REST over HTTP (FastAPI). JSON in/out. No auth (Non-Goals). Base path `/api`. All IDs are UUIDs. Errors use a consistent envelope: `{"error": {"code": str, "message": str, "detail": any}}` with appropriate HTTP status. Endpoints are grouped by service; each maps to a router in `backend/app/api/routes/` (see Backend_Structure.md).

Notation: request/response bodies are described by their key fields; full shapes are the Pydantic models in Data_Model.md.

## Conventions
- `POST` for actions/creation, `GET` for reads, `PATCH` for partial updates, `DELETE` for removal.
- Long operations (processing, review pipeline, bootstrap) run synchronously for portfolio scale but return a `run_id` where a record is created; a `GET` fetches status/results.
- Pagination: `?limit=&offset=` on list endpoints; responses include `{items, total}`.
- `PATCH` applies only the fields present in the body. A field sent as `null` is cleared; a field left out is untouched.
- **Build status marker.** The playbook redesign (`playbook_plan.md`) changes several contracts below. Rows and fields marked **†** are specified but not yet implemented; they belong to phase 4 of `playbook_implementation.md`. Unmarked rows describe the running backend.

---

## S1 — Document Processing  `/api/documents`

Ingestion runs through Extend AI (Parse + Extract) in the background, so upload is **asynchronous**: `POST` returns `202` immediately and the client polls `GET /{id}` until `status` is `ready` or `failed` (`document_processing_plan.md` §3.6, §5.1; `document_processing_implementation.md` §4.3).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | Upload a contract. Multipart `file`, `paper_origin`, optional `contract_type`, `party_role`, `context` (JSON string), optional `force` (boolean). Validates and stores the file, writes `contract` + `contract_version` (version 1) with `status = processing`, schedules the background ingest, and returns before Extend is called. |
| `GET` | `/api/documents/{contract_id}` | Fetch the contract, its parties, signatories, fields with evidence, and any warnings. |
| `GET` | `/api/documents/{contract_id}/clauses` | Clause array. Query parameter `level`: `1` (default, top-level sections only) or `all`. |
| `GET` | `/api/documents/{contract_id}/text` | Canonical text (for offset resolution / display). Unchanged. |
| `POST` | `/api/documents/{contract_id}/reprocess` | Re-run ingest against the stored file. `409 has_analysis` when a flag or redline already exists for the contract, unless `force=true` (which deletes that analysis first). |

**`POST` responses:**

- `202` — `{"contract_id": "<uuid>", "version_id": "<uuid>", "status": "processing"}`
- `400` — `invalid_paper_origin`, `invalid_contract_type`, `invalid_party_role`, `invalid_context`, `unsupported_format`, `empty_file`
- `409` — `duplicate_file` with `{"existing_contract_id": "<uuid>"}` (the file's sha256 already exists; bypass with `force=true`)
- `413` — `file_too_large`

**`GET /{id}` response shape:**

```json
{
  "id": "…", "title": "…", "original_filename": "…", "status": "ready",
  "status_reason": null, "paper_origin": "own", "source_format": "docx",
  "contract_type": "saas_msa", "contract_type_source": "extracted",
  "party_role": "vendor", "context": {}, "counterparty_id": "…",
  "current_version_id": "…", "page_count": 9,
  "created_at": "…", "updated_at": "…",
  "parties": [{"party_id": "…", "name": "…", "role": "counterparty", "role_label": "Customer",
               "entity_type": "…", "jurisdiction": "…", "address": "…"}],
  "signatories": [{"printed_name": "…", "title": "…", "party_name": "…", "is_signed": true, "signed_date": "2026-01-12"}],
  "fields": [{"field_key": "governing_law", "value": "Delaware", "source": "extract", "confidence": "high",
              "quote": "…", "page": 7, "char_start": 18230, "char_end": 18262, "clause_id": "…"}],
  "metadata": {"effective_date": "2026-01-12", "expiry_date": "2029-01-12", "expiry_is_derived": true, "…": "…"},
  "warnings": []
}
```

`fields` holds the value in force per key (`user` over `extract` over `derived`). While `status` is `processing`, the lists are empty. When `failed`, `status_reason` is one of `password_protected`, `unsupported_format`, `too_large`, `unreadable`, `no_text`, `extraction_failed`, `timeout`, `provider_unavailable`.

**`GET /{id}/clauses` item shape:**

```json
{"id": "<uuid>", "clause_key": "<uuid>", "ordinal": 4, "level": 1, "parent_id": null,
 "section_number": "6", "title": "Limitation of Liability", "heading_text": "6. LIMITATION OF LIABILITY",
 "clause_type": "limitation_of_liability", "type_source": "extract", "issue_keys": [],
 "text": "…", "char_start": 5120, "char_end": 6480, "page_start": 3, "page_end": 3}
```

### Contract type and context

Playbook resolution needs to know what the contract is and the deal it belongs to.

- `contract_type` not supplied → taken from one field in the Extend Extract schema (an enum generated from `agreement_type`), returned alongside every other field in the same run; `contract_type_source` is `extracted`. A user-supplied value at upload always wins and is recorded as `contract_type_source = "user"`. There is no separate classification call.
- `regimes` not supplied → derived by deterministic keyword rules: `hipaa` if the text mentions PHI or business-associate terms, `gdpr` if it mentions GDPR, controller and processor.
- `deal_value_band` → derived from a supplied deal value using the band boundaries in `context_dimension`.
- With no context dimensions defined (no seed loaded), the context is accepted as given; validation and band derivation are skipped.

## S7 — Repository & Search  `/api/repository`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/repository/contracts` | Faceted list: filters `contract_type, counterparty_id, status, effective_date_from/to, value_min/max`. Deterministic. |
| `GET` | `/api/repository/search` | Query params `q` (keyword full-text) or `type=faceted`. Deterministic full-text (`tsvector`) + faceted. |
| `POST` | `/api/repository/smart-search` | Body `{query: str}`. One LLM call → `{filters, semantic_query?}`; executes faceted + optional vector search; returns merged results. |
| `PATCH` | `/api/repository/contracts/{id}` | **†** Update `contract_type`, `party_role` and `context` after upload. Same validation as the upload form. |
| `GET` | `/api/repository/contracts/{id}/redline-history` | Prior positions per clause type (from S3/NMS decision log). |
| `GET` | `/api/repository/contracts/{id}/versions` | List versions (parent-child). |
| `POST` | `/api/repository/contracts/{id}/versions` | Store a new version (bytes + relation); increments version_number. |
| `GET` | `/api/repository/precedent-search` | Internal-ish: `?clause_type=&query=` → vector search over `clause_embedding` (used by S4). |

## S6 — Playbook & Rules  `/api/playbooks`

The playbook is versioned: rules and their children belong to a `playbook_version`. Only a `draft` version is editable; any write to a `published` or `superseded` version returns **409**. Every edit on a draft appends a `playbook_change_log` row.

### Playbooks and rules

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/playbooks` | List playbooks (header fields: key, layer, party_role, paper_scope, jurisdiction, status, current version). |
| `POST` | `/api/playbooks` | Create playbook. |
| `GET` | `/api/playbooks/{id}` | Playbook + the rules of its current version. |
| `PATCH` | `/api/playbooks/{id}` | Update playbook header. |
| `DELETE` | `/api/playbooks/{id}` | Delete. Cascades to versions, rules and rule children. |
| `GET` | `/api/playbooks/{id}/rules` | Rules for a playbook. Every rule response (this endpoint, the single-rule `GET`/`POST`/`PATCH` below, and the embedded rules on `GET /api/playbooks/{id}`) embeds its full child set: `positions`, `parameters`, `red_lines`, `objections`, `dependencies`, `test_cases`. |
| `POST` | `/api/playbooks/{id}/rules` | Create rule. Body: scalars (`clause_type`, `required`, `risk_weight`, `playbook_version_id?`, `issue_id?`, `rule_key?`, `title?`, `position_summary?`, `risk_rationale?`, `negotiable?`, `default_zone?`, `needs_human_judgment?`, `judgment_note?`, `applies_when?`, `detection_guidance?`, `source_ref?`, `authored_by?`, `approved_by?`, `last_reviewed_at?`) plus inline `positions: []` and `red_lines: []` child arrays, created in the same transaction. Unknown fields — including the five removed legacy fields (`preferred_language`, `acceptable_variations`, `prohibited_terms`, `fallback_language`, `escalation_threshold`, gone as of migration `015`, task 5.5) — are rejected with 422. 409 `version_not_draft` if `playbook_version_id` names a non-draft version. |
| `PATCH` | `/api/playbooks/rules/{rule_id}` | Update rule. Nullable scalar fields can be cleared with `null`; an omitted field is left unchanged. `positions`/`red_lines`, when present (including `[]`), replace the rule's full set of that child table by id-sync; omitting them leaves the existing rows untouched. Sending either for a rule in a non-draft version fails with 409 `version_not_draft` (same gate as the per-child endpoints below); a scalar-only PATCH is not gated. |
| `DELETE` | `/api/playbooks/rules/{rule_id}` | Delete rule and its children. |

### Versions

Routes live in `app/api/routes/playbook_versions.py` (separate module from `playbooks.py`; `app/main.py` auto-discovers every `router` under `app/api/routes/`, so this needed no change to `playbooks.py`'s existing functions). Business rules — draft-only writes, minimum validation, change-log entries — live in `app/services/playbook/versions.py`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/playbooks/{id}/versions` | List versions with status and effective dates. |
| `POST` | `/api/playbooks/{id}/versions` | Create a draft by copying the current version (rules and all children), via `playbook_repo.copy_version`. Body `{version, created_by?}`. 400 if the playbook has no current version. |
| `GET` | `/api/playbooks/versions/{version_id}` | Fetch one version. |
| `POST` | `/api/playbooks/versions/{version_id}/publish` | Publish a draft. Body `{change_summary?, approved_by}`. Requires a change summary (in the body or already on the version) and an approver, and validates the per-rule minimums (`playbook_plan.md` §7.2: a preferred position; an acceptable-variant position; 2+ fallback positions and 2+ objections for negotiable rules; a risk rationale of 2+ sentences; a red line when `risk_weight >= 7`; 5+ test cases). **Does not yet** run the version's test cases or enforce a pass-rate threshold — that is task 4.10's test-case runner, which does not exist yet; until it lands, minimum validation stands in for it. 409 if the version is not a draft; 400 with a per-rule violation list if minimums fail, or if no change summary/approver is available. Freezes the version, sets `playbook.current_version_id`, marks the previous version `superseded`. |
| `GET` | `/api/playbooks/versions/diff?a=&b=` | Field-level diff between two versions' rule sets, matched by `rule_key`: rules added/removed, and per modified rule, changed scalar fields plus child-table row-count deltas. Child rows are not individually matched across versions — `copy_version` gives every child row a fresh id, so most child tables have no stable key to diff by; positions/parameters/etc. are summarized as a count delta rather than field-by-field. |
| `POST` | `/api/playbooks/versions/{version_id}/test` **†** | Run the rule test cases for a version. Returns pass rate per rule and per expected outcome, plus failing cases. `?mode=deterministic` runs only cases decidable without the model (phrase, regex and missing-clause cases); the default mode calls the model. Not yet implemented — task 4.10. |

### Rule children

CRUD on draft versions only (409 if the rule's version is `published` or `superseded`), one sub-resource per child table. Each follows the same shape: `GET`/`POST` on `/api/playbooks/rules/{rule_id}/<child>`, `PATCH`/`DELETE` on `/api/playbooks/<child>/{id}`. Every write appends one `playbook_change_log` row (no-op for a legacy rule with no `playbook_version_id`).

| `<child>` | Table | Notes |
|---|---|---|
| `positions` | `rule_position` | The ladder: one `preferred` (rung 0), fallbacks at rung 1..n, plus `acceptable_variant` rows. |
| `parameters` | `rule_parameter` | Structured limits: `preferred_value`, `green_limit`, `yellow_limit`, `context_overrides`. |
| `red-lines` | `red_line` | Rule-scoped CRUD follows the standard shape above (`/api/playbooks/rules/{rule_id}/red-lines`, draft-gated). Playbook-scoped: `GET`/`POST` `/api/playbooks/{id}/red-lines`. Global: `GET`/`POST` `/api/playbooks/red-lines` (in `playbooks.py`'s literal section, next to `/resolve`, since it is a bare two-segment path). `PATCH`/`DELETE` for any scope at `/api/playbooks/red-lines/{id}`; playbook- and global-scoped rows are not attached to any version, so they are always editable and log nothing. |
| `objections` | `rule_objection` | Counterparty objection, sendable response, talking points, recommended position. |
| `dependencies` | `rule_dependency` | `read_with` \| `trade_against` \| `requires` \| `conflicts_with` another `rule_key`. |
| `test-cases` | `rule_test_case` | Sample clause, expected outcome, zone, rung or red-line key; `is_trap` for negated or look-alike wording. |

### Lookups

Read-only. `taxonomy`/`context-dimensions` are backed by `taxonomy_repo`, `roles`/`escalation-policies` by `authority_repo` (both task 1.4); all four live in `playbooks.py`'s literal section (bare two-segment paths, same ordering reason as `/resolve`).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/playbooks/taxonomy` | Agreement types, clause families and clause issues, in one read. |
| `GET` | `/api/playbooks/roles` | Approver roles. |
| `GET` | `/api/playbooks/context-dimensions` | Context dimensions with allowed values. |
| `GET` | `/api/playbooks/escalation-policies` | `?playbook_id=&clause_type=&zone=` optional filters. The approval matrix, most specific first. |

### Resolve

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/playbooks/resolve` | Deterministic. Today: `?contract_type=` → `{contract_type, applied_practice_areas, rules: {clause_type: rule}}`, an identity match on practice area. **†** Target: `?contract_type=&party_role=&paper_origin=&context=` (context as URL-encoded JSON) → `{rules: ResolvedRule[], playbook_version_ids, applied_playbook_keys}`. |

Target resolution **†**, in order:

1. Select the active `base` playbook.
2. Select the active `agreement` playbook whose `practice_area`, `party_role` and `paper_scope` match.
3. Select every active `overlay` whose `applies_when` matches the context.
4. Take each playbook's `current_version_id`.
5. Merge rules by `rule_key`, highest `precedence` first (base 10, agreement 20, overlay 30); ties broken by playbook key.
6. Drop rules whose `applies_when` does not match.
7. Return the merged rules with children. Each `ResolvedRule` carries `source_playbook_id`, `source_playbook_name` and `source_version`.

An unknown contract type resolves to the baseline only. With no playbooks loaded the result is an empty list, which every consumer handles.

### Bootstrap

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/playbooks/bootstrap` | Body `{playbook_id, contract_ids}` or `{playbook_id, contract_type}`. Batch LLM job that mines preferred language + acceptable variations from executed contracts. Returns `{created_rule_count}`. **†** Writes a `preferred` position and `acceptable_variant` positions on rules in a **draft** version with `authored_by = "bootstrap"`; rejects a published version; never creates fallbacks, red lines or parameters; samples across contracts. |

## S2 — Contract Analysis  `/api/analysis`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analysis/{contract_id}` | Run analysis. Layer 1 (deterministic structural) + Layer 2 (batched LLM, paper-origin-aware). Returns `AnalysisResult` (flags[], risk). Persists `flag`, `risk_score`. **†** Each governed flag carries `rule_key`, `zone` (green\|yellow\|red), `position_id` or `red_line_id`, and `parameter_values`; `risk.score` is normalised to 0–1 and `risk.max_zone` is returned. |
| `GET` | `/api/analysis/{contract_id}` | Fetch stored flags + risk. |
| `GET` | `/api/analysis/{contract_id}/flags` | Flags only, filterable by `flag_type, severity` (**†** and `zone`, `rule_key`). |

## S3 — Redline & Suggestion  `/api/redlines`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/redlines/{contract_id}` | Generate redlines for flagged clauses. Body `{stance_mode}`. For each queued clause: NMS-context read → bundled LLM (replacement text + alternatives + explanation + comment) → deterministic diff → non-interference check. Persists `redline`, writes NMS `decision_event` (outcome pending). **†** The preferred redline adapts the rule's rung 0 language to the contract's defined terms; `alternatives` are the rule's fallback rungs allowed by their `conditions`, in order, each with its `position_id`; the counterparty comment draws on the best-matching objection's `response` (`objection_id` recorded). The decision event records `rule_id`, `rule_key`, `position_id`, `playbook_version_id`. |
| `GET` | `/api/redlines/{contract_id}` | Fetch redlines. |
| `POST` | `/api/redlines/{redline_id}/toggle-fallback` | Deterministic; re-diffs. Today swaps preferred↔the LLM's first alternative. **†** Steps one rung down the playbook ladder per call and sets `position` to `fallback_1`, `fallback_2`, … |
| `POST` | `/api/redlines/{redline_id}/refine` | Body `{instruction}`. Multi-pass refinement LLM call → re-diff. |
| `POST` | `/api/redlines/{redline_id}/decision` | Body `{outcome: accepted\|rejected, final_text?}`. Updates redline status + appends NMS outcome. **†** Accepting a `yellow` rung creates a `playbook_exception` in `requested` status for that rung's approver. |

## S4 — Drafting  `/api/drafting`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/drafting/clause` | Body `{clause_type, context, mode}`. Cascade: playbook lookup → frequency tracker (Service 7 last-N, metadata-scoped) → LLM (rewrite/novel). Returns drafted text + source (playbook\|frequency\|llm). Today the playbook step fires only when the caller passes `preferred_language`. **†** With `contract_type`, `party_role` and deal context in the request (and optionally an issue key), the service resolves the playbook itself and returns rung 0 language with no model call; the caller-supplied override is kept. |
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
| `POST` | `/api/review/run` | Body `{contract_id}` or multipart upload. Orchestrates S1→S6→S2→S3 → deterministic gate. Creates `review_run`; returns run_id + gate decision + redlines/escalation. **†** `gate_decision` is one of `auto_applied` (worst zone none/green), `needs_approval` (yellow) or `escalated` (red, or a redline quality failure); `gate_reason` names the approver role, time limit and required information; the run records `playbook_version_ids`. |
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
| `GET` | `/api/health` | Liveness (DB ping, embedding model loaded, object storage reachable). Also reports `db_schema` and `db_schema_exists` — the project schema on the shared database. |

---

## Notes for implementers
- The **diff engine** behind `/api/versions/diff` and the redline `tracked_changes` field is the same shared component (Tech_Stack §7).
- The **frequency tracker** used by `/api/drafting/clause` is a deterministic last-N query exposed by S7 (`/api/repository/precedent-search` is the vector sibling; the frequency query is a separate metadata-scoped aggregation).
- `smart-search`, `qa`, `easy-prompt`, and `nl_to_filter` are the **only** endpoints where an LLM touches search/query translation; the actual retrieval is always deterministic.
- Endpoints that persist LLM output must validate it (FR-7) before writing.
- **The model never assigns a zone.** Layer 2 returns which position the text matches, extracted parameter values with verbatim quotes, and a yes/no with a quote per semantic red line; the deterministic evaluator turns that into green, yellow or red.
- **No endpoint depends on seed data.** Empty playbook, role and policy tables are valid: resolve returns an empty list, and the gate still returns a decision and records that no approver is configured.
- Object keys in requests and responses are logical (`contracts/{id}/{filename}`); the storage backend applies the project prefix.
