# Document processing implementation: from current state to target state

This document is the work breakdown for moving document processing from what exists today (`document_processing_status.md`) to the target design (`document_processing_plan.md`). Each task is written so a sub-agent can pick it up with no other briefing.

**Every agent must read first:** sections 1 to 5 of this document, and `document_processing_plan.md` sections 1.1 (scope), 5 (pipeline), 7 (data model) and 11 (removal rules).

## 1. Ground rules

These repeat the rules in `playbook_implementation.md` section 1, which also apply here.

- **Repository:** work on the local `main` branch. Do not create worktrees. Do not push. Commit only when the user asks.
- **Database:** `backend/.env` points at a remote Postgres. Do not run migrations or loaders against it without the user's go-ahead. Write and test against mocked sessions, as the existing unit tests do.
- **Partitioning:** everything lives in the `precedent` namespace. Models inherit the schema from shared metadata; migrations do not name a schema; hand-written SQL names it from the setting. See `playbook_implementation.md` section 1.1.
- **Cloud only:** no local database, no local file storage. Tests use `tests/in_memory_storage.py` and mocked sessions.
- **No network in tests.** Nothing in `backend/tests/` or `backend/seed/tests/` calls Extend. Tests use the fake client from task 0.1 and the recorded responses from task 0.3.
- **Live Extend calls need the user's go-ahead** and a key in `EXTEND_API_KEY`. Only tasks 6.2 and 6.3 make them. Never write the key to a file in the repository or print it.
- **Seed isolation:** nothing under `backend/app/`, `backend/tests/`, `backend/migrations/` or `backend/scripts/` may import from `seed` or read a file under `backend/seed/`. Seed code may import from `app`. Tasks that touch seed code also run `pytest seed/tests`.
- **Tests:** run `cd backend && .venv/bin/python -m pytest -q` before reporting a task done. Baseline on 2026-11-16: 1,263 passed, 4 failed. The 4 failures are all in `tests/unit/test_llm_batch.py` and are not ours; do not fix them here, and do not add to them. Seed suite baseline: 144 passed.
- **Migrations are serial.** Only one agent writes a migration at a time. Check the head with `.venv/bin/alembic heads` and set `down_revision` to it. The head on 2026-11-16 is `m3n4o5p6q7r8` (file `013`). The playbook work may add more first; always use the real head and the next free file number.
- **Old and new code coexist only during development.** New modules get new names so the old pipeline keeps working and the suite stays green until phase 5. Phase 5 deletes the old pipeline in one go. Do not add switches between the two.
- **Scope.** Versioning, clause matching across versions, the diff engine and version comparison are out of scope (`document_processing_plan.md` section 1.1). Do not improve them.
- **File ownership.** A task owns the files it lists. Do not edit another task's file; report the problem instead.
- **Reporting.** Finish with: files changed, test result, each "Done when" item marked met or not met, and anything left open.

## 2. Current state the tasks start from

Checked 2026-11-16.

| Item | State |
|---|---|
| Old pipeline | `app/services/document_processing/`: `parsers.py`, `segmentation.py`, `clause_types.py`, `extraction.py`, `service.py`, plus `context_capture.py` from playbook task 4.1 |
| Contract type | `context_capture.classify_contract_type` makes a model call through `core/llm` when the uploader gives no type. Prompt `core/llm/prompts/contract_type_classify.md`, task key `contract_type_classify`, schema `core/llm/schemas/classification.py` |
| LLM import guard | **Not working.** `tests/unit/test_ci_guards.py` builds its path as `backend/backend/app`, which does not exist, so every guard in the file passes on nothing. The CI workflow step does check the real path and would fail on `context_capture.py` |
| Tables | `contract` has `party_role` and `context`; `clause.clause_type` has a foreign key to `clause_family`; `clause.issue_keys` exists. Migrations `010` to `013` are the playbook's |
| Reference data | `agreement_type`: agreement kinds are `nda`, `saas_msa`, `dpa`, `vendor_msa`. `clause_family`: 29 keys including `other`, each with `synonyms` |
| Seed contracts | 12 DOCX files under `backend/seed/contracts/data/halcyon/docx/`, built from `source/*.md` by `seed/contracts/build.py`. Word heading styles, numbered sections with sub-numbers (`1.1`). `expected.yaml` holds expected playbook findings, contract type, counterparty and context. It holds no field-level answers |
| Seed parse test | `seed/tests/test_contracts_parse.py` imports the old `parse` and `segment` |
| Our organisation | Halcyon Care, Inc. (fictional), per `playbook_implementation.md` section 2 |
| Extend test material | `backend/tests/fixtures/extend_eval/`: four forms of one test contract, an answer file, 20 recorded responses, three scripts |
| Dependencies | `pdfplumber`, `python-docx`, `spacy`, `rapidfuzz`, `httpx` are runtime dependencies. A `seed` dependency group exists |

## 3. Extend API facts

Confirmed against the live API on 2026-11-16. Use these; do not re-derive them.

| Item | Value |
|---|---|
| Base URL | `https://api.extend.ai` |
| Headers | `Authorization: Bearer <key>`, `x-extend-api-version: 2026-02-09` |
| Upload | `POST /files/upload`, multipart field `file`. Returns `{id}` |
| Extract | `POST /extract_runs` with `{file: {id}, config: {baseProcessor, baseVersion, parseConfig: {engine, engineVersion}, schema, advancedOptions: {citationsEnabled: true}}}`. Returns `{id, status}` |
| Poll | `GET /extract_runs/{id}` until `status` is `PROCESSED` or `FAILED`. About 20 seconds for 3 pages |
| Parsed text | `GET /parse_runs/{parseRunId}`, using the `parseRunId` on the finished extract run. No extra charge. Blocks are at `output.chunks[].blocks[]`; chunks are one per page by default |
| Pinned versions | `extraction_light` `3.8.0`, `parse_light` `1.0.0` |
| Block fields used | `type`, `content` (markdown), `metadata.page.number` |
| Block types seen | `text`, `heading`, `section_heading`, `table`, `key_value`, `header`, `footer`, `page_number` |
| Extract output | `output.value` shaped like the schema; `output.metadata["<path>"].citations[]` with `referenceText` and `page.number`. Paths look like `effective_date`, `parties[0].name` |
| Schema rules | Primitives must be nullable (`["string","null"]`). Enums must include `null` and must be declared as a separate `"enum"` list (e.g. `{"type": ["string","null"], "enum": [...values, null]}`) — the enum's literal values must NOT be put into the `"type"` array itself (confirmed live: `["value1","value2",null]` as `type` is rejected with "Invalid type array. Only combinations of a primitive type and null are supported"). Array properties must be a bare `"type": "array"` — `["array","null"]` is rejected the same way, and `"nullable": true` is rejected separately as unsupported; there is no supported way to make an array property itself nullable. Array items must have a bare primitive `"type"` (e.g. `{"type": "string"}`) — a nullable item type (`["string","null"]`) is rejected with "Array items must have a type property. Array items type must be one of: string, number, integer, boolean, object"; a nullable *property inside an object item* (e.g. `parties[].name`) is fine. No `anyOf`, `oneOf` or `$ref`. Nesting to 5 levels. `"extend:type": "date"` gives ISO dates |
| Failure | `status: FAILED` with `failureReason`, e.g. `CORRUPT_FILE`, `PASSWORD_PROTECTED_FILE`, `FILE_TYPE_NOT_SUPPORTED`, `FILE_SIZE_TOO_LARGE`, `OUT_OF_CREDITS` |
| Rate limit | HTTP 429 with code `RATE_LIMIT_EXCEEDED`; honour `Retry-After` |

Known quirks the code must handle (all reproduced in the recorded responses):

1. A running page header is tagged `header` only on page 1; on later pages it is `heading` or `text`.
2. A paragraph in capitals can be tagged `section_heading`.
3. Run-in headings ("2. Services. Supplier shall…") are inside a `text` block.
4. A table crossing a page break comes back as two `table` blocks.
5. A corrupt DOCX and a blank page return `PROCESSED` with little or no text.
6. Free-text answers vary in wording and capitals between runs. Numbers, dates, booleans and enums do not.
7. On the Light tier, values inside lists (`parties[0].name`) have no citation.
8. A line-break hyphen appears as "third- party". A Word bullet appears as a private-use character (``).

## 4. Shared contracts between tasks

Tasks in phase 2 run in parallel. They agree through the types and shapes below. Task 0.2 creates the types; do not change them without updating this section.

### 4.1 Types (`app/services/document_processing/types.py`)

Frozen dataclasses. No database or network imports.

```python
@dataclass(frozen=True)
class Block:
    index: int            # position in the parse output, 0-based
    type: str             # Extend block type
    text: str             # cleaned text as it appears in canonical text
    page: int             # 1-based
    char_start: int       # offsets into canonical text; -1 if the block was dropped
    char_end: int
    dropped: bool = False # header, footer, page number, repeated header

@dataclass(frozen=True)
class CanonicalDocument:
    text: str
    blocks: tuple[Block, ...]   # all blocks, dropped ones included
    page_count: int

@dataclass(frozen=True)
class SectionHint:               # one entry of Extract's clause list
    section_number: str | None
    title: str | None
    family: str | None

@dataclass(frozen=True)
class ClauseDraft:
    ordinal: int                 # document order, 0-based, parents before children
    level: int                   # 1 = section, 2+ = sub-clause
    parent_ordinal: int | None
    section_number: str | None
    title: str | None            # clean title, no numbering
    heading_text: str | None     # raw heading as written
    text: str
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    clause_type: str = "other"
    type_source: str = "none"    # extract | dictionary | none
    issue_keys: tuple[str, ...] = ()
    anchored: bool = True        # False if found by the fallback rule

@dataclass(frozen=True)
class FieldValue:
    field_key: str
    value: Any                   # JSON-serialisable, typed per the registry
    source: str                  # extract | derived
    confidence: str | None       # high | low
    quote: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    clause_ordinal: int | None

@dataclass(frozen=True)
class PartyDraft:
    name: str
    role_label: str | None
    entity_type: str | None
    jurisdiction: str | None
    address: str | None
    role: str = "other"          # own | counterparty | other

@dataclass(frozen=True)
class SignatoryDraft:
    printed_name: str | None
    title: str | None
    party_name: str | None
    is_signed: bool | None
    signed_date: date | None

@dataclass(frozen=True)
class IngestResult:
    document: CanonicalDocument
    title: str | None
    contract_type: str | None
    clauses: tuple[ClauseDraft, ...]
    fields: tuple[FieldValue, ...]
    parties: tuple[PartyDraft, ...]
    signatories: tuple[SignatoryDraft, ...]
    warnings: tuple[str, ...]
```

### 4.2 Module names

New modules use names that do not clash with the old ones, so both can exist until phase 5.

| New module | Role | Replaces |
|---|---|---|
| `app/core/extend/client.py` | Extend HTTP client | — |
| `document_processing/types.py` | Section 4.1 | DTOs in `service.py`, `extraction.py`, `parsers.py` |
| `document_processing/fields.py` | Field registry and Extract schema builder | `extraction.py` |
| `document_processing/canonical.py` | Blocks to canonical text | `parsers.py` |
| `document_processing/sections.py` | Segmentation | `segmentation.py` |
| `document_processing/clause_typing.py` | Clause typing | `clause_types.py` |
| `document_processing/mapping.py` | Extract output to field values, evidence, checks | `extraction.py` |
| `document_processing/parties.py` | Own-organisation matching | inline code in `service.py` |
| `document_processing/upload_validation.py` | Size, type, hash, filename | `_source_format_from_filename` |
| `document_processing/invariants.py` | Guarantees in plan section 7.5 | — |
| `document_processing/ingest.py` | Orchestrator | `service.py` |
| `document_processing/context_capture.py` | Stays. Loses the model call in task 3.4 | — |

### 4.3 API shapes

`POST /api/documents`: multipart `file`, `paper_origin`, optional `contract_type`, `party_role`, `context` (JSON string), optional `force` (boolean).

- `202` `{"contract_id": "<uuid>", "version_id": "<uuid>", "status": "processing"}`
- `400` `invalid_paper_origin`, `invalid_contract_type`, `invalid_party_role`, `invalid_context`, `unsupported_format`, `empty_file`
- `409` `duplicate_file` with `{"existing_contract_id": "<uuid>"}`
- `413` `file_too_large`

`GET /api/documents/{id}`:

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

`GET /api/documents/{id}/clauses`: list of

```json
{"id": "<uuid>", "clause_key": "<uuid>", "ordinal": 4, "level": 1, "parent_id": null,
 "section_number": "6", "title": "Limitation of Liability", "heading_text": "6. LIMITATION OF LIABILITY",
 "clause_type": "limitation_of_liability", "type_source": "extract", "issue_keys": [],
 "text": "…", "char_start": 5120, "char_end": 6480, "page_start": 3, "page_end": 3}
```

Query parameter `level`: `1` (default) or `all`.

`GET /api/documents/{id}/text`: unchanged.

`POST /api/documents/{id}/reprocess`: `202`; `409` `has_analysis` when a flag or redline exists, unless `force=true`.

## 5. Coordination with the playbook work

| Playbook item | What to do |
|---|---|
| Task 4.1, done: model call to classify contract type | Task 3.4 here removes the model call and takes the type from Extract. The validators, `derive_regimes` and `derive_deal_value_band` stay as they are |
| Task 5.2, done: 12 seed contracts and `seed/tests/test_contracts_parse.py` | Task 5.3 here rewrites the parse test and the builder's docstring. Task 6.1 adds field answers beside `expected.yaml`. The contracts and `expected.yaml` are not edited |
| Task 5.4: end-to-end verification by uploading the corpus through the API | Must run after phase 5 here, because upload becomes `202` plus polling. Tell the user if 5.4 is about to run earlier |
| Task 5.5: delete `_SYNONYMS` from `clause_types.py`, load synonyms from `clause_family`, update docs | Phase 5 here deletes `clause_types.py` outright and `clause_typing.py` already reads `clause_family`. That part of 5.5 is no longer needed; its legacy-column drop is unaffected |
| Task 4.9: frontend alignment | Task 4.1 here changes the same files in `frontend/lib/api/`. Run them one after the other |
| Migrations | Serial across both streams. Always take the real head |

## 6. Task map

| Task | Title | Depends on | Can run alongside |
|---|---|---|---|
| 0.1 | Extend client, settings and fake client | — | 0.2, 0.3 |
| 0.2 | Shared types | — | 0.1, 0.3 |
| 0.3 | Recorded fixtures and loader | — | 0.1, 0.2 |
| 1.1 | Migration A: contract, version, clause, cascades | — | phases 0 and 2 |
| 1.2 | Migration B: new tables and metadata columns | 1.1 | phases 0 and 2 |
| 1.3 | Repositories and reading rule | 1.2 | phase 2 |
| 2.1 | Field registry and Extract schema | 0.2 | 2.2–2.8 |
| 2.2 | Canonical text builder | 0.2, 0.3 | 2.1, 2.3–2.8 |
| 2.3 | Segmentation | 0.2, 0.3 | 2.1, 2.2, 2.4–2.8 |
| 2.4 | Clause typing | 0.2 | 2.1–2.3, 2.5–2.8 |
| 2.5 | Mapping, evidence, checks, derived values | 2.1, 0.3 | 2.2–2.4, 2.6–2.8 |
| 2.6 | Parties and own-organisation matching | 0.2 | 2.1–2.5, 2.7, 2.8 |
| 2.7 | Invariants | 0.2 | 2.1–2.6, 2.8 |
| 2.8 | Upload validation | — | 2.1–2.7 |
| 2.9 | Pure pipeline assembly and replay accuracy test | 2.1–2.7 | 1.x |
| 3.1 | Ingest orchestrator | 0.1, 1.3, 2.8, 2.9 | 6.1 |
| 3.2 | Embeddings at ingest | 1.3 | 3.1 |
| 3.3 | Documents API | 3.1 | 3.4, 3.5, 3.6 |
| 3.4 | Contract type from Extract; remove the model call | 3.1 | 3.3, 3.5, 3.6 |
| 3.5 | Repoint `store_version` | 3.1 | 3.3, 3.4, 3.6 |
| 3.6 | Downstream readers and analytics views | 1.3 | 3.1–3.5 |
| 4.1 | Frontend types, upload flow and readers | 3.3 | 3.4–3.6 |
| 5.1 | Delete the old pipeline and its tests | 3.2–3.6, 4.1 | 5.3, 5.4 (land together) |
| 5.2 | Migration C: drop old columns | 5.1 | 5.4 |
| 5.3 | Seed-side updates | 5.1 | 5.1 (land together), 5.4 |
| 5.4 | Planning and README updates | 3.3 | 5.1–5.3 |
| 6.1 | Field answers for the 12 seed contracts | — | everything |
| 6.2 | Corpus run against live Extend | 2.9, 6.1, user go-ahead, key | phases 3 and 4 |
| 6.3 | Database and end-to-end check | 5.1–5.3, user go-ahead | — |
| 6.4 | Removal proof and close-out | 6.3 | — |

Three tracks can run at once:

- **Schema** (1.1 → 1.2 → 1.3): strictly serial, one agent.
- **Logic** (0.2 and 0.3, then 2.1 to 2.8 in parallel, then 2.9): no database, no network. Up to eight agents.
- **Content** (6.1): reads seed source files only.

Phase 3 starts when 1.3 and 2.9 are both done. **Run 6.2 as soon as 2.9 and 6.1 are done**, before phase 3 finishes: it is the first test on real multi-page contracts with sub-numbering, and a bad result should change the logic before the orchestration is built on it. Phase 5 is one coordinated change. Phase 6.3 and 6.4 are last.

---

## Phase 0: Foundations

### 0.1 Extend client, settings and fake client

- **Depends on:** nothing. **Parallel with:** 0.2, 0.3.
- **Owns:** `backend/app/core/extend/__init__.py`, `client.py`, `errors.py`; `backend/tests/fake_extend.py`; `backend/tests/unit/test_extend_client.py`; the Extend lines in `app/core/config.py` and `backend/.env.example`.
- **Do:**
  1. Settings: `extend_api_key` (optional string; ingest fails with a clear error when unset), `extend_base_url` (default from section 3), `extend_extract_processor` (`extraction_light`), `extend_extract_version` (`3.8.0`), `extend_parse_engine` (`parse_light`), `extend_parse_version` (`1.0.0`), `extend_poll_interval_seconds` (3), `extend_timeout_seconds` (300), `own_org_names` (list parsed from a comma-separated `OWN_ORG_NAMES`, default empty), `max_upload_mb` (25).
  2. `ExtendClient` built on `httpx.AsyncClient`. Methods: `upload(filename, data) -> file_id`; `extract(file_id, schema) -> ExtractRun` (creates the run, polls to a final state, returns `value`, `metadata`, `parse_run_id`, `usage`, processor version); `parse_output(parse_run_id) -> list[dict]` (blocks flattened across chunks, in order); `parse(file_id) -> list[dict]` (a standalone parse run for the text-only path, config `{"engine", "engineVersion", "blockOptions": {"tables": {"targetFormat": "markdown"}}}`).
  3. Errors in `errors.py`: `ExtendError` with `reason` and `retryable`; subclasses `ExtendRunFailed` (carries `failureReason`), `ExtendTimeout`, `ExtendUnavailable` (network errors and 5xx), `ExtendAuthError`. Retry 429 and 5xx up to three times with backoff, honouring `Retry-After`.
  4. `get_extend_client(settings)` factory, the single place the client is built.
  5. `tests/fake_extend.py`: `FakeExtendClient` with the same methods, constructed from a recorded extract response and a recorded parse response (task 0.3 loader), with options to raise each error.
  6. Never log the key or the `Authorization` header.
- **Done when:** unit tests cover success, a `FAILED` run, timeout, 429 then success, 5xx exhaustion and a missing key, all with `httpx.MockTransport`; no test opens a socket; nothing outside `app/core/extend/` contains the string `api.extend.ai`; the suite passes.

### 0.2 Shared types

- **Depends on:** nothing. **Parallel with:** 0.1, 0.3.
- **Owns:** `backend/app/services/document_processing/types.py`, `backend/tests/unit/test_dp_types.py`.
- **Do:** create the dataclasses exactly as in section 4.1. Add `IngestResult.level1()` returning level 1 clauses in order. No other logic.
- **Done when:** the module imports with no dependency on `sqlalchemy`, `httpx` or other `document_processing` modules; a test builds one of each type; the suite passes.

### 0.3 Recorded fixtures and loader

- **Depends on:** nothing. **Parallel with:** 0.1, 0.2.
- **Owns:** `backend/tests/fixtures/ingest/` and `backend/tests/ingest_fixtures.py`. Deletes `backend/tests/fixtures/extend_eval/` when done.
- **Do:**
  1. Create one folder per case under `tests/fixtures/ingest/`: `msa_styled_docx`, `msa_runin_docx`, `msa_runin_pdf`, `msa_scanned_pdf`. Each holds `extract.json` and `parse.json` copied from the matching `*_light_extract.json` and `*_light_parse.json` in `extend_eval/responses/`, and `answers.json` copied from `extend_eval/docs/answers.json`.
  2. Keep the four source documents under `tests/fixtures/ingest/documents/`. Keep `make_docs.py` beside them as the record of how they were made. Drop `run_extend.py`, `extras.py` and the Performance-tier responses.
  3. Hand-build three small edge cases as JSON, no network: `blank` (zero blocks), `corrupt_docx_processed` (one garbage block under 200 characters), `no_sections` (extract output with an empty `clauses` list and plain paragraphs).
  4. Correct `answers.json`: replace `assignment_allowed_without_consent` with `assignment_requires_consent: true` and `assignment_exceptions: ["merger or sale of substantially all assets"]` (plan section 3.5 explains why).
  5. `tests/ingest_fixtures.py`: `load_case(name) -> (extract_dict, parse_blocks, answers)` and `all_cases()`.
  6. Confirm no file contains an API key (`grep -r "sk_" tests/fixtures/ingest` prints nothing).
- **Done when:** `load_case` works for all seven cases in a test; `extend_eval/` is gone; no fixture file is larger than 300 KB; the suite passes.

---

## Phase 1: Schema

One agent, in order. Follow `playbook_implementation.md` section 1.1 for schema and namespace rules. Each migration has a working downgrade. Update the ORM models in the same task so models and migrations match. Do not run against the remote database.

### 1.1 Migration A: contract, version, clause, cascades

- **Depends on:** nothing. **Parallel with:** phases 0 and 2.
- **Owns:** one new migration file; `app/db/models/contract.py` (`Contract`, `ContractVersion`), `app/db/models/clause.py`, the `clause_id` columns in `app/db/models/analysis.py` and `redline.py`; `tests/unit/test_models.py` additions.
- **Do:** (details in plan section 7.3)
  1. `contract`: add `original_filename` (text, nullable), `status_reason` (text, nullable), `contract_type_source` (text, nullable, check in `user`, `extracted`). Replace `ck_contract_status` with `processing`, `failed`, `ready`, `analyzed`, `redlined`, `executed`. Add a foreign key from `contract_type` to `agreement_type.key`. Give `updated_at` an `onupdate` in the model.
  2. `contract_version`: add `file_sha256`, `file_size_bytes`, `page_count`, `source_format`, `original_filename` (all nullable); unique on (`contract_id`, `version_number`); index on `file_sha256`.
  3. `clause`: add `contract_version_id` (nullable for now, foreign key to `contract_version.id`), `clause_key` (UUID, not null, default `uuid4`; back-fill existing rows with `gen_random_uuid()`), `parent_id` (self foreign key, nullable), `level` (integer, not null, server default 1), `section_number`, `title`, `page_start`, `page_end`, `type_source` (text, not null, server default `none`, check in `extract`, `dictionary`, `none`), `text_sha256`. Checks: `char_end > char_start`, `char_start >= 0`, `level >= 1`. Index (`contract_id`, `clause_key`). Unique (`contract_version_id`, `ordinal`).
  4. `clause_family`: insert `preamble` and `signature_block` (category `structure`, empty synonyms), using the same insert pattern as migration `010`.
  5. Foreign keys `flag.clause_id` and `redline.clause_id` to `clause.id`, `ON DELETE SET NULL`.
  6. Recreate every foreign key that points at `contract.id` with `ON DELETE CASCADE`, and `clause_embedding.clause_id`, `clause.parent_id` and `clause.contract_version_id` likewise. List the tables by reading the models; there are about a dozen.
  7. `contract_version_id` stays nullable here because the old pipeline still writes clauses without it. Task 5.2 makes it not null.
- **Done when:** `alembic upgrade head --sql` renders without error for upgrade and downgrade; model tests assert the new columns, checks and cascade rules; the old pipeline's tests still pass; the suite passes.

### 1.2 Migration B: new tables and metadata columns

- **Depends on:** 1.1. **Parallel with:** phases 0 and 2.
- **Owns:** one new migration file; new model files `app/db/models/field.py` (`ContractField`), `party_link.py` (`ContractParty`, `ContractSignatory`), `ingest_run.py` (`IngestRun`); `ContractMetadata` and `Party` in `contract.py`; `ClauseEmbedding` in `clause.py`; `app/db/models/__init__.py`; `app/core/namespace.py` table list; model tests.
- **Do:** create the tables exactly as plan section 7.3 describes.
  1. `contract_field`: columns as listed there, `value` JSONB not null, checks on `source` (`extract`, `derived`, `user`) and `confidence` (`high`, `low` or null). Unique (`contract_version_id`, `field_key`, `source`). Index (`field_key`, `contract_id`). `clause_id` `ON DELETE SET NULL`.
  2. `contract_party`: `role` check (`own`, `counterparty`, `other`); unique (`contract_id`, `party_id`).
  3. `contract_signatory`.
  4. `ingest_run`: `status` check (`running`, `succeeded`, `failed`); `warnings` JSONB not null default `[]`.
  5. `party`: add `is_own_org` boolean not null default false.
  6. `clause_embedding`: unique on `clause_id`; add `model` text nullable.
  7. `contract_metadata`: add `contract_version_id`, `expiry_is_derived`, `initial_term_months`, `renewal_term_months`, `renewal_notice_days`, `dispute_resolution`, `total_value_amount` (numeric), `currency`, `liability_cap_amount` (numeric), `liability_cap_basis`, `payment_terms_days`, `termination_for_convenience`, `termination_notice_days`. Do not drop the old columns here; task 5.2 does.
  8. Add the four new tables to the namespace table list so the partition check knows them.
- **Done when:** upgrade and downgrade render with `--sql`; model tests cover every new table, constraint and index; `scripts/check_partition.py` tests still pass; the suite passes.

### 1.3 Repositories and reading rule

- **Depends on:** 1.2. **Parallel with:** phase 2.
- **Owns:** `app/db/repositories/clause_repo.py`, `contract_repo.py`, new `field_repo.py`, `ingest_repo.py`; their unit tests.
- **Do:**
  1. `clause_repo.get_clauses_for_contract(session, contract_id, *, level="top", version_id=None)`: defaults to the contract's current version and level 1. While `contract_version_id` is still null on old rows, treat null as "belongs to the current version" so existing behaviour is unchanged. `level="all"` returns every level. Apply the same default to `get_clauses_for_contracts`.
  2. `clause_repo.replace_clauses(session, contract_id, version_id, drafts) -> list[Clause]`: deletes the version's clauses and inserts the drafts, resolving `parent_ordinal` to `parent_id`, setting `text_sha256`.
  3. `field_repo`: `replace_extracted(session, contract_id, version_id, run_id, values)` (replaces `extract` and `derived` rows, never `user` rows); `values_in_force(session, version_id) -> dict[str, ContractField]` (`user` over `extract` over `derived`); `set_user_value(...)`.
  4. `contract_repo`: `upsert_party` using `INSERT … ON CONFLICT (normalized_name) DO NOTHING` then select; `replace_contract_parties`; `replace_signatories`; `write_metadata_projection(session, contract_id, version_id, values_in_force, registry_projection)`; `find_by_sha256(session, sha256)`.
  5. `ingest_repo`: `start_run`, `finish_run`, `fail_run`, `latest_run(version_id)`.
- **Done when:** unit tests with mocked sessions cover each function, including the "user row wins" rule and the null-version fallback; every existing caller of `get_clauses_for_contract` still passes its tests; the suite passes.

---

## Phase 2: Logic

Pure functions. No database, no network, no storage. Each task tests against the cases from task 0.3. Run in parallel.

### 2.1 Field registry and Extract schema

- **Depends on:** 0.2. **Parallel with:** 2.2–2.8.
- **Owns:** `document_processing/fields.py`, `tests/unit/test_dp_fields.py`.
- **Do:**
  1. `FieldDef(key, kind, tier, description, enum=None, projection=None, derived_from=None)`; `kind` in `string`, `integer`, `number`, `boolean`, `date`, `enum`, `string_list`.
  2. `REGISTRY`: every field in plan section 4. Tier 1 keys: `effective_date`, `expiry_date`, `initial_term_months`, `auto_renewal`, `renewal_term_months`, `renewal_notice_days`, `governing_law`, `dispute_resolution` (enum `litigation`, `arbitration`, `mediation`, `escalation` — `escalation` meaning an informal internal escalation or negotiation step required before formal proceedings), `dispute_venue`, `liability_cap_amount`, `liability_cap_basis`, `total_value_amount`, `currency`, `payment_terms_days`, `termination_for_convenience`, `termination_for_convenience_party` (enum `either`, `customer`, `vendor`), `termination_notice_days`. Tier 2 keys: `cure_period_days`, `notice_period_days`, `indemnification_cap_amount`, `liability_exclusions` (list), `assignment_requires_consent`, `assignment_exceptions` (list), `confidentiality_period_years`, `ip_ownership` (enum `customer`, `vendor`, `joint`), `non_compete_months`, `non_solicitation_months`, `sla_uptime_percent`, `sla_response_time_hours`, `warranty_period_days`, `breach_notification_hours`, `data_processing_agreement`, `gdpr_applicable`, `survival_clauses` (list), `insurance_required`, `exclusivity`, `most_favoured_customer`, `audit_rights`, `change_of_control_restriction`.
  3. `projection` names the `contract_metadata` column for the 16 projected fields (plan section 7.3).
  4. `build_extract_schema(agreement_type_keys, clause_family_keys) -> dict`: the Extend JSON schema. Top level: `title`, `contract_type` (enum from the argument), `parties[]` (`name`, `role_label`, `entity_type`, `jurisdiction`, `address`), `signatories[]` (`printed_name`, `title`, `party_name`, `is_signed`, `signed_date`), `clauses[]` (`section_number`, `title`, `family` as an enum from the argument; description: every top-level numbered section in order, no sub-clauses), and one property per registry field. Follow the schema rules in section 3. Descriptions must say "leave null if not stated" and, for `expiry_date`, "only if an explicit end date is written; do not compute". For `dispute_resolution`: "the mechanism that applies; if arbitration is excluded, do not answer arbitration" and use `escalation` when the contract requires an informal internal escalation or negotiation step before formal proceedings.
  5. `validate_value(field_def, raw) -> value | None`: coerces and rejects wrong types and out-of-enum values.
- **Done when:** the generated schema, built with the four agreement kinds and 31 family keys, equals a checked-in snapshot; a test asserts every primitive is nullable and every enum contains `null`; `validate_value` is tested for each kind; every `projection` name is a real `ContractMetadata` column once 1.2 lands (assert by name list until then); the suite passes.

### 2.2 Canonical text builder

- **Depends on:** 0.2, 0.3. **Parallel with:** 2.1, 2.3–2.8.
- **Owns:** `document_processing/canonical.py`, `tests/unit/test_dp_canonical.py`.
- **Do:** `build_canonical(parse_blocks: list[dict]) -> CanonicalDocument`, per plan section 5.2.
  1. Drop `footer` and `page_number` blocks.
  2. Drop running headers: any block whose normalised text equals a `header` block's text, and any block that is the first kept block on at least half the pages (minimum two pages) with identical text. Normalise by stripping markdown marks, case and whitespace.
  3. Clean kept blocks: strip leading `#` marks and `**`; close up line-break hyphens (`r"(\w)- (\w)"` → joined, only when the joined word is not otherwise split by a real hyphen-space pattern; keep it conservative and tested on "third- party"); replace private-use characters (``–``) at the start of a block with `-`; collapse internal whitespace runs except newlines inside tables.
  4. Join a `table` block to the previous one when it is the first kept block of its page and the previous kept block is a `table` ending the prior page: append its data rows, drop its separator row.
  5. Join kept blocks with `"\n\n"`. Record `char_start` and `char_end` for each, `-1` for dropped ones.
- **Done when:** for every fixture case, `text[b.char_start:b.char_end] == b.text` for each kept block; the header line "Halcyon Systems, Inc. - Confidential" and every footer are absent from the text of all four contract cases; the `msa_styled_docx` case has one fee table with four data rows; "third-party" has no stray space in `msa_runin_pdf`; `blank` yields empty text without error; the suite passes.

### 2.3 Segmentation

- **Depends on:** 0.2, 0.3. **Parallel with:** 2.1, 2.2, 2.4–2.8.
- **Owns:** `document_processing/sections.py`, `tests/unit/test_dp_sections.py`.
- **Do:** `segment(document: CanonicalDocument, hints: list[SectionHint]) -> tuple[list[ClauseDraft], list[str]]` (clauses and warnings), per plan section 5.3. Use only kept blocks.
  1. **Anchor.** For each hint in order, search forward from the previous anchor for the first block whose start matches the hint's number and title: optional `Article`/`Section` word, the number, optional `.`/`)`/`-`/`:`, then the title, compared case-insensitively with punctuation removed. If the hint has no number, match on title at the start of a block of at most 12 words. A match may be a heading block or the opening of a text block.
  2. **Title and heading.** `section_number` and `title` come from the hint. `heading_text` is the matched prefix as written in the text.
  3. **Fallback for an unanchored hint.** Skip it and add a warning `section_not_anchored:<number> <title>`.
  4. **No hints at all.** Segment by rule: a block starts a section if it opens with a section number followed by a title of at most 8 words ending in `.` or `:`, or is a heading block of at most 12 words that is not all capitals over 8 words. Mark these `anchored=False`. If nothing matches, return one clause covering the whole text.
  5. **Sub-clauses.** Inside a section, a block that opens with `(a)`–`(z)`, `(i)`-style roman in parentheses, or a number extending the section number (`6.1` in `6`, `6.1.2` in `6.1`) starts a child. A child runs to the next sibling or the end of its parent. Depth follows the numbering.
  6. **Preamble.** Text before the first section is one level 1 clause, `clause_type="preamble"`, `type_source="none"`, title `None`.
  7. **Signature block.** From the first `key_value` block after the last anchored section, or a block starting "IN WITNESS WHEREOF", to the end: one level 1 clause, `clause_type="signature_block"`.
  8. **Ranges.** Level 1 clauses partition the text from 0 to its end, in order; each ends where the next starts minus the separator. `text` is the exact slice. `page_start`/`page_end` from the blocks covered. `ordinal` is depth-first document order.
  9. Add warning `low_anchor_rate` when under 80% of hints were anchored.
- **Done when:** all four contract cases yield exactly 14 anchored sections with the numbers and titles in `answers.json`, plus one preamble and one signature block; no clause starts at "30 days", "90 days", "I." or the capitals disclaimer; section 2 and section 10 each have children `(a)` and `(b)`; `text == document.text[char_start:char_end]` for every clause; `no_sections` returns sensible output without error; a test with `6.1`/`6.2` sub-numbers nests correctly; the suite passes.

### 2.4 Clause typing

- **Depends on:** 0.2. **Parallel with:** 2.1–2.3, 2.5–2.8.
- **Owns:** `document_processing/clause_typing.py`, `tests/unit/test_dp_clause_typing.py`.
- **Do:** per plan section 5.4.
  1. `FamilyIndex(keys: set[str], synonyms: dict[str, str])`, where `synonyms` maps a lower-cased phrase to a family key. `FamilyIndex.from_rows(rows)` builds it from `clause_family` rows (key, name and each synonym). `async load_family_index(session)` reads the table; cache per process with an explicit `clear_family_index_cache()`.
  2. `clean_title(title)`: strip numbering, `Article N`, `Section N`, trailing punctuation; lower-case.
  3. `type_clause(draft, hint_family, index) -> ClauseDraft`: keep `preamble` and `signature_block` as set; else `hint_family` when it is in `index.keys` and not `other` (`type_source="extract"`); else exact synonym match on the cleaned title, then `rapidfuzz.fuzz.token_sort_ratio >= 80` (`"dictionary"`); else `other` (`"none"`).
  4. Compound titles: split the cleaned title on ` and `, `;`, `,`, `/`. Any part that maps to a family other than the chosen one is added to `issue_keys`.
  5. Sub-clauses (level 2+) inherit the parent's type with `type_source` of the parent unless their own title maps to a family.
- **Done when:** with an index built from the 31 keys and the synonyms in migration `010`, the cases in the status document's probe F type correctly ("ARTICLE 7 - INDEMNIFICATION", "Section 9. Confidentiality", "Data Security" → `security`, "Service Levels" → `service_levels`); the hint wins when valid and is ignored when not a known key; "Governing Law and Disputes" yields `governing_law` with `dispute_resolution` in `issue_keys`; no import of the old `clause_types.py`; the suite passes.

### 2.5 Mapping, evidence, checks, derived values

- **Depends on:** 2.1, 0.3. **Parallel with:** 2.2–2.4, 2.6–2.8.
- **Owns:** `document_processing/mapping.py`, `tests/unit/test_dp_mapping.py`.
- **Do:** per plan section 5.5.
  1. `map_fields(extract_value, extract_metadata, document, clauses) -> tuple[list[FieldValue], list[str]]`. For each registry field with a non-null value: validate with `fields.validate_value`; take the first citation's `referenceText` and page.
  2. Evidence: find the quote in `document.text` exactly; else with whitespace-insensitive matching mapped back to real offsets; prefer the occurrence on the cited page. Found → `confidence="high"` with offsets and the level 1 `clause_ordinal` containing it. Not found → quote and page kept, offsets null, `"low"`. No citation → `"low"`.
  3. Sanity checks, each dropping the value with a warning `dropped:<key>:<reason>`: dates outside 1990–2100; negative amounts or durations; `expiry_date` not after `effective_date`; percentages outside 0–100.
  4. Derived: when `expiry_date` is absent and `effective_date` and `initial_term_months` are present, add `expiry_date` with `source="derived"`, computed by calendar months, no quote.
  5. `map_parties(extract_value, document) -> list[PartyDraft]`: drop entries whose name is empty, equals its own role label, or is a bare role word (`customer`, `supplier`, `vendor`, `company`, `licensor`, `licensee`, `party`); de-duplicate on normalised name.
  6. `map_signatories(extract_value) -> list[SignatoryDraft]`.
  7. `map_hints(extract_value) -> list[SectionHint]`, `map_title`, `map_contract_type(extract_value, allowed_keys)` (null when not allowed).
- **Done when:** on the four contract cases every Tier 1 field in `answers.json` matches, with exact match for numbers, dates, booleans and enums and case-insensitive containment for free text; every `high` value satisfies `document.text[char_start:char_end] == quote`; `expiry_date` is `2028-03-03` with source `derived`; a test proves each sanity check and the party filter; the suite passes.

### 2.6 Parties and own-organisation matching

- **Depends on:** 0.2. **Parallel with:** 2.1–2.5, 2.7, 2.8.
- **Owns:** `document_processing/parties.py`, `tests/unit/test_dp_parties.py`.
- **Do:** per plan section 5.6.
  1. `normalize_party_name(name)`: lower-case, strip punctuation, collapse whitespace, drop a leading "the". Keep corporate suffixes.
  2. `assign_roles(parties, own_org_names) -> tuple[list[PartyDraft], list[str]]`: a party whose normalised name equals, or starts with, a normalised own-organisation name gets `own`; the first remaining party gets `counterparty`; the rest `other`. Warnings: `own_org_not_found` when the setting is non-empty and nothing matched (then no counterparty is assigned); `own_org_not_configured` when the setting is empty (then no roles are assigned; do not guess); `no_counterparty` when only our own organisation is present.
  3. `link_signatory(signatory, parties) -> int | None`: index of the party whose normalised name matches `party_name`.
- **Done when:** tests cover: own organisation listed first, listed second, absent, setting empty, three parties, "Halcyon Care, Inc." against a setting of "Halcyon Care"; signatory linking with capitals differences ("HALCYON SYSTEMS, INC."); the suite passes.

### 2.7 Invariants

- **Depends on:** 0.2. **Parallel with:** 2.1–2.6, 2.8.
- **Owns:** `document_processing/invariants.py`, `tests/unit/test_dp_invariants.py`.
- **Do:** `check_result(result: IngestResult, family_keys, registry) -> list[str]` returning violations for plan section 7.5 points 1 to 6: clause text equals its slice; level 1 clauses ordered, non-overlapping, covering the text with only whitespace between; children inside parents; every `clause_type` in `family_keys`, `preamble` and `signature_block` at most once; every field key in the registry with a valid value; every field with offsets matches its quote. `class InvariantError(Exception)` carrying the list. Points 7 to 9 are database-level and belong to task 3.1's tests.
- **Done when:** one passing case and one failing test per rule; the function never raises on malformed input, it reports; the suite passes.

### 2.8 Upload validation

- **Depends on:** nothing. **Parallel with:** 2.1–2.7.
- **Owns:** `document_processing/upload_validation.py`, `tests/unit/test_dp_upload_validation.py`.
- **Do:** `validate_upload(filename, data, max_mb) -> ValidatedUpload(source_format, sha256, size_bytes, safe_filename)`.
  1. Empty data → `AppError(400, "empty_file")`. Over the limit → `AppError(413, "file_too_large")`.
  2. Type from the first bytes: `%PDF-` → `pdf`; `PK\x03\x04` with a `word/document.xml` entry → `docx`. Anything else → `AppError(400, "unsupported_format")`. The extension is not trusted.
  3. `safe_filename`: base name only, characters outside `[A-Za-z0-9._ -]` replaced with `_`, no leading dots, at most 120 characters, extension forced to match the detected type.
- **Done when:** tests cover a PDF named `.docx`, a zip that is not a Word file, `../../etc/passwd.pdf`, an empty file, an oversized file and a normal file of each type; the suite passes.

### 2.9 Pure pipeline assembly and replay accuracy test

- **Depends on:** 2.1–2.7. **Parallel with:** phase 1.
- **Owns:** `build_result` in a new `document_processing/pipeline.py`; `tests/unit/test_dp_pipeline_replay.py`.
- **Do:**
  1. `build_result(extract_value, extract_metadata, parse_blocks, *, family_index, agreement_type_keys, own_org_names) -> IngestResult`: `build_canonical` → `map_hints` → `segment` → `type_clause` for each clause (hint family looked up by section number, then title) → `map_fields`, `map_parties` + `assign_roles`, `map_signatories`, `map_title`, `map_contract_type` → collect warnings → `check_result`, raising `InvariantError` on violations. Raise `NoTextError` when canonical text is under 200 characters.
  2. Replay test over all fixture cases, asserting the marks in plan section 2: Tier 1 field accuracy at least 85% per field across the four contract cases; at least 90% of expected sections found; at most one false split per document; typing at least 85%. `blank` and `corrupt_docx_processed` raise `NoTextError`.
- **Done when:** the replay test passes and prints a per-field accuracy table on failure; `pipeline.py` has no database, storage or network import; the suite passes.

---

## Phase 3: Orchestration and API

### 3.1 Ingest orchestrator

- **Depends on:** 0.1, 1.3, 2.8, 2.9. **Parallel with:** 6.1.
- **Owns:** `document_processing/ingest.py`, `tests/unit/test_dp_ingest.py`.
- **Do:** per plan section 5.1.
  1. `async create_contract(session, *, validated, data, paper_origin, contract_type, party_role, context, force=False) -> tuple[contract_id, version_id]`: duplicate check on `sha256` (`AppError(409, "duplicate_file", …)` unless `force`); insert `contract` (`status="processing"`, `title` and `original_filename` from `safe_filename`, `canonical_text=""`) and `contract_version` number 1 (`relation="version"`, `canonical_text=""`, file facts, object key `contracts/{contract_id}/v1/{safe_filename}`); set `current_version_id`; commit; then `storage.put`. If the put fails, mark the contract `failed` with `status_reason="storage_failed"`.
  2. `async run_ingest(session_factory, contract_id, version_id) -> None`: opens its own session. Starts an `ingest_run`. Reads the file from storage, uploads to Extend, runs Extract with the schema from `fields.build_extract_schema` (agreement kinds and family keys read from the tables), fetches parse blocks by `parse_run_id`. Stores the two raw responses at `contracts/{contract_id}/v1/extract.json` and `parse.json`. Calls `pipeline.build_result`.
  3. One transaction: `replace_clauses`; party upserts and `replace_contract_parties`; `replace_signatories`; `replace_extracted`; `write_metadata_projection`; update `contract` (`canonical_text`, `title` when Extract gave one, `counterparty_id`, `status="ready"`, `status_reason=None`), `contract_version` (`canonical_text`, `page_count`); finish the run with warnings, versions and credits. Commit.
  4. Contract type: keep a `user`-supplied value. Otherwise use the extracted one with `contract_type_source="extracted"`. Then fill `context.regimes` and `deal_value_band` with the existing `context_capture` helpers, as `service.py` does today.
  5. Failures: catch per kind, roll back, and in a fresh transaction set `status="failed"` with the `status_reason` from section 4.3 (`ExtendRunFailed` reasons mapped: `PASSWORD_PROTECTED_FILE` → `password_protected`, `FILE_TYPE_NOT_SUPPORTED` → `unsupported_format`, `FILE_SIZE_TOO_LARGE` → `too_large`, `CORRUPT_FILE`/`PARSING_ERROR` → `unreadable`; `NoTextError` → `no_text`; `ExtendTimeout` → `timeout`; `ExtendUnavailable` → `provider_unavailable`; anything else → `extraction_failed`) and fail the run. Never leave a contract in `processing`.
  6. `async extract_canonical_text(data, filename) -> str`: validate, upload, standalone parse, `build_canonical`; raises `NoTextError` under 200 characters.
  7. `async sweep_stale(session, older_than_minutes=15)`: marks `processing` contracts older than the limit as `failed`, reason `timeout`.
  8. Parsing and Extend calls are async; `storage.put/get` are synchronous, so wrap them in `asyncio.to_thread`.
- **Done when:** with `FakeExtendClient`, mocked sessions and in-memory storage, tests prove: the happy path writes every table and ends `ready`; each failure kind ends `failed` with the right reason and writes no clauses; a duplicate returns 409 and `force` bypasses it; a user-supplied contract type is kept; plan section 7.5 points 7 and 8 hold on the written rows; the raw responses are in storage; nothing imports the old `service.py`, `parsers.py`, `extraction.py`, `segmentation.py` or `clause_types.py`; the suite passes.

### 3.2 Embeddings at ingest

- **Depends on:** 1.3. **Parallel with:** 3.1.
- **Owns:** `app/services/repository/vector.py` (`embed_and_store_clauses` only), its tests; one call site in `ingest.py` added after 3.1 lands.
- **Do:** make `embed_and_store_clauses` idempotent (delete then insert per clause, or upsert on the new unique key), set `model` from the embedding setting, and accept an explicit clause list. In `run_ingest`, after the main commit, embed level 1 clauses except `preamble` and `signature_block`. An embedding failure adds the warning `embedding_failed` to the run and does not fail the contract. Run the model in `asyncio.to_thread`.
- **Done when:** a test shows running twice leaves one row per clause; ingest tests show embeddings written for the right clauses and a failure downgraded to a warning; the suite passes.

### 3.3 Documents API

- **Depends on:** 3.1. **Parallel with:** 3.4, 3.5, 3.6.
- **Owns:** `app/api/routes/documents.py`, `app/schemas/documents.py` (new), `tests/unit/test_documents_api.py`, the startup hook in `app/main.py`.
- **Do:** implement section 4.3 exactly.
  1. `POST`: validate `paper_origin`, `contract_type`, `party_role`, `context` with the existing `context_capture` validators; `validate_upload`; `create_contract`; schedule `run_ingest` with FastAPI `BackgroundTasks`; return 202.
  2. `GET /{id}`, `GET /{id}/clauses` (through `clause_repo`, not a direct query), `GET /{id}/text`, `POST /{id}/reprocess`.
  3. Response models in `app/schemas/documents.py`. Remove `ProcessedContract` from this route's imports.
  4. On application startup, call `sweep_stale`.
- **Done when:** route tests cover every status code in section 4.3; the clause list returns UUID `id` values; a `processing` contract returns empty lists; reprocess returns 409 when a flag exists; the route file has no import from the old pipeline; the suite passes.

### 3.4 Contract type from Extract; remove the model call

- **Depends on:** 3.1. **Parallel with:** 3.3, 3.5, 3.6.
- **Owns:** `document_processing/context_capture.py`, `app/core/llm/registry.py` (one key), `app/core/llm/prompts/contract_type_classify.md`, `app/core/llm/schemas/classification.py`, `tests/unit/test_context_capture.py`, `tests/unit/test_ci_guards.py`, the guard step in `.github/workflows/ci.yml`.
- **Do:**
  1. Delete `classify_contract_type`, its constants, the prompt file, the schema file (if nothing else uses it) and the `contract_type_classify` registry key. Remove the `core.llm` imports from `context_capture.py`. Keep the validators, `list_classifiable_agreement_types`, `derive_regimes` and `derive_deal_value_band`.
  2. Fix `tests/unit/test_ci_guards.py`: `_BACKEND` must point at the real `backend/` folder. Add an assertion that each guarded folder exists, so the guards cannot pass on a missing path again.
  3. Add guards in the test and in CI: `api.extend.ai` appears only under `app/core/extend/`; `core.extend` is imported only under `app/services/document_processing/`.
- **Done when:** the repaired guard tests pass and fail when a `core.llm` import is added to `document_processing` (prove it once, then remove the probe); no reference to `contract_type_classify` remains in `app` or `tests`; the suite passes.

### 3.5 Repoint `store_version`

- **Depends on:** 3.1. **Parallel with:** 3.3, 3.4, 3.6.
- **Owns:** `app/services/repository/service.py` (`store_version` and its helper only), its tests, the `_GET_STORAGE_TARGETS` tuple in `tests/conftest.py`.
- **Do:** replace the `parsers.parse` import with `ingest.extract_canonical_text`; replace `_source_format_from_filename` with `upload_validation.validate_upload`; fill the new `contract_version` file columns. Change nothing else about versioning. The first uploaded "new version" is now number 2, because ingest writes number 1; confirm the numbering code handles that.
- **Done when:** version tests pass with `FakeExtendClient`; `repository/service.py` has no import from `parsers`; behaviour is otherwise unchanged; the suite passes.

### 3.6 Downstream readers and analytics views

- **Depends on:** 1.3. **Parallel with:** 3.1–3.5.
- **Owns:** `backend/db/views.sql`, the view migration it needs (serial with other migrations), `app/services/analytics/service.py`, `app/services/drafting/frequency_tracker.py` (clause query only), `tests/unit/test_analytics_views_sql.py`.
- **Do:**
  1. Rewrite the views to read `contract_metadata.total_value_amount`, `currency`, `liability_cap_amount` and the other typed columns in place of `financial_fields->>…` and the `liability_cap` JSON. Follow the schema-naming rule for hand-written SQL.
  2. Update the analytics service and schemas to match.
  3. Move `frequency_tracker` onto the reading rule: current version, level 1.
  4. Read every other consumer of `contract_metadata` (`obligations/monitor.py`, `search_repo.py`, `contract_repo.py`, `smart_search.py`) and confirm it uses only columns that remain. Report any that do not; do not change their logic.
- **Done when:** `grep -rn "financial_fields\|milestone_dates\|liability_cap\b" backend/db backend/app/services/analytics` prints nothing; view SQL tests pass; the suite passes.

---

## Phase 4: Frontend

### 4.1 Frontend types, upload flow and readers

- **Depends on:** 3.3. May start earlier from section 4.3. **Not parallel with** playbook task 4.9.
- **Owns:** `frontend/lib/api/types.ts` (contract, clause and metadata types), `frontend/lib/api/hooks.ts` (the two upload mutations and the document queries), `frontend/components/intake/new-contract-slide-over.tsx`, `frontend/components/workspace/tabs/overview-tab.tsx`, `frontend/components/primitives/hover-card.tsx`.
- **Do:**
  1. Types to match section 4.3: `ContractDetail`, `ContractField`, `ContractPartyRow`, `Signatory`, `Clause` with `id`. Remove `ProcessedContract` and the old `ContractMetadata` keys (`parties`, `liability_cap`, `financial_fields`, `milestone_dates`, `extracted`, `notice_period_days`, `payment_terms`).
  2. Upload: on 202, poll `GET /api/documents/{id}` every 2 seconds until `ready` or `failed`, up to 5 minutes. Show progress while `processing`, a readable message per `status_reason` when `failed`, and offer the existing contract on 409.
  3. Overview and hover card read parties from `parties`, values from `metadata` and `fields`, and show evidence quotes where the design has room.
- **Done when:** type-check and lint pass; the frontend test suite passes; no file under `frontend/` references a removed key; an upload against a local backend with a fake client reaches the workspace (state in the report if this could not be run).

---

## Phase 5: Switch-over

Tasks 5.1 and 5.3 land together, because deleting the old parser breaks the seed parse test until it is rewritten.

### 5.1 Delete the old pipeline and its tests

- **Depends on:** 3.2–3.6, 4.1. **Lands with:** 5.3.
- **Owns:** every deletion in plan section 11.2 under "Application code", "Dependencies" and "Tests"; `tests/unit/test_no_legacy_document_processing.py` (new).
- **Do:** follow plan section 11.1 rules.
  1. Delete `parsers.py`, `extraction.py`, `service.py`, `segmentation.py`, `clause_types.py` from `document_processing/`.
  2. Delete `tests/unit/test_parsers.py`, `test_extraction.py`, `test_segmentation.py`, `test_document_service.py`, `test_clause_types.py`; remove the `ParsedDocument` case from `tests/integration/test_determinism.py`; remove the old `service.get_storage` entry from `tests/conftest.py`.
  3. Remove `pdfplumber` and `spacy` from `pyproject.toml`. Move `python-docx` out of the runtime dependencies and into both the `seed` group (the corpus builder needs it) and the `dev` group (the fixture generator needs it). Regenerate `uv.lock`.
  4. Fix every import that breaks. Callers are changed; no shims.
  5. Add the removal guard test: the five files do not exist; the searches in plan section 11.3 find nothing under `app`, `tests`, `scripts`.
  6. Old `ContractMetadata` attributes are removed from the model here, together with task 5.2's migration.
- **Done when:** the four searches in plan section 11.3 print nothing (the first excludes `seed/` for `python-docx` only); `uv sync` then the suite passes with `pdfplumber` and `spacy` not installed; the removal guard passes; `pytest seed/tests` passes once 5.3 is in.

### 5.2 Migration C: drop old columns

- **Depends on:** 5.1. Serial with other migrations. Destructive: needs the user's go-ahead before it is applied anywhere.
- **Owns:** one new migration; `ContractMetadata` and `Clause` models.
- **Do:** drop `contract_metadata.parties`, `financial_fields`, `milestone_dates`, `liability_cap`, `notice_period_days`, `payment_terms`, `extracted`. Delete all rows from `clause`, `clause_embedding` and `contract_metadata` that have no `contract_version_id` (plan section 7.4: existing contracts are re-ingested), then make `clause.contract_version_id` not null. The downgrade recreates the columns empty. State in the migration docstring that it deletes data.
- **Done when:** upgrade and downgrade render with `--sql`; model tests updated; `grep -rn "financial_fields\|milestone_dates\|notice_period_days" backend/app backend/db backend/tests frontend/lib frontend/components frontend/app` prints nothing; the suite passes.

### 5.3 Seed-side updates

- **Depends on:** 5.1. **Lands with:** 5.1. These are playbook-owned files; tell the user they are being changed.
- **Owns:** `backend/seed/tests/test_contracts_parse.py`, the module docstring of `backend/seed/contracts/build.py`.
- **Do:** rewrite the parse test so it no longer imports the old pipeline: assert 12 source files and 12 DOCX files exist, each DOCX opens with `python-docx`, and each has numbered headings. Segmentation of the corpus is now proved by task 6.2, not by this test. Update the builder's docstring, which describes the old segmenter's heading detection. Do not change the contracts or `expected.yaml`.
- **Done when:** `pytest seed/tests` passes with the old pipeline deleted; no file under `backend/seed/` imports a deleted module.

### 5.4 Planning and README updates

- **Depends on:** 3.3. **Parallel with:** 5.1–5.3.
- **Owns:** the documents listed under "Documents" in plan section 11.2.
- **Do:** rewrite the document processing parts of `development_docs/PRD.md` (FR-8, SC-1), `Architecture.md` (diagram 2 and the S1 notes), `Tech_Stack.md`, `Backend_Structure.md`, `Data_Model.md`, `API_Spec.md` (S1 section, from section 4.3 here), `Implementation_Plan_Backend.md` (mark T-020 to T-025 as superseded) and `backend/README.md`. Add a line at the top of `document_processing_status.md` saying it describes the code before this change. Mark the "Extract only" decision in `extend_ai.md` as replaced. In `playbook_implementation.md`, note under tasks 4.1 and 5.5 what section 5 here changed.
- **Done when:** `grep -rniE "pdfplumber|spacy|python-docx" development_docs backend/README.md` shows only lines that say they were removed; the zero-LLM statement for S1 is replaced by the "processed once, pinned, stored" rule everywhere it appeared.

---

## Phase 6: Verify

### 6.1 Field answers for the 12 seed contracts

- **Depends on:** nothing. **Parallel with:** everything. Content task, no code.
- **Owns:** `backend/seed/contracts/data/halcyon/fields_expected.yaml` (new).
- **Do:** read each file under `seed/contracts/data/halcyon/source/` and write, per contract: `title`, `contract_type` (from `expected.yaml`), both parties with role labels, the counterparty name (from `expected.yaml`), every Tier 1 field in plan section 4 with the value as written in the contract or `null` when the contract does not state it, signatories if present, and the ordered list of top-level sections with number, title and expected clause family. Use only keys that exist in `clause_family`. Do not edit the contracts.
- **Done when:** the file covers all 12 contracts; every value can be traced to a line in the source file (add the section number as a comment); a second read of three contracts chosen at random finds no error.

### 6.2 Corpus run against live Extend

- **Depends on:** 2.9, 6.1, the user's go-ahead and a key in `EXTEND_API_KEY`. Cost: about 12 contracts × 6 to 15 pages × 1.2 credits, under 250 credits. **Run this before phase 3 is finished.**
- **Owns:** `backend/seed/contracts/evaluate_ingest.py` (new, run as `python -m seed.contracts.evaluate_ingest`), `document_processing_verification.md` at the repository root.
- **Do:**
  1. For each of the 12 DOCX files: upload, Extract, fetch blocks, run `pipeline.build_result` with `own_org_names=["Halcyon Care"]`. No database writes. Keep the raw responses in memory only, except as in step 4.
  2. Compare with `fields_expected.yaml`: per-field accuracy, section recall, false splits, typing accuracy, counterparty correct or not, invariant violations, warnings, seconds and credits per contract.
  3. Also convert two contracts to PDF and run them, to cover the PDF path on real-length documents.
  4. With the user's agreement, save the responses for two contracts (one MSA, one DPA) into `backend/tests/fixtures/ingest/` as new replay cases with their answers, so sub-numbered multi-page contracts are covered in CI. This is a copy made by hand into the application's fixtures; the application tests still do not read the seed folder.
  5. Write the report with real numbers, including failures as they are.
- **Done when:** the report exists; each mark in plan section 2 is stated as met or not met; every miss is listed with a probable cause. Do not tune answers to hide failures. If a mark is not met, stop and report before phase 3 continues; list proposed logic changes separately.

### 6.3 Database and end-to-end check

- **Depends on:** 5.1–5.3 and the user's go-ahead to touch the remote database.
- **Do:** run `scripts/check_partition.py`; apply the migrations; start the backend; upload three seed contracts through the API (one own paper, one counterparty paper, one DPA); poll to `ready`. Check in the database: one `contract_version` numbered 1; clauses with `contract_version_id`; plan section 7.5 points 7, 8 and 9; `clause_embedding` rows for level 1 clauses; an `ingest_run` row with versions and credits. Upload the same file again and confirm 409. Upload a corrupt file and confirm `failed` with a reason. Delete one contract and confirm every child row is gone. Run `check_partition.py` again.
- **Done when:** each check is reported as passed or failed with the query used; nothing was written outside the project namespace.

### 6.4 Removal proof and close-out

- **Depends on:** 6.3.
- **Do:** run the four searches in plan section 11.3 and the full application and seed suites. Confirm the deleted files are absent and `pdfplumber` and `spacy` are not installed. Add the outcome to `document_processing_verification.md`. Tell the user that playbook task 5.4 can now run.
- **Done when:** every search prints nothing; both suites pass apart from the 4 known `test_llm_batch` failures; the report is complete.

## 7. Definition of done for the whole programme

1. A PDF or DOCX uploaded through the API reaches `ready` with clauses, fields with evidence, parties, signatories and embeddings, or reaches `failed` with a reason. Nothing stays in `processing`.
2. The marks in plan section 2 are met on the fixture set in CI and reported for the 12 seed contracts.
3. Every guarantee in plan section 7.5 holds and is tested.
4. No file, test, dependency or document from the old pipeline remains; the removal guard enforces it.
5. Versioning behaves as it did before, apart from the first upload being version 1.
6. The planning documents describe what is built.
