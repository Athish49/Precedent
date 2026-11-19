# Extend.ai — Contract Document Extraction

## Decision

**Replaced by `document_processing_plan.md`.** The "Extract only" decision below was superseded after a live test (`document_processing_plan.md` section 3.5): Extract alone gives no character offsets and does not return parsed text at all, so clause text and offsets cannot be built from it. The adopted design uses **Parse and Extract together** — fields come from Extract, text comes from Parse, and clause boundaries are cut by our own code anchored on Extract's section list over Parse's blocks. See `document_processing_plan.md` sections 1 and 3 for the reasoning and 5 for the pipeline. The API mechanics below (auth, upload, create run, poll, consume output, error handling) remain accurate and are still in use; only the "Extract only" architectural call is overridden.

Use **Extract** only (not Parse separately, not Split). Extract runs Parse internally, so one call gives structured fields. Contracts (MSA, NDA, etc.) have clear, consistent structure, so schema-based Extract is sufficient — no need to also call Parse directly.

- Base processor: `extraction_light`
- Underlying parse engine: `parse_light` (set via `config.parseConfig.engine`)
- Use **async** endpoint (`POST /extract_runs` + polling or webhook) for production. The sync `POST /extract` endpoint is for testing only (5-min timeout).

## Auth
```
Authorization: Bearer <EXTEND_API_KEY>
x-extend-api-version: 2026-02-09
```
Base URL: `https://api.extend.ai`

Workspace-scoped keys need nothing else. Org-scoped keys also need `X-Extend-Workspace-Id: ws_xxx`.

## Step 1: Upload file
```
POST /files/upload
Content-Type: multipart/form-data
field: file=<binary>
```
Response:
```json
{ "object": "file", "id": "file_xxx", "name": "contract.pdf", "type": "PDF" }
```
Use `file.id` in the next call. (Alternatively pass `file.url` directly if the doc is already hosted, skipping upload.)

## Step 2: Create extract run
```
POST /extract_runs
Content-Type: application/json
```
Payload:
```json
{
  "file": { "id": "file_xxx" },
  "config": {
    "baseProcessor": "extraction_light",
    "parseConfig": {
      "engine": "parse_light"
    },
    "schema": {
      "type": "object",
      "properties": {
        "contract_type": { "type": ["string", "null"], "description": "e.g. MSA, NDA, SOW" },
        "parties": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": ["string", "null"] },
              "role": { "type": ["string", "null"], "description": "e.g. Disclosing Party, Client" }
            }
          }
        },
        "effective_date": { "type": ["string", "null"], "extend:type": "date" },
        "term": { "type": ["string", "null"], "description": "Contract duration/term" },
        "governing_law": { "type": ["string", "null"] },
        "clauses": {
          "type": "array",
          "description": "Each distinct clause/section in the contract",
          "items": {
            "type": "object",
            "properties": {
              "title": { "type": ["string", "null"] },
              "text": { "type": ["string", "null"] }
            }
          }
        }
      }
    },
    "advancedOptions": {
      "citationsEnabled": true
    }
  }
}
```
- Adjust `schema.properties` per contract type as needed. For unseen/unknown contract types, omit `schema` entirely to auto-infer fields, or use `extractionRules` (plain-language string) to steer inference instead of a fixed schema.
- `citationsEnabled: true` returns bounding-box + source text per field (adds latency) — drop it if not needed.

Response (immediately, status will be `PROCESSING`):
```json
{ "object": "extract_run", "id": "exr_xxx", "status": "PROCESSING" }
```

## Step 3: Poll for result
```
GET /extract_runs/{id}
```
Poll until `status` is `PROCESSED` (or `FAILED`). Alternatively subscribe to the `Extract Run Processed` / `Extract Run Failed` webhook events instead of polling.

Response when done:
```json
{
  "object": "extract_run",
  "id": "exr_xxx",
  "status": "PROCESSED",
  "output": {
    "value": {
      "contract_type": "NDA",
      "parties": [{ "name": "Acme Corp", "role": "Disclosing Party" }],
      "effective_date": "2026-01-15",
      "term": "2 years",
      "governing_law": "Delaware",
      "clauses": [{ "title": "Confidentiality", "text": "..." }]
    },
    "metadata": {
      "contract_type": {
        "logprobsConfidence": 0.98,
        "ocrConfidence": 0.99,
        "citations": [{ "page": { "number": 1 }, "referenceText": "..." }]
      }
    }
  }
}
```
Note: `extraction_light` does **not** return `logprobsConfidence` (performance-tier only).

## Consuming the output
- `output.value` — the structured data, shaped exactly like `schema`. Use directly.
- `output.metadata[field]` — per-field `ocrConfidence` (0–1) and `citations`. Route low-confidence fields (e.g. `ocrConfidence < 0.9`) to manual review.

## Error handling
`failureReason` on `status: "FAILED"` — key ones: `UNABLE_TO_DOWNLOAD_FILE`, `FILE_TYPE_NOT_SUPPORTED`, `FILE_SIZE_TOO_LARGE`, `PASSWORD_PROTECTED_FILE`, `PARSING_ERROR`, `OUT_OF_CREDITS`.

## Reusable config (optional, skip for MVP)
To avoid resending the same `config` every call, save it once as an **Extractor** (`POST /extractors`) and reference it via `{"extractor": {"id": "ex_xxx"}}` instead of inline `config`. Not required to get started.

## SDK (Python)
```python
from extend_ai import Extend
client = Extend()  # reads EXTEND_API_KEY env var

file = client.files.upload(file=open("contract.pdf", "rb"))

run = client.extract_runs.create(
    file={"id": file.id},
    config={
        "baseProcessor": "extraction_light",
        "parseConfig": {"engine": "parse_light"},
        "schema": {...},
    },
)

# poll
run = client.extract_runs.retrieve(run.id)
```
