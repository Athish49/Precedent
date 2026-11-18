# Playbook status

Date: 2026-11-16. Scope: backend playbook service (S6), its consumers, the planning docs in `development_docs/`, and `backend/scripts/seed_playbooks.py`.

## Summary

- **The playbook never reaches a contract today.** Nothing in the app writes `contract.contract_type`, so `resolve()` is called with an empty string and returns zero rules. Seeding the database will not change review output until that is fixed.
- **The seed is valid but thin.** It would create 5 playbooks and 29 rules with no errors. Fallback language is empty on all 29 rules.
- **Two of the eight rule fields are dead.** `fallback_language` and `escalation_threshold` are stored and editable but no code reads them.
- **The gate thresholds do not match the score scale.** Scores are unbounded (a single flag scores at least 1.0); the gate auto-applies below 0.4 and escalates at 0.7. Every flagged contract escalates.
- **The playbooks page calls two endpoints with the wrong shape.** Resolve preview and bootstrap will both fail against the current backend.
- **Against the foundation model from the earlier research, the playbook scores 6 of 28 (21%).** This is my own rubric, described in section 6.

What was and was not verified:

| Claim | How it was checked |
|---|---|
| Seed data is valid | Built every rule as an ORM object and a `RuleCreate` model; 0 errors |
| Seed and playbook unit tests pass | Ran 84 tests across 6 files; all passed |
| Seed counts and coverage | Dry-run script over `_TEMPLATES`, no database |
| Seed has not been run | Confirmed later the same day by a read-only query: `playbook` and `playbook_rule` have 0 rows, as does every other table |
| Deleting a seeded playbook fails | From reading the code only; not run against Postgres |
| Frontend calls fail | From reading both sides; not run in a browser |

## 1. How the playbook is built

Two tables, defined in `backend/app/db/models/playbook.py` and migration `002_playbook_tables.py`.

**`playbook`**: `id`, `name`, `practice_area` (one of `hipaa`, `gdpr`, `saas_msa`, `nda`, `dpa`), `precedence`, timestamps.

**`playbook_rule`**: one row per clause type per playbook.

| Field | Type | Read by |
|---|---|---|
| `clause_type` | text | Join key to `clause.clause_type` everywhere |
| `preferred_language` | text | Layer 2 prompt, redline prompt, redline rationale |
| `acceptable_variations` | JSON list | Layer 2 prompt |
| `prohibited_terms` | JSON list | Layer 1 literal match |
| `required` | bool | Layer 1 missing-clause check |
| `risk_weight` | numeric | Scoring multiplier |
| `fallback_language` | text | **Nothing** |
| `escalation_threshold` | numeric | **Nothing** |

Supporting code:

- `services/playbook/service.py` and `api/routes/playbooks.py`: CRUD for playbooks and rules.
- `services/playbook/routing.py`: `resolve(contract_type)` picks playbooks by practice area and merges rules, highest precedence first, one winner per clause type.
- `services/playbook/bootstrap.py`: batch LLM job that mines preferred language and acceptable variations from executed contracts. It samples at most 5 clauses per type, 1,000 characters each.
- `services/document_processing/clause_types.py`: the clause taxonomy. 20 canonical types plus `other`, matched from headings by synonym dictionary and fuzzy match.

## 2. Downstream features

| Feature | What it takes from the playbook | Notes |
|---|---|---|
| Layer 1 structural analysis | `required`, `prohibited_terms` | Deterministic. Prohibited terms are matched as literal, case-insensitive substrings |
| Layer 2 content analysis | `preferred_language`, `acceptable_variations` | One LLM call per contract. Clauses without a rule are still assessed for risk and vagueness |
| Risk scoring | `risk_weight` | Score is the sum of severity base (1, 3 or 9) times weight |
| Redline generation | `preferred_language` only | Alternatives are written by the LLM, not taken from the playbook |
| Fallback toggle | Nothing | Swaps in the LLM's first alternative |
| Review gate | Nothing directly | Uses flag types, max severity and the aggregate score |
| Drafting cascade | Nothing | See section 4 |
| Negotiation memory | Nothing | Logs `preferred` or `fallback` per decision |
| Compliance check (obligations) | Nothing | No playbook reference in `services/obligations/` |
| Playbooks page | All fields | CRUD works; resolve preview and bootstrap do not (section 4) |

## 3. What the planning docs specify

Sources: `PRD.md` §3.2, `Data_Model.md` §6, `API_Spec.md` S6, `Architecture.md` diagram 7, `Implementation_Plan_Backend.md` T-035 to T-039.

- A unified store keyed by clause type: preferred language, acceptable variations, prohibited terms, fallback language, required flag, risk weight, escalation threshold.
- Practice-area routing that selects **all** applicable rule sets and merges them by precedence.
- The contract type signal comes from upload context or S1 metadata.
- Self-service CRUD.
- A one-time LLM bootstrap for preferred language and variations; prohibited terms come from the seed and human edits.
- Seed templates for NDA, DPA, SaaS MSA, HIPAA and GDPR with default prohibited terms, base rules and risk weights.
- S3 consumes "preferred + fallback language" from S6.
- Drafting cascade: playbook lookup, then frequency reuse, then LLM.
- Decision events record `preferred`, `fallback_1`, and so on.
- Versioning and audit are explicitly out of scope (`Architecture.md:298`).

The docs do **not** plan any of these: counterparty objections, talking points, give-gets, risk rationale, numeric thresholds, approver roles, risk zones, party side, jurisdiction, rule dependencies or rule-level tests.

## 4. Planned versus actual

| Planned | Actual | Status |
|---|---|---|
| Two tables with the documented columns | Matches `Data_Model.md` exactly | Done |
| CRUD API | All nine routes present | Done |
| Resolve endpoint | Present | Done, with caveats below |
| Bootstrap via batch LLM | Present; skips clause types that already have a rule | Done |
| Seed script with five templates | Present, tested | Done; not yet run (0 rows in the database) |
| Contract type from upload or metadata | `contract_type` is never written anywhere in `app/` | **Missing** |
| Route to all applicable practice areas | Identity mapping only: `saas_msa` resolves to the SaaS playbook and nothing else | **Missing** |
| Frontend multi-type resolve (`saas_msa+gdpr`) | Returns zero rules | **Missing** |
| S3 uses playbook fallback language | Only `preferred_language` is passed; `fallback_language` is never read | **Missing** |
| `position_offered` of `fallback_1`, `fallback_2` | Check constraint allows only `preferred` or `fallback` | Partial |
| Drafting: playbook lookup first | Service never queries the playbook; it returns "playbook" only if the caller passes `preferred_language`, and the frontend never does | **Missing** |
| Compliance check against playbook | No playbook use in the obligations service | **Missing** |
| `escalation_threshold` per rule | Stored, never read | Dead field |
| Gate thresholds on aggregate score | Score scale and thresholds do not match | Broken |

### Defects found while comparing

1. **Contract type is never set.** `document_processing/service.py:133` creates the contract without it, and no route updates it. The pipeline at `workflows/review_pipeline.py:35` and `contract_analysis/service.py:29` then resolves an empty string. Result: no missing-clause flags, no prohibited-term flags, no deviation flags, all weights default to 1.0, and redlines get no preferred language.
2. **Gate scale mismatch.** `scoring.py` returns a raw sum. With seed weights the smallest non-zero score on a governed clause is 2.0, and 1.0 on an ungoverned one. `gate.py:28` auto-applies below 0.4 and escalates at 0.7. `tests/unit/test_gate.py` feeds scores between 0.1 and 0.7, so the tests pass on a scale the scorer never produces. Auto-apply can only happen with zero flags, when there is nothing to apply.
3. **Resolve response shape.** The backend returns `{contract_type, applied_practice_areas, rules: {clause_type: rule}}`. The frontend types it as `ResolvedRule[]` with `source_playbook_id` and `source_playbook_name`, and calls `.map` on it (`frontend/lib/api/hooks.ts:214`, `playbooks/page.tsx:352`). Neither source field exists in the backend.
4. **Bootstrap request shape.** The frontend posts `{corpus: [...]}` and reads `created_count`. The backend requires `{playbook_id, contract_ids | contract_type}` and returns `created_rule_count`.
5. **Scale mismatch in the rule editor.** The form labels risk weight "0–1" and caps both risk weight and escalation threshold at 1. The seed uses weights of 2 to 10 and thresholds of 6 to 7.5.
6. **Deleting a playbook with rules.** The foreign key has no cascade and `delete_playbook` does not remove rules first, so deleting any seeded playbook should fail with a constraint error.
7. **PATCH cannot clear a field.** `service.update_rule` drops every `None`, so a threshold or fallback cannot be reset to empty.
8. **No uniqueness.** Nothing prevents two playbooks with the same name or two rules for the same clause type in one playbook. With duplicates, the merge winner depends on row order.
9. **`updated_at` never changes.** It has a server default but no update trigger.
10. **Seed command inconsistency.** The script header says `python -m scripts.seed_playbooks`; the README says `python scripts/seed_playbooks.py`. Both should work, because `app` is installed into the virtualenv.

## 5. Seed robustness and coverage

All numbers come from a dry run over `_TEMPLATES`; nothing was written to a database.

### Volume

| Playbook | Area | Precedence | Rules | Required | Variations | Prohibited terms | Clause types covered |
|---|---|---|---|---|---|---|---|
| NDA Standard | nda | 10 | 5 | 3 | 9 | 9 | 5 of 20 |
| DPA Standard | dpa | 10 | 5 | 4 | 8 | 10 | 5 of 20 |
| SaaS MSA Standard | saas_msa | 10 | 7 | 6 | 12 | 16 | 7 of 20 |
| HIPAA Standard | hipaa | 15 | 6 | 6 | 7 | 17 | 6 of 20 |
| GDPR Standard | gdpr | 15 | 6 | 6 | 10 | 13 | 6 of 20 |
| **Total** | | | **29** | **25** | **46** | **65** | **15 of 20 distinct** |

### Field fill rates (29 rules)

| Field | Filled | Rate |
|---|---|---|
| `preferred_language` | 29 | 100% |
| `acceptable_variations`, at least one | 29 | 100% |
| `acceptable_variations`, at least two | 17 | 59% |
| `prohibited_terms`, at least one | 22 | 76% |
| `required = true` | 25 | 86% |
| `escalation_threshold` | 13 | 45% |
| `fallback_language` | 0 | 0% |

### Content depth

- Preferred language: 1,113 words in total; median 38 words per rule, range 24 to 53.
- Acceptable variations: 1.59 per rule; median 9 words each. These are one-line summaries, not alternative clause text.
- Prohibited terms: 2.24 per rule; 63 distinct. Median length is 4 words, and 59 of 65 are three words or longer.
- Risk weights: range 2 to 10, median 7.
- 13 of 29 rules contain a number or duration in the preferred text; none store it as a structured value.
- One variation contains an unfilled placeholder: "Total liability shall not exceed $[X]."

### Taxonomy coverage

- Five canonical types have no rule in any playbook: `amendment`, `assignment`, `definitions`, `force_majeure`, `insurance`.
- WorldCC's three most negotiated terms are limitation of liability, price and indemnification. Only the SaaS MSA playbook covers all three. HIPAA covers indemnification only. NDA, DPA and GDPR cover none.
- The SaaS MSA playbook has no rule for confidentiality, data protection, governing law or term.

### Robustness

What holds up:

- 0 validation errors; 0 unknown keys; every clause type is canonical.
- 0 duplicate clause types within a playbook.
- 0 prohibited terms collide with the same rule's own preferred or acceptable text.
- Idempotent by playbook name, with one commit per playbook.

What does not:

- **Idempotency is name-only.** Editing a template after the first run changes nothing; there is no upsert or template version.
- **Precedence is inert.** HIPAA and GDPR are set to 15 to override the base playbooks, but identity routing means only one playbook ever resolves. HIPAA and GDPR also tie at 15.
- **Prohibited terms are literal phrases.** They match only if the contract uses those exact words, and they also match when the phrase is negated.

To show the last point I ran the real `run_layer1` over 22 sentences I wrote myself. This is an illustration of the mechanism, not a statistical sample.

| Probe set | Result |
|---|---|
| Risky clauses, mostly worded differently from the seed phrase | 4 of 18 flagged |
| Benign clauses that negate a seed phrase | 4 of 4 wrongly flagged |

Example miss: "Provider's liability under this Agreement shall be unlimited." Layer 2 may still catch the misses, but only Layer 1 flags are hard stops in the gate.

The four benign sentences that were wrongly flagged, which task 4.3 in `playbook_implementation.md` uses as a regression check:

1. "Nothing in this Agreement shall impose unlimited liability on either party."
2. "This clause shall not be construed as a waiver of confidentiality."
3. "This Section shall not be read as granting no termination right to Customer."
4. "The parties acknowledge that HIPAA compliance optional language has been removed."

## 6. Benchmark if the seed runs

### Database after seeding

| Measure | Value |
|---|---|
| `playbook` rows | 5 |
| `playbook_rule` rows | 29 |
| Rules per playbook | 5 to 7, mean 5.8 |
| Share of the app's 20 clause types governed, per contract type | 25% to 35% |
| Rules with fallback language | 0 |
| Rules reaching an uploaded contract today | 0, because contract type is never set |

### What a resolved contract would see, once contract type is wired

| Contract type | Rules | Required | Score if every required clause is missing |
|---|---|---|---|
| `nda` | 5 | 3 | 198 |
| `dpa` | 5 | 4 | 270 |
| `saas_msa` | 7 | 6 | 396 |
| `hipaa` | 6 | 6 | 450 |
| `gdpr` | 6 | 6 | 378 |
| empty, `msa`, `saas_msa+gdpr`, anything else | 0 | 0 | 0 |

For comparison, the gate thresholds are 0.4 and 0.7.

If multi-area routing existed, `saas_msa + gdpr` would merge to 12 rules and `saas_msa + gdpr + dpa` to 13.

### Against the foundation model

The rubric is the 28 elements from the earlier research: 8 header fields, 12 clause-record fields, 3 guardrail elements and 5 governance elements. Full support scores 1, partial 0.5. The weighting is mine.

| Layer | Elements | Full | Partial | Absent |
|---|---|---|---|---|
| Playbook header | 8 | 1 (agreement type) | 0 | 7 |
| Clause record | 12 | 1 (preferred position) | 5 | 6 |
| Guardrails and authority | 3 | 0 | 1 | 2 |
| Governance | 5 | 0 | 2 | 3 |
| **Total** | **28** | **2** | **8** | **18** |

Score: 6 of 28, or 21%.

Partial items:

- **Taxonomy:** one level, free text, no validation against the canonical list.
- **Fallback ladder:** a single text field, unused and unseeded.
- **Red lines:** literal phrases, not testable conditions.
- **Detection guidance:** acceptable variations only.
- **Escalation:** a numeric field with no approver or zone, unused.
- **Zones:** the gate is binary (auto-apply or escalate) and global.
- **Deviation log:** `decision_event` records outcomes but not which rule or rung.
- **Layered inheritance:** the precedence merge is coded but never has more than one input.

Absent entirely: party side, jurisdiction, owner, effective dates, version, risk rationale, numeric thresholds, counterparty objections, give-gets, dependencies, provenance, a global prohibited list, an approval matrix, change log, and per-rule test cases.

## 7. Suggested order of work

This list was written before the target design existed. The agreed target is in `playbook_plan.md` and the full task breakdown is in `playbook_implementation.md`; where they differ from this list, they take precedence. Later checks also found that the database and storage are not partitioned by project, that storage falls back to a local folder, and that seed code sits outside a dedicated folder. Those findings are recorded in `playbook_plan.md` sections 10 and 11.

1. Set `contract_type` at upload, or classify it in document processing. Nothing else matters until rules resolve.
2. Normalise the risk score, or move the gate thresholds to the scorer's scale, and fix the gate tests to match.
3. Fix the resolve and bootstrap contracts between frontend and backend, and the 0–1 limits in the rule editor.
4. Wire `fallback_language` into redline generation and the toggle, then fill it in the seed.
5. Implement multi-area routing so the HIPAA and GDPR overlays apply on top of a base playbook.
6. Add cascade on playbook delete and a unique constraint on playbook and clause type.
7. Extend the schema toward the foundation model: fallback ladder, structured thresholds, objections, approver and zone, rule versioning.
