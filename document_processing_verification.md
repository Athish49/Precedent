# Document processing verification: live Extend corpus run (task 6.2)

Date: 2026-11-18. Companion to `document_processing_plan.md` section 2 (the
"good enough" marks) and `document_processing_implementation.md` section
6.2. Produced by running `backend/seed/contracts/evaluate_ingest.py`
against the real Extend API, using the real `EXTEND_API_KEY` already placed
in `backend/.env` by the user, with `own_org_names=["Halcyon Care"]`. No
database writes happened at any point. The key was never printed or logged.

The numbers below come from two passes: the live corpus run itself (12
DOCX contracts + 1 PDF contract, billed), and a second, **free** pass that
re-fetches each already-completed run's output (`GET /extract_runs/{id}`
and `GET /parse_runs/{id}`, both reads of data already paid for) and
re-runs the pure `pipeline.build_result` locally with a fixed
section-matching scorer (the first version of the scorer had a latent bug
— see section 3 for what it was and, importantly, that fixing it did not
actually change any number in this report). No new Extract runs were
issued to produce any number below.

**Bottom line: a hard blocker was found and worked around locally (not
fixed in the owning module). Of plan section 2's five marks: three are
NOT MET on the live corpus, two were not evaluated by this run at all
(Tier 2 field accuracy, and failure handling — no corrupt/blank file was
in this corpus), and none is confirmed MET.** Per the implementation
doc's own done-when clause, this report stops here — phase 3 should not
be treated as validated by this run until the issues below are resolved
by the coordinator/user.

## 0. Update, 2026-11-18: fixes applied and confirmed

Everything proposed in section 9 below was implemented (by two agents working
on `fields.py`/`mapping.py` and `sections.py` respectively, with no network
calls), then confirmed against a small, targeted live re-run — 4 of the 12
contracts (3, 8, 9, 10), not the full corpus — rather than re-running
everything. Full application suite: 1741 passed, 0 failed after the fixes.
**This is a historical snapshot at this exact point in the programme, not
the final count** — later phases (orchestration, API, frontend, then
deleting the old pipeline in phase 5) added and removed tests, net fewer;
the final, current count is 1675 passed, 0 failed, recorded in section 13.3.
An earlier version of this document did not make this distinction clear,
which an independent audit correctly flagged as a number that "doesn't
reproduce" — it was never wrong, just a mid-programme figure read as if it
were the final one.

Confirmed on fresh live calls:
- **The schema blocker (section 1) is fixed.** All 4 live Extract calls
  succeeded with no 400, using `fields.build_extract_schema`'s output
  verbatim, no workaround.
- **The false-split bug (section 5.3, change #9) is fixed.** Extract
  reproduced the exact duplicate-hint condition live on both contracts 3 and
  9; the corrected regex produced a benign `section_not_anchored` warning
  instead of a spurious clause in both cases. 0 false splits on both.
- **The appendix/exhibit/schedule/annex recall gap (section 5.1a, change #3)
  is fixed, confirmed via both mechanisms independently:** the updated
  `clauses[]` schema description made Extract itself hint all of contract
  8's 9 schedules and contract 9's 6 schedules by their non-numeric labels
  on the live calls; a free replay of the original (pre-fix) hint-less
  output confirmed `sections.py`'s new fallback-detection pass also catches
  every one of them on its own. True recall is 31/31 (contract 8) and 30/30
  (contract 9) — see the next item for why the live run's own scorer first
  reported 30/31 and 29/30.
- **A pre-existing bug in `evaluate_ingest.py`'s scorer** (not one of the
  original findings — found during the confirmation run) undercounted
  recall by exactly one on contracts 8 and 9: `_match_sections`'s candidate
  pool excluded every `signature_block`-typed clause, but a trailing
  schedule can legitimately type as `signature_block` via its own Extract
  hint family (e.g. "Schedule D: Signature and Execution"), so such a
  clause could never match its own named expected entry even though the
  pipeline found it correctly. Fixed in `evaluate_ingest.py` by including
  `signature_block`-typed clauses in the matching pool (the generic
  `has_signature` presence check used for the dedicated `"signature"`
  sentinel entry does not consume from that pool, so the two cannot
  conflict). This is a fix to the evaluation script only, not to the
  pipeline itself.
- **Contract 10's termination_for_convenience miss is fixed on this call**
  (Extract now correctly returns `True`/`"either"` for §12.11) — flagged at
  the time as a best-effort, not-guaranteed prompt improvement, and it held
  on this one re-run (n=1, not proof of determinism for an LLM-backed API).

**One tension was found to be inherent, not a bug, and is accepted as a
known limitation rather than further "fixed":** the leave-null-vs-infer-false
convention change for `termination_for_convenience`/`auto_renewal` (section
9, change #4) improved contract 10's case but, on the same confirmation run,
produced the opposite-direction miss on contracts 8 and 9 (expected `null`,
got `False`/`True`). Real documents genuinely split both ways on this
convention; no further prompt wording closes both directions at once
without reopening the other. Accepted as-is.

With this update, every mark from plan section 2 that was previously NOT MET
due to the three fixed bugs should be re-evaluated as part of any future
full-corpus run (not re-run here, per the "small/targeted, not all 12"
instruction) — the per-contract numbers in sections 4-6 below are the
**original, pre-fix** numbers and are left unchanged below as the historical
record of what task 6.2 found; they are superseded for contracts 3, 8, 9, and
10 by the confirmation above, but have not been re-measured for contracts 1,
2, 4, 5, 6, 7, 11, 12.

## 1. Blocker found: `fields.py`'s Extract schema is invalid JSON Schema

`app/services/document_processing/fields.py::build_extract_schema` (task
2.1, already "done and tested" per unit tests, which never make a live
call) produces a schema that the real Extend API rejects outright with
`400 INVALID_REQUEST`. Three concrete, live-confirmed defects, all in
`_field_schema` / `build_extract_schema`:

1. **Enum-as-type.** Every enum property (`dispute_resolution`,
   `termination_for_convenience_party`, `ip_ownership`, and the inline
   `contract_type` and `clauses[].family` properties) is built as
   `{"type": [*values, None], ...}` — i.e. the enum's literal string values
   are put directly into the JSON Schema `type` array, where only
   primitive type names belong. Confirmed live error: `"Invalid type
   array. Only combinations of a primitive type and null are supported
   (e.g. [\"string\", \"null\"]); Path: config.properties.contract_type"`.
   Correct shape, confirmed accepted: `{"type": ["string", "null"], "enum":
   [...values, null]}`.
2. **Nullable array.** Every array property (`parties`, `signatories`,
   `clauses`, and every `string_list` field) is built as `{"type":
   ["array", "null"], ...}`. Extend rejects `["array", "null"]` with the
   same "Invalid type array" message. A bare `"type": "array"` is accepted;
   `"nullable": true` is rejected separately as an unsupported property.
   There is no supported way to make an array property itself nullable on
   this API.
3. **Nullable array item.** `string_list` fields additionally build
   `"items": {"type": ["string", "null"]}`. Extend rejects this too:
   `"Array items must have a type property. Array items type must be one
   of: string, number, integer, boolean, object"`. An array item's own
   type cannot be a nullable list (a nullable *property inside an object
   item*, e.g. `parties[].name`, is fine and was left untouched — only a
   bare primitive item type is affected).

**None of these were fixed in `fields.py`** — that file is owned by task
2.1, and file-ownership rules forbid editing another task's file here.
Instead, `evaluate_ingest.py` carries a local, script-only
`_fix_enum_schema()` that rewrites the schema after calling
`build_extract_schema()` and before sending it to Extend, with each defect
documented in its docstring and the live error bodies quoted. This was
necessary to run the corpus at all: without it, every one of the 12
contracts fails after ~0.5-0.9s with a 400 before even reaching the Extend
processor (confirmed — this is exactly what happened on the first attempt
at this task, before the schema bug was found).

**Downstream consequence for `mapping.py`, once `fields.py` is properly
fixed:** because array properties cannot be null, Extend will return `[]`
rather than `null` for a `string_list` Tier 2 field (`liability_exclusions`,
`assignment_exceptions`, `survival_clauses`) when nothing is stated.
`mapping.py::map_fields` only skips a field when the raw value `is None`
(`if raw is None: continue`); an empty list is not `None`, so it would
proceed to `validate_value` (which explicitly returns `[]` rather than
treating it as absent — see its own docstring, "may be empty list; callers
may treat `[]` as None if desired") and get stored as a real `FieldValue`
with `value=[]`. Whoever fixes `fields.py` should also add an
empty-list-means-absent check in `map_fields`, or this will store a
value for every Tier 2 list field on every contract, stated or not.

**This is a real bug in `fields.py` that must be fixed there before any
other live-Extend-dependent task (6.3, and ultimately `ingest.py` in task
3.1) can work.** It was invisible to task 2.1's own unit tests because
none of them make a live call (correctly, per the "no network in tests"
rule) — this is precisely the kind of problem 6.2 exists to surface before
phase 3 is built on unverified logic. Two more things worth flagging to
whoever fixes it: `tests/unit/test_dp_fields.py` snapshot-tests the
generated schema, so that snapshot will need regenerating against the
corrected shape; and `document_processing_implementation.md` section 3's
"Schema rules" row should gain the array rules confirmed here (a bare
`"array"` type, and array items with a bare primitive type) so the next
person who touches this code has them written down.

## 2. What ran

- All 12 seed DOCX contracts under `seed/contracts/data/halcyon/docx/`:
  upload → Extract (schema from `fields.build_extract_schema`, patched as
  above) → `parse_output` → `pipeline.build_result` with
  `family_index` built from the real migrations 010 + 016 (31 keys,
  same technique as `tests/unit/test_dp_pipeline_replay.py`),
  `agreement_type_keys=["nda","saas_msa","dpa","vendor_msa"]`,
  `own_org_names=["Halcyon Care"]`.
- One of the two planned PDF-path contracts:
  `07_dpa_counterparty_subprocessor_breach.docx`, converted to PDF with
  LibreOffice (`soffice --headless --convert-to pdf`, found at
  `/opt/homebrew/bin/soffice`) and run the same way. It is scored
  separately below as a DOCX-vs-PDF comparison, not folded into the
  12-contract corpus numbers.
- **The second planned PDF contract (`01_saas_msa_own_clean`) was NOT
  run.** See "Cost" below for why, and "What was not done" for the honest
  accounting.
- `build_result` raised **zero** `InvariantError`s and **zero**
  `NoTextError`s across all 13 real runs (12 DOCX + 1 PDF). Every run
  reached `status=ok`. This is a genuinely positive result: the pipeline's
  own guarantees (plan section 7.5, points 1-6) held on every real,
  multi-page, sub-numbered contract in the corpus — something the earlier
  3-page synthetic test (plan section 3.5) could not demonstrate.
- No fixtures were saved to `backend/tests/fixtures/ingest/`. See section 7.

## 3. Methodology, and a scoring bug caught and fixed mid-task

- **Field accuracy**, per Tier 1 key: integer/number compared with
  tolerance (number fields allow 1%, or a number is extracted from a
  descriptive expected string and compared to that, see "known scoring
  caveats" below); boolean with `is`; date as ISO string equality; string/
  enum/string_list by case-insensitive containment or >=30% token overlap
  (same method `tests/unit/test_dp_pipeline_replay.py` already uses for the
  four-case replay fixture). `expiry_date` is special-cased: `derived`
  values are scored as a match when the expected answer is `null`, because
  `fields_expected.yaml` deliberately records only an explicit stated date
  (task 6.1's own rule) while the pipeline *correctly* derives `expiry_date`
  from `effective_date` + `initial_term_months` per plan section 5.5 point
  4 — that is intended system behaviour, not a miss.
- **Section recall, false splits, typing**: `fields_expected.yaml`'s
  `sections` list per contract is matched against the result's level-1
  clauses **one-to-one**: a clause consumed by one expected entry is
  removed from the candidate pool and cannot also satisfy a second.
  Matching prefers an exact normalised section-number match whose title
  isn't wildly wrong (a loose `rapidfuzz` sanity check), then falls back
  to the best fuzzy title match (`token_sort_ratio >= 75`) for non-numeric
  labels (`exhibit_a`, `schedule_1`, `annex_1`). `preamble` and `signature`
  are matched against presence of a `preamble`/`signature_block`-typed
  clause. A level-1 clause not consumed by any expected entry counts as a
  false split. Typing accuracy is scored only over expected sections whose
  `clause_family` is one of the 31 real taxonomy keys, per the plan's own
  rule — reported two ways below (over all expected taxonomy sections, and
  restricted to only the ones that were anchored, to separate segmentation
  failures from typing failures).
- **The first version of this matcher had a latent one-to-many bug**,
  caught during review before this report was finalised: it looked a
  clause up by number alone, with no title check and no removal from the
  pool, so one clause could in principle silently satisfy more than one
  expected entry. It was fixed in `evaluate_ingest.py::_match_sections`
  (now one-to-one, with a title sanity check on number matches) before
  this report was finalised. **Checked directly: the fix changed zero
  per-contract numbers** for any of the 12 DOCX contracts (every
  sections/typing/false-split figure below is identical before and after
  the fix) — the bug was real and worth fixing for future runs, but it
  happened not to have actually inflated anything in this particular
  corpus. (The one case that looked, on first read, like exactly this bug
  in action — contract 7's section 9 — turned out to be a correct match
  for an unrelated reason: see section 5's note on duplicate Extract
  hints.)
- **Two methodology decisions made after seeing the raw matches, disclosed
  here in full:**
  1. **Section recall is scored per document, not as a corpus-wide
     aggregate.** `test_dp_pipeline_replay.py` — the codebase's own
     existing reading of this mark for the four-case fixture — applies
     `found_rate >= 0.90` to each case individually, not to a pooled
     total. An earlier draft of this report scored the pooled aggregate
     (90.4%, "MET") and missed that 5 of the 12 documents individually
     fall below 90% recall. Switching to the per-document reading is what
     turned this mark from MET to NOT MET; the matcher fix above did not
     change this (or any other) mark.
  2. **The PDF run is scored separately from the 12 DOCX contracts**,
     rather than pooled in as a 13th data point. Checked directly: this
     flips no mark's MET/NOT MET verdict. The shifts in the per-field and
     typing percentages between pooling and not pooling it are plain
     arithmetic, not a difference in what the PDF run itself got right or
     wrong: the DOCX run for contract 7 *also* missed the same
     `liability_cap_basis` citation (it is one of the two
     `liability_cap_basis` misses counted in both the pooled and
     unpooled tables), and both the DOCX and PDF runs for contract 7
     typed exactly 22 of 28 sections correctly — `annex_3` makes no
     difference to the typing count because the DOCX run anchored it but
     typed it wrong (`notices` instead of `other`; see section 5.2), while
     the PDF run never anchored it at all (see section 6). Pulling one
     run below the 12-contract pool's own rate for a given field (as the
     PDF run's 78.6% section-typing rate for contract 7 sits below the
     12-DOCX pool's 83.9%) mechanically raises that field's or that
     metric's rate when removed, and pulling out a run that scored a
     field *correctly* mechanically lowers that field's rate — which is
     exactly the mixed-direction pattern seen in `liability_cap_basis`
     (rises when the PDF is removed) versus `dispute_resolution`,
     `auto_renewal`, `effective_date`, and `termination_notice_days` (each
     falls slightly). Keeping the 12-DOCX corpus as the clean denominator
     is more defensible regardless of this arithmetic, given the task
     describes a 12-contract corpus with the PDF path as a supplementary
     check — but it is not simply
     "stricter."
- **Counterparty**: the `role="counterparty"` party's name, matched
  against `fields_expected.yaml`'s `counterparty` by the same fuzzy
  text-match rule used for free-text fields.
- This methodology is honest but imperfect — see "Known scoring caveats"
  at the end. It was written once, mostly before looking at results; the
  one change made after seeing results was the matcher bug fix above,
  which made every number *stricter*, never more favourable.

## 4. Results against plan section 2's marks

Plan section 2 lists five marks. This run's result against each, stated
plainly: **three NOT MET, two not evaluated, zero confirmed MET.**

| Mark | Required | Actual (12 DOCX contracts) | Met? |
|---|---|---|---|
| Tier 1 field accuracy, per field | >=85% | see table below | **NOT MET** (7 of 17 fields below 85%) |
| Tier 2 field accuracy | >=70%, blank ok, no confident wrong value | not scored this run (see "What was not done") | **not evaluated** |
| Top-level clause boundaries: found, AND at most one false split per document | >=90% found per document; <=1 false split per document | found: **5 of 12 documents below 90%** (aggregate 275/304 = 90.5%, but the mark is per-document); false splits: max 1 (contracts 3 and 9 each had exactly 1; all others 0) — **this is one combined mark, and it fails as a whole on the found-rate half even though the false-split half independently holds** | **NOT MET** |
| Clause typing accuracy | >=85% | 255/304 = **83.9%** (but 255/275 = 92.7% when restricted to sections that were anchored — see section 5) | **NOT MET** |
| Failures give a clear error, never a stored empty contract | — | 0/13 runs failed; `NoTextError`/`InvariantError` never triggered, but no corrupt/blank/oversized file was in this corpus to exercise the failure paths at all | **not evaluated** |

### Per-contract table (12 DOCX, the primary corpus)

`seconds` is client-side wall-clock time, measured in the evaluation
script from the start of the upload call through fetching the parse
blocks (upload + Extract run + poll-to-completion + parse fetch). It is
not Extend's own server-side processing time (see section 6 for that
distinction on the one contract where both were measured).

| # | file | pages | seconds | credits | fields | sections | false splits | typing | counterparty | invariant violations |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 01_saas_msa_own_clean | 14 | 33.5 | 16.8 | 14/17 | 34/34 (100%) | 0 | 32/34 | correct | 0 |
| 2 | 02_saas_msa_own_midmarket_yellow | 14 | 29.7 | 16.8 | 15/17 | 34/34 (100%) | 0 | 32/34 | correct | 0 |
| 3 | 03_saas_msa_hipaa_counterparty_hospital_red | 14 | 29.4 | 16.8 | 12/17 | 33/33 (100%) | 1 | 30/33 | correct | 0 |
| 4 | 04_saas_msa_gdpr_counterparty_euclinic_yellow | 13 | 29.7 | 15.6 | 14/17 | 16/19 (84%) | 0 | 16/19 | correct | 0 |
| 5 | 05_saas_msa_counterparty_strategic | 13 | 32.8 | 15.6 | 15/17 | 16/19 (84%) | 0 | 16/19 | correct | 0 |
| 6 | 06_dpa_gdpr_own_clean | 12 | 23.2 | 14.4 | 17/17 | 17/20 (85%) | 0 | 15/20 | correct | 0 |
| 7 | 07_dpa_counterparty_subprocessor_breach | 13 | 26.4 | 15.6 | 16/17 | 26/28 (93%) | 0 | 22/28 | correct | 0 |
| 8 | 08_baa_hipaa_counterparty_missing | 11 | 35.9 | 13.2 | 16/17 | 22/31 (71%) | 0 | 19/31 | correct | 0 |
| 9 | 09_mutual_nda_own_clean | 12 | 32.7 | 14.4 | 16/17 | 24/30 (80%) | 1 | 22/30 | correct | 0 |
| 10 | 10_mutual_nda_counterparty_residuals | 12 | 23.2 | 14.4 | 14/17 | 15/16 (94%) | 0 | 14/16 | correct | 0 |
| 11 | 11_vendor_msa_counterparty_lowcap | 13 | 29.5 | 15.6 | 16/17 | 19/20 (95%) | 0 | 18/20 | correct | 0 |
| 12 | 12_vendor_msa_counterparty_reasonable | 12 | 29.4 | 14.4 | 16/17 | 19/20 (95%) | 0 | 19/20 | correct | 0 |

Section recall below 90% on contracts **4, 5, 6, 8, 9** — all five are
driven by unanchored exhibits/schedules/annexes trailing material (see
section 5).

### Tier 1 field accuracy, per field (12 DOCX contracts)

| Field | Matched | Total | % | Mark |
|---|---|---|---|---|
| currency | 12 | 12 | 100.0% | MET |
| dispute_venue | 12 | 12 | 100.0% | MET |
| expiry_date | 12 | 12 | 100.0% | MET |
| governing_law | 12 | 12 | 100.0% | MET |
| initial_term_months | 12 | 12 | 100.0% | MET |
| payment_terms_days | 12 | 12 | 100.0% | MET |
| renewal_notice_days | 12 | 12 | 100.0% | MET |
| renewal_term_months | 12 | 12 | 100.0% | MET |
| liability_cap_amount | 11 | 12 | 91.7% | MET |
| termination_for_convenience_party | 11 | 12 | 91.7% | MET |
| auto_renewal | 10 | 12 | 83.3% | NOT MET |
| effective_date | 10 | 12 | 83.3% | NOT MET |
| liability_cap_basis | 10 | 12 | 83.3% | NOT MET |
| termination_notice_days | 10 | 12 | 83.3% | NOT MET |
| dispute_resolution | 7 | 12 | 58.3% | NOT MET |
| termination_for_convenience | 8 | 12 | 66.7% | NOT MET |
| total_value_amount | 8 | 12 | 66.7% | NOT MET |

10 of 17 scored Tier 1 fields are at or above the 85% mark; 7 are below it.

## 5. Every miss, with probable cause

**dispute_resolution (7/12, 58.3%) — the dominant failure.** The registry
enum is `litigation | arbitration | mediation`.
- Contracts 1, 2, 3: expected is descriptive ("senior-management
  escalation before formal proceedings"), which is not representable in
  the three-value enum at all — this cannot score as a match regardless of
  what Extract answers. Got `litigation` in each case, which is a
  plausible reading given each of these contracts' venue clause names a
  specific court. **Probable cause: field design** (the enum is too narrow
  for this common real-world pattern), not a clear extraction fault.
- Contracts 4, 5: expected `null` (no dispute-resolution clause, only a
  governing-law/venue clause naming "courts of Ireland" / "courts of
  Delaware"). Got `litigation` both times. This is a defensible reading of
  a venue clause, not obviously wrong — **probable cause is ambiguous
  between field design and a genuine inference choice**; it is not
  confidently an extraction overreach, and an earlier draft of this report
  overstated that characterization.

**total_value_amount (8/12, 66.7%).** All 4 misses are "not extracted"
(Extract itself returned `null`) on contracts where the expected answer is
a composite, descriptive figure ("$180,000 annual subscription fee plus
$12,000 one-time implementation fee"; "exceeds $1,800,000 annually").
**Probable cause: field design.** The registry types this as a single
`number`; a composite two-part fee structure has no single correct number,
and Extract appears to decline to answer rather than guess one of the two
figures.

**termination_for_convenience (8/12, 66.7%).** The 4 misses, checked
individually against the raw Extract output:
- Contracts 1, 4: expected `False` (no convenience-termination clause,
  only for-cause), Extract returned `None` ("not extracted").
- Contract 8: expected `None` (this BAA ties termination to the
  underlying agreement and to breach only, which the answer key reads as
  "not addressed" rather than "no such right"), Extract returned `False`.
- Contract 10: expected `True` — §12.11 states "either party may terminate
  discussions regarding the Purpose at any time ... without liability".
  Extract returned `None`. **This one is a genuine extraction miss**, not
  a convention issue: the clause is there and states the opposite of what
  was extracted.

Contracts 2, 3, 11, 12 all have the same "only for-cause termination
present" pattern as contracts 1 and 4, yet Extract answered `False` on
those and `None` on 1 and 4 — **both the answer key's convention and
Extract's own answers are inconsistent on this pattern**, not just the
answer key. **Probable cause: a mix of (a) a genuine extraction miss on
contract 10, and (b) a convention that neither the field description nor
Extract applies consistently** for "clause type present, no convenience
right stated" versus "clause type absent entirely." The field's own
description says "leave null if not stated," which would argue for `None`
in all of contracts 1, 2, 3, 4, 11, 12 alike; Extract instead answers
`False` on four of them (2, 3, 11, 12) and `None` on two (1, 4) — a 4-2
split, not an even one, but still inconsistent on an identical underlying
pattern. One of the two conventions should be
fixed, and separately, contract 10's miss should be investigated as a
real extraction failure. See "Proposed logic changes."

**liability_cap_basis (10/12, 83.3%).** The 2 misses (contracts 3 and 7)
are "not extracted" where the contract defers to another document ("the
Agreement," "the underlying services agreement") rather than restating a
cap formula itself, or (contract 3) states the cap is explicitly
uncapped/unlimited — the expected answer for contract 3 is `"none;
liability expressly uncapped"`. **Probable cause: likely a real
extraction gap** on cross-referential/deferral language, compounded by a
field-design edge case for contract 3 (an "uncapped" contract has no
formula-shaped "basis" to quote). Contract 3's `liability_cap_amount`
miss — covered separately in section 5.1 — is the same underlying
"uncapped" statement, there expressed as the string `"unlimited (no
cap)"` for a field typed `number`.

**termination_notice_days (10/12, 83.3%).** Both misses are false
positives: contracts 3 and 4 got `30` where the expected answer is `null`
(the contract states only a cure period, not a separate
termination-notice period). **Probable cause: likely a real extraction
confusion** between `cure_period_days` and `termination_notice_days` — the
two fields' descriptions may be too close for the model to reliably
separate "days to cure a breach before termination" from "days' notice
required for termination" when only the former is present.

**auto_renewal (10/12, 83.3%).** Both misses are "not extracted" on the
two NDAs (contracts 9, 10), where the expected answer is `False` because
the contract states only a fixed term with no renewal clause at all (same
leave-null-vs-infer-false convention tension as
`termination_for_convenience` above). **Probable cause: convention
mismatch**, not a pipeline fault, by the same reasoning.

**effective_date (10/12, 83.3%).** Both misses are on the two vendor MSAs
(contracts 11, 12), where Extract found and returned the date from "made
as of September 15, 2026" / "made as of October 2, 2026", but the expected
answer is `null` because `fields_expected.yaml`'s own comment notes
`"Effective Date" is used undefined in 4.1 without a parenthetical
definition tying it to that date`. **Probable cause: likely a genuinely
disputable judgement call in the answer key**, not a clear extraction
fault — reading "made as of" as the effective date is a defensible, common
convention that most readers of the contract would likely also apply. This
is flagged honestly as a miss per the scoring rule above, but it is the
one field-level miss in this list that may say more about the answer key's
strictness than about the pipeline.

**Section recall below 90% on 5 of 12 documents, and clause typing at
83.9% overall — the two structural misses, and they share a root cause
that was checked directly against the raw Extract output, not assumed.**
Every one of the 29 unanchored entries across all 12 contracts (full list
in the appendix below) is an exhibit, schedule, or annex (`Exhibit A`,
`Schedule 1`, `Annex 1`, etc.) — e.g. contract 8 alone has 9 unanchored
schedules out of 31 expected sections, which alone drags it to 71%
recall. **The cause is not the segmenter's anchor logic.** All 9
contracts with at least one such unanchored item (4, 5, 6, 7, 8, 9, 10,
11, 12) were checked directly against their raw `clauses[]` hint list:
8 of the 9 (4, 5, 6, 8, 9, 10, 11, 12) contain **zero non-numeric
`section_number` entries at all** — none of their exhibits, schedules, or
annexes was ever hinted by Extract in the first place. The 9th, contract
7, contains exactly one non-numeric entry, `{"section_number": "ANNEX
3", ...}` — and that is precisely the one appendix item contract 7's
segmenter *did* anchor successfully (`annex_1`/`annex_2` in the same
contract were never hinted and were not anchored, same as the other 8
contracts). **In every case checked, the segmenter anchored every
appendix item it was given a hint for, and anchored none of the ones it
was not given a hint for.** The probable cause is that Extract's own
`clauses[]` output — built from the schema's own description, "every
top-level numbered section ... no sub-clauses" — systematically omits
exhibits/schedules/annexes as not being "numbered sections" in the sense
the prompt means, not a failure of `sections.py`'s anchor regex on hints
it was actually given. The unhinted appendix text is not lost — each such
item's text is merged into the preceding level-1 clause, e.g. contract
8's Schedules 1-2 merge into section 16 (they sit between numbered
sections 16 and 17 in the document, not at the very end); trailing
appendices at the actual end of a document merge into the last numbered
section, or into the signature block where one was detected — but it
is not a separate, correctly-typed clause of its own.

**Typing accuracy restricted to sections that WERE anchored is 92.7%
(255/275)** — comfortably above the 85% mark — which shows the *typing*
logic (`clause_typing.py`) itself is working well once a section is
anchored at all; the 83.9% overall figure is low because of the
segmentation/hinting gap above, not because of mistyping. The 20
anchored-but-mistyped sections (out of 275 anchored) are listed in the
appendix below; several are defensible synonym-driven dictionary matches
that simply disagree with the answer key's single "best fit" choice for a
mixed-topic section (e.g. "Interpretation" dictionary-matching to
`definitions` where the answer key calls the whole section `other`),
rather than clear typing errors.

**The two false splits (contracts 3 and 9) have a confirmed root cause:
Extract emitting a genuine duplicate hint for one section, where the
duplicate has no title — and the resulting number-only anchor attempt
matching a sub-clause's own number prefix rather than failing cleanly.**
Contract 3's raw hint list contains `{"title": "SECURITY", "family":
"security", "section_number": "9"}` immediately followed by `{"title":
None, "family": "security", "section_number": "9"}`; contract 9's
contains the same pattern for section 13 (`"GENERAL PROVISIONS"` then a
second, title-less hint also numbered `13`). The segmenter anchors the
first (titled) occurrence normally. For the second, title-less hint, plan
section 5.3's own rule for a hint with no title is to anchor on the
number alone, with no title pattern to require — and the extra clause
created in each case was checked directly: contract 3's extra clause
starts at `"9.1 Halcyon shall maintain administrative, technical and
physical safeguards..."` and contract 9's at `"13.1 This Agreement may be
amended only by a written instrument..."`. In both cases the number-only
anchor regex (`9\s*[.\-):]*\s*`, `13\s*[.\-):]*\s*`) matched the start of
a `9.1`/`13.1` **sub-clause** elsewhere in the document — the pattern has
nothing stopping it from matching just the leading digits of a longer
number, so `9` matches the `9` in `9.1` just as readily as a bare `9`
followed by whitespace or punctuation — creating a spurious extra level-1
clause rather than failing to anchor at all. **This is a different, and
more precisely diagnosable,
mechanism than an earlier draft of this paragraph speculated** (a "stray
cross-reference in running text"): it is specifically the number-only
regex matching a sub-clause's own numbering, confirmed by reading each
extra clause's actual text.

**Contract 7's duplicate hint for section 9 is a different case, not the
same pattern.** Its raw hint list contains `{"title": "SUB-PROCESSORS",
...}` immediately followed by `{"title": "Sub-processors", ...}` (same
section number, **both titled**, differing only in capitalisation) — not
a title-less duplicate. The segmenter anchors the first occurrence
normally; the second occurrence's anchor requires matching the number
*and* a title pattern derived from "Sub-processors", which is already
satisfied by the first clause's text and has nowhere else to match,
producing the benign warning `section_not_anchored:9 Sub-processors` with
no extra clause. **The discriminator between a benign warning and an
actual false split is therefore whether the duplicate hint has a title at
all, not where the document happens to contain a stray match**: a titled
duplicate's anchor is specific enough to fail cleanly when its target is
already taken; a title-less duplicate's anchor is unconstrained enough to
match a sub-clause's number instead. See "Proposed logic changes" for the
fix this points to (a negative-lookahead fix to the number-only regex,
checked directly against all 12 DOCX contracts and confirmed to remove
both false splits with no other change to any contract's section-found
count — see proposed change #9).

**Counterparty correct: 12/12 (100%).** Own-organisation matching against
`own_org_names=["Halcyon Care"]` worked on every contract, including the
Ireland-subsidiary cases (contracts 4 and 6, where "Halcyon Care Ireland
Ltd" is "us").

### 5.1 Individual misses inside fields that otherwise MET their mark

Two fields cleared 85% overall but each hide one real miss worth naming,
per the "every miss listed" requirement:

- **liability_cap_amount, contract 3** (11/12 overall, MET): expected
  `"unlimited (no cap)"`, a string describing the absence of a cap, for a
  field typed `number`. Extract itself returned `None`. No number can
  represent "no cap" under this field's type — this is the same
  field-design tension as `total_value_amount`'s composite figures, on a
  single contract rather than four.
- **termination_for_convenience_party, contract 10** (11/12 overall, MET):
  expected `"either party"` (free text matching the enum's `"either"`
  value). Extract returned `None` — the same contract 10, same clause
  (§12.11) that `termination_for_convenience` also missed entirely (see
  above). Both misses on contract 10 point at the same real extraction
  gap: Extract did not find §12.11's "either party may terminate
  discussions ... at any time ... without liability" at all.

### 5.1a Every unanchored section (all 29, across the 9 affected contracts)

- Contract 4: `exhibit_a` "Exhibit A - Sample Order Form", `exhibit_b`
  "Exhibit B - Data Processing Addendum", `exhibit_c` "Exhibit C - Support
  and Maintenance"
- Contract 5: `exhibit_a` "Exhibit A - Sample Order Form", `exhibit_b`
  "Exhibit B - Support and Maintenance", `exhibit_c` "Exhibit C -
  Governance and Reporting"
- Contract 6: `annex_1` "Annex 1 - Description of Processing", `annex_2`
  "Annex 2 - Technical and Organisational Measures", `annex_3` "Annex 3 -
  Breach Notification Content"
- Contract 7 (DOCX): `annex_1` "Annex 1: Description of Processing",
  `annex_2` "Annex 2: Schedule of Safeguards" (its third annex, `annex_3`
  "Annex 3: Points of Contact", **was** anchored — see the hint-list
  finding above)
- Contract 7 (PDF): same two, plus `annex_3` "Annex 3: Points of Contact"
  (unlike the DOCX run, the PDF run did not anchor `annex_3` either — see
  section 6)
- Contract 8: `schedule_1` "Schedule 1: Description of Services",
  `schedule_2` "Schedule 2: Points of Contact", `schedule_3` "Schedule 3:
  Underlying Agreement Cross-Reference", `schedule_4` "Schedule 4:
  Execution and Approval", `schedule_5` "Schedule 5: Amendment History",
  `schedule_6` "Schedule 6: Background on Business Associate",
  `schedule_7` "Schedule 7: Defined Terms Cross-Reference", `schedule_8`
  "Schedule 8: Notices Checklist", `schedule_9` "Schedule 9: Relationship
  to Future Versions of this BAA" (all 9 of this contract's schedules)
- Contract 9: `schedule_a` "Schedule A: Illustrative Discussion Topics",
  `schedule_b` "Schedule B: Administration of this Agreement",
  `schedule_c` "Schedule C: Background Information", `schedule_d`
  "Schedule D: Signature and Execution", `schedule_e` "Schedule E: Defined
  Terms Cross-Reference", `schedule_f` "Schedule F: Notices Checklist"
  (all 6 of this contract's schedules)
- Contract 10: `schedule_a` "Schedule A - Illustrative Topics for
  Discussion"
- Contract 11: `exhibit_a` "Exhibit A - Sample Statement of Work
  (Illustrative Form)"
- Contract 12: `exhibit_a` "Exhibit A - Sample Statement of Work
  (Illustrative Form)"

(29 total across the 12 DOCX contracts; contracts 1, 2, 3 have no
unanchored sections at all.)

### 5.2 Every anchored-but-mistyped section (20 of 275 anchored sections)

Format: contract — expected number/title — expected family → got family —
`type_source` (checked directly against each clause's own `type_source`
attribute, not inferred).

- 1 — 19 Support Services — `other` → `service_levels` — `extract`
- 1 — 21 Third-Party Services and Integrations — `other` → `entire_agreement` — `dictionary`
- 2 — 19 Support Services — `other` → `service_levels` — `extract`
- 2 — 21 Third-Party Services and Integrations — `other` → `entire_agreement` — `dictionary`
- 3 — 17 Support Services — `other` → `service_levels` — `extract`
- 3 — 19 Third-Party Services and Integrations — `other` → `entire_agreement` — `dictionary`
- 3 — 31 Exhibit A: Subscription Fees and Term — `other` → `term` — `extract`
- 6 — 1 Roles of the Parties — `definitions` → `data_protection` — `extract`
- 6 — 11 Return and Deletion — `data_protection` → `termination` — `extract`
- 7 — 1 Roles of the Parties — `definitions` → `data_protection` — `extract`
- 7 — 5 Personnel Confidentiality — `data_protection` → `confidentiality` — `extract`
- 7 — 20 Interpretation — `other` → `definitions` — `dictionary`
- 7 — Annex 3: Points of Contact — `other` → `notices` — `extract`
- 8 — 8 Term and Termination — `term` → `termination` — `extract`
- 8 — 14 Interpretation — `other` → `definitions` — `dictionary`
- 8 — 17 Public Information — `other` → `compliance` — `extract`
- 9 — 18 Interpretation — `other` → `definitions` — `dictionary`
- 9 — 23 Relationship to Future Agreements — `other` → `confidentiality` — `extract`
- 10 — 13 Acknowledgements — `other` → `entire_agreement` — `extract`
- 11 — 4 Term and Termination — `term` → `termination` — `extract`

**14 of the 20 are `type_source="extract"` — i.e. `clause_typing.py`
kept Extract's own hint family verbatim (per plan section 5.4's own
rule, a non-`other` hint wins), and it was Extract's hint that disagreed
with the answer key**, not a dictionary decision. `term`→`termination`
(contracts 8, 11) and `other`→`compliance` (contract 8) are
closely-related, defensible disagreements over a mixed-topic or
ambiguous title where Extract's hint and the answer key chose different
single "best fits." `definitions`→`data_protection` (contracts 6 and 7,
both for a section titled "Roles of the Parties") is a defensible content
reading on its own terms — a DPA/subprocessor agreement's "Roles of the
Parties" section is substantially about data-protection roles
(controller/processor), so `data_protection` is not simply wrong — but it
has a concrete downstream consequence worth naming: `expected.yaml`'s
playbook rule `definitions.roles_of_parties` is keyed to the
`definitions` family, and with the pipeline typing this section
`data_protection` instead, that rule would not find section 1 in either
contract 6 or contract 7. `data_protection`→`confidentiality` (contract
7, "Personnel Confidentiality") reads similarly as a defensible
content-driven reading rather than a clear naming error.

**6 of the 20 are `type_source="dictionary"`**, all involving a hint
whose family was `other` (or absent) being overridden by a fuzzy-synonym
dictionary match — exactly plan section 5.4's documented rule that a
non-`other` hint is trusted but an `other` (or missing) hint falls through
to the dictionary. Three are "Interpretation"→`definitions` (contracts 7,
8, 9): a defensible dictionary match on a genuinely ambiguous title where
the answer key chose `other` as the single best fit for what is usually a
short boilerplate clause. The other three are "Third-Party Services and
Integrations"→`entire_agreement`, identical across contracts 1, 2, and 3
(the same template-derived SaaS MSA boilerplate, so this is one recurring
pattern, not three independent misses) — this one reads as a genuine
dictionary false positive rather than a defensible judgment call: a
section about third-party service integrations plausibly contains a word
(e.g. "integration") that matches a synonym registered against the
entire-agreement/integration-clause family, with no real connection to
the section's actual subject.

### 5.3 The two false-split clauses themselves

- Contract 3: an extra level-1 clause, `section_number="9"`, `title=None`,
  `clause_type="security"`, not matched to any expected section.
- Contract 9: an extra level-1 clause, `section_number="13"`, `title=None`,
  `clause_type="other"`, not matched to any expected section.

Both trace to the duplicate-hint pattern described above (a second,
title-less hint for a section number already anchored by its titled
twin).

## 6. DOCX vs PDF: contract 7

| | fields | sections | typing | warnings |
|---|---|---|---|---|
| DOCX | 16/17 | 26/28 (93%) | 22/28 | `section_not_anchored:9 Sub-processors` (benign, see above) |
| PDF | 16/17 | 25/28 (89%) | 22/28 | none |

The PDF run is **not identical** to its DOCX counterpart, but checking
its own raw `clauses[]` hint list directly (rather than inferring from
the absence of a warning) shows the difference is consistent with, not
contrary to, the two root causes already established above:

- **The PDF run's hint list has zero non-numeric `section_number`
  entries at all** (24 hints total) — unlike the DOCX run, which hinted
  exactly one appendix item (`"ANNEX 3"`). So the PDF run never anchored
  `annex_3` either, not because it anchored a hint badly, but because
  Extract never hinted it in the first place for this format — the same
  "Extract's hint list omits appendices" pattern as every other contract,
  just slightly more complete in this one instance for the DOCX run than
  the PDF run of the identical document.
- **The PDF run's hint list has zero duplicate section numbers at all**
  (confirmed directly) — so it did not reproduce the DOCX run's duplicate
  `"9"` hint, and correspondingly produced no `section_not_anchored`
  warning. This is a difference in what Extract's hint generation
  happened to produce for the same document converted to a different
  format, not a difference in how the pipeline processed it.

Both of Extract's own format-dependent hint-list differences happen to
work in the PDF run's favour for the duplicate-hint issue (no spurious
warning) and against it for the appendix-hinting issue (one fewer section
found than the DOCX run, 25/28 vs 26/28). Fields correct is identical
between the two formats (16/17 each), and typing correct is identical in
absolute terms (22/28 in both), though as a rate of what was anchored
this is 22/26 (85%) for DOCX versus 22/25 (88%) for PDF — the PDF run
anchored one fewer section but still got the same number right. This is
a useful, if small and single-contract, data point that the PDF
path does not obviously regress relative to DOCX in the pipeline's own
logic — the observed difference traces entirely to Extract's hint
generation varying slightly by input format, not to anything `sections.py`
or `clause_typing.py` did differently.

**Sample size, for calibrating how much weight to put on "exhibits are
never hinted":** checked directly across all 12 DOCX contracts plus this
PDF run, **zero of the 29 unanchored sections listed in the appendix
(section 5.1a) were ever given a hint by Extract**, for any of the 9
affected contracts. Separately, exactly 3 appendix-type items elsewhere
in the corpus *were* hinted, and all 3 were anchored successfully:
contract 1's "Exhibit A" (hinted as an ordinary numeric section, `33`,
continuing the document's main numbering, and not counted among the 29
unanchored since the answer key itself numbers it `33` rather than giving
it a special label), contract 3's "Exhibit A" (same pattern, numbered
`31`), and contract 7 DOCX's "Annex 3" (hinted with the literal
non-numeric label `"ANNEX 3"` — the one case in the corpus where a
specially-labelled appendix item got a hint at all). The pattern that
holds without exception in this corpus is narrower than "exhibits are
never hinted": an appendix item hinted as part of the main numeric
sequence gets anchored like any other section; a specially-labelled
appendix item is anchored only in the one case where it happened to be
hinted, and is unanchored in all 29 cases where it was not.

Extend's own server-side processing time for the PDF run (`createdAt` to
`updatedAt` on the extract run) was 23.8 seconds, versus a 26.4-second
client-side wall-clock figure (upload through fetching parse blocks) for
the same contract's DOCX run. These two numbers measure different things
(server processing time vs. client-observed wall time including upload
and polling overhead) and should not be read as a direct apples-to-apples
PDF-vs-DOCX speed comparison; they are both reported here for
completeness, not as evidence of a speed difference between formats.

## 7. What was not done

- **Tier 2 field accuracy was not scored in this report.**
  `fields_expected.yaml` (task 6.1) only covers Tier 1 fields; scoring
  Tier 2 fields against the source contracts directly was out of scope for
  the time available in this run and is not included above. The plan
  section 2 mark for Tier 2 fields is therefore **not evaluated**, not
  "met" or "not met" — this should not be read as a pass.
- **The second planned PDF contract (`01_saas_msa_own_clean`) was not
  run.** The cost ceiling (next section) was reached by the 12-DOCX corpus
  run itself; running a second PDF conversion past that point was declined
  rather than pushed through.
- **No fixtures were saved to `backend/tests/fixtures/ingest/`.** Step 4 of
  the implementation doc's own task description (saving two contracts'
  responses as new replay cases) is explicitly gated on "the user's
  agreement" in the implementation doc's own wording. This was not done
  and the question is explicitly surfaced back to the user/coordinator
  rather than decided here, per the task's own instruction not to make
  that call.
- **No database writes happened anywhere in this run**, consistent with
  the task's constraints.

## 8. Cost

### Extract run IDs, for reproducibility

Every number in this report can be reproduced with free `GET
/extract_runs/{id}` and `GET /parse_runs/{id}` calls against these 13
already-completed, already-billed run IDs — no new Extract run is needed
to re-check anything above, or to pull a response for fixture-saving if
the user approves that step (section 7):

| Contract | Format | Extract run ID |
|---|---|---|
| 1 (01_saas_msa_own_clean) | docx | `exr_m2uZ1GlxoWXyinukvd2xk` |
| 2 (02_saas_msa_own_midmarket_yellow) | docx | `exr_8jKhauE4mSFm86IxSUXts` |
| 3 (03_saas_msa_hipaa_counterparty_hospital_red) | docx | `exr_UTBxCvsfcxCApGT3rO2aM` |
| 4 (04_saas_msa_gdpr_counterparty_euclinic_yellow) | docx | `exr_GotjqRHtlfT3ji8MvcvQ1` |
| 5 (05_saas_msa_counterparty_strategic) | docx | `exr_v2LdgRqy6wRRAqfIVEDyW` |
| 6 (06_dpa_gdpr_own_clean) | docx | `exr_X0O5bMz7HDmBBBUhlqihG` |
| 7 (07_dpa_counterparty_subprocessor_breach) | docx | `exr_HfzIxVLMkk8jgWglYHKVR` |
| 8 (08_baa_hipaa_counterparty_missing) | docx | `exr_6ubG9P70Dwg3hdQT2MRfB` |
| 9 (09_mutual_nda_own_clean) | docx | `exr_WR9ry7UZUwa2XRHHSEV6v` |
| 10 (10_mutual_nda_counterparty_residuals) | docx | `exr_GaLxUJKzN5eBrS0oqzizh` |
| 11 (11_vendor_msa_counterparty_lowcap) | docx | `exr_tyD5H5CnMuv8My9WZuCq6` |
| 12 (12_vendor_msa_counterparty_reasonable) | docx | `exr_luxq1TjMe3ARKfnwdOBs7` |
| 7 (07_dpa_counterparty_subprocessor_breach) | pdf | `exr_e99KDM6xUPDY5ehvDZwXe` |

| Item | Credits |
|---|---|
| Schema-bug diagnosis (4 billed live calls against contract 1's 14-page DOCX: 3 minimal-schema probes used to isolate each of the three defects in section 1, plus 1 validation run against the full patched schema before trusting it for the corpus — a malformed schema gets a 400 and is never billed, confirmed live; only these 4 valid-schema calls were billed) | 67.2 |
| The 12-contract DOCX corpus run | 183.6 |
| The 1 PDF-path run (`07_dpa_counterparty_subprocessor_breach.pdf`) | 16.8 |
| **Total billed, 2026-11-18** | **267.6** |

The implementation doc's ceiling is "roughly 12 contracts x 6-15 pages x
1.2 credits/page, under 250 credits total." The real corpus (DOCX + the one
PDF run) cost 200.4 credits on its own — under the 250 ceiling by itself,
and consistent with the 1.2-credits/page estimate (observed: 11-14 pages
per contract, 1.2 credits/page exactly, matching extract (0.7/page) + parse
(0.5/page) combined). The total including schema-bug diagnosis (267.6) is
about 7% over the 250 ceiling, not "far above" it. The overage is entirely
attributable to the real, load-bearing defect in section 1 — it could not
have been found without live calls, and finding it before running the
full corpus against a schema the API would reject on every single contract
was the better use of that budget. For this actual run, the script's cost
ceiling was manually seeded at `running_credits = 67.2` (the schema-bug
diagnosis spend, paid outside the script itself) before the corpus loop
started, specifically so the 250-credit ceiling would account for the
true cumulative spend for the day, not just what that one process
invocation billed. That seed is the only reason the ceiling triggered
where it did: the printed warnings landed at 220.8 and 236.4 credits, and
the stop landed at 250.8 (67.2 already spent + 183.6 from the 12 DOCX
contracts) right after the 12th and last DOCX contract completed. Without
that seed, the ceiling would never have triggered during the 12-contract
DOCX loop at all (183.6 alone never reaches 250), both planned PDF
contracts would have run, and the day's true total would have landed
around 284 credits (267.6 as billed, plus the ~16.8 for the second PDF
contract that was in fact skipped). **The hardcoded seed has since been
removed from the script** — a future run starts at `running_credits =
0.0` — because leaving it in would make every future run of this script
hit the ceiling about 67 credits early for no reason specific to that
run. One real gap found in the script during this run — also now fixed —
is that the cost-ceiling check originally guarded only the DOCX loop, not
the subsequent PDF loop; the PDF run for contract 7 had already been
dispatched (and billed) in the instant between the ceiling being reached
and the process being killed externally, which is why it appears in the
results above despite the ceiling having already been reached. No further
PDF runs were attempted once that was discovered, and the PDF loop is now
gated the same way the DOCX loop is. Running the second planned PDF
contract (`01_saas_msa_own_clean`) would cost roughly another 16.8
credits; whether to spend that is left to the coordinator/user.

## 9. Proposed logic changes (not implemented here — coordinator/user decision)

Per the task's own constraint, none of these were implemented. They are
listed for the coordinator and user to decide on, not acted on:

1. **Fix `fields.py::build_extract_schema`'s three schema defects (section
   1 above), and regenerate `test_dp_fields.py`'s schema snapshot
   accordingly.** This is a hard blocker for any other live-Extend-
   dependent work (task 6.3, and the real `ingest.py` in task 3.1):
   without this fix, the schema the application would actually send is
   rejected by the API on every call. The fix is mechanical (correct enum
   and array type encoding); the correct shapes are confirmed live in this
   report's section 1 and in `evaluate_ingest.py::_fix_enum_schema`'s
   docstring, which can be used as a reference. Also add the "no nullable
   arrays; array items take a bare primitive type" rule to
   `document_processing_implementation.md` section 3's Extend API facts
   table.
2. **Add an empty-list-means-absent check to `mapping.py::map_fields`**
   for `string_list` fields, once fix #1 lands — see the "downstream
   consequence" note in section 1.
3. **Get `clauses[]` hints for exhibits/schedules/annexes from Extract, or
   add a fallback segmentation rule for unhinted trailing material to
   `sections.py`.** This is the direct cause of both the section-recall
   and clause-typing marks not being met; typing itself is fine (92.7% on
   sections that were anchored) once segmentation finds the section in
   the first place, and **this report confirmed directly (not just
   suspected) that the anchor logic is not at fault**: pulling the raw
   `clauses[]` hint list for contracts 6, 7, and 8 shows the segmenter
   anchored every single appendix item it was given a hint for (contract
   7's one hinted annex) and none of the ones it was not (contracts 6 and
   8's appendices, zero of which were ever hinted; contract 7's other two
   annexes, also unhinted). The fix belongs upstream of the anchor regex:
   either get the schema's `clauses[]` description to also ask for
   exhibits/schedules/annexes explicitly (it currently says "every
   top-level numbered section ... no sub-clauses," which the model
   appears to read as excluding them), or add a `sections.py` rule that
   independently detects trailing appendix headings the same way the
   no-hints-at-all fallback already detects ordinary numbered sections,
   so this material gets its own clause instead of being merged into the
   end of whichever section precedes it.
4. **Reconcile the leave-null-if-not-stated convention with the "no such
   right exists" convention used in `fields_expected.yaml`** for
   `termination_for_convenience`, `termination_for_convenience_party`, and
   `auto_renewal`. Either the registry's field descriptions should
   explicitly ask the model to infer `false` when the relevant clause type
   exists but states no such right, or the answer key's convention should
   move to `null` for these cases and the mark should be re-scored. Note
   that Extract's own answers are inconsistent on this pattern too (section
   5's `termination_for_convenience` paragraph): fixing only the answer key
   or only the field description may not be enough on its own.
5. **Reconsider `dispute_resolution`'s enum** (`litigation | arbitration |
   mediation`) against the real corpus, where "informal escalation before
   formal proceedings" is a common pattern not representable by any of the
   three values.
6. **Reconsider `total_value_amount`'s single-number type** against
   composite/multi-line fee structures (e.g. "$X annual plus $Y one-time"),
   which this field cannot represent and which Extract appears to decline
   to answer rather than guess at.
7. **Disambiguate `termination_notice_days` from `cure_period_days`** in
   the field descriptions — Extract conflated the two on 2 of 12 runs.
8. **Improve `liability_cap_basis` extraction on deferral/cross-reference
   language** ("subject to the Agreement's limitation of liability") and
   on "unlimited/no cap" phrasing, both of which were missed.
9. **Add a negative lookahead to the number-only anchor regex used for a
   title-less hint** (plan section 5.3's rule for a hint with no title;
   `sections.py`'s pattern is built as `rf"{num}\s*[.\-):]*\s*"`, which
   lets `9` match the leading digits of `9.1` or `90` just as readily as
   a standalone `9`). Both confirmed false splits in this corpus (section
   5.3's appendix) trace to exactly this: Extract emitted a second,
   title-less duplicate hint for a section number already anchored by its
   titled twin (contract 3's section 9, contract 9's section 13), and the
   orphaned hint's number-only anchor matched the leading digits of an
   unrelated `9.1`/`13.1` **sub-clause** elsewhere in the document
   (confirmed by reading each extra clause's actual text), producing a
   spurious extra level-1 clause. Contract 7's own duplicate hint for
   section 9 is titled on both occurrences and did not hit this failure
   mode — it produced only a harmless warning, because a titled anchor
   attempt is specific enough to fail cleanly when its target is already
   taken. **Fix and verification, both done without any repo edit or new
   Extract run:** changing the prefix to `rf"{num}(?!\.?\d)\s*[.\-):]*\s*"`
   (a negative lookahead that blocks a following `.` + digit or a bare
   digit, so `9` no longer matches `9.1` or `90` but still matches `9.`,
   `9)`, or `9` followed by whitespace) was monkeypatched over
   `sections._build_anchor_regex` in a scratch script and replayed against
   all 12 DOCX contracts' already-billed Extract output: both false
   splits disappeared, and every contract's section-found count was
   otherwise identical to what is reported in section 4's table — the fix
   does not affect any currently-correct anchor in this corpus (not
   checked against every theoretically possible anchor pattern, only the
   12 real contracts available here). This fix belongs in `sections.py`,
   owned by task 2.3.
10. **Investigate contract 10's `termination_for_convenience` /
    `termination_for_convenience_party` miss** (section 5 and 5.1) as a
    standalone extraction failure, separate from the convention question
    in #4: Extract returned `None` for both fields where §12.11 plainly
    states "either party may terminate discussions ... at any time ...
    without liability."

## 10. Confirmation of what this task did not do

- Did not edit `app/services/document_processing/fields.py` (owned by task
  2.1) despite finding a real, confirmed-live bug in it. The workaround
  lives entirely in `backend/seed/contracts/evaluate_ingest.py`, which this
  task owns.
- Did not make any database writes.
- Did not save any contract's Extract/Parse responses into
  `backend/tests/fixtures/ingest/`. That decision is explicitly left to
  the user/coordinator per the implementation doc's own gating language.
- Did not tune any scoring rule, matching threshold, or field after seeing
  results in order to improve a reported number. Two things changed after
  the first pass, both disclosed in full in section 3: fixing the
  section-matcher's latent one-to-many bug (checked directly: changed
  zero numbers in this corpus), and switching section recall from a
  pooled aggregate to the correct per-document reading (this is what
  turned that mark from "MET" to "NOT MET" — not the matcher fix). Neither
  change was chosen to move a number in either direction; both were
  correctness fixes to the scoring methodology itself.
- Did not print, log, or write the Extend API key anywhere.

## 11. Known scoring caveats (methodology honesty)

- `total_value_amount`'s "number" scoring extracts a leading numeric value
  from a descriptive expected string and compares within 1% tolerance;
  where the expected string has no extractable leading number, it is
  scored as a miss by construction. This affected 0 of the 4 misses for
  this field (all 4 were "not extracted," i.e. Extract itself returned
  null) — the caveat is noted for transparency but did not change any
  outcome here.
- The section/typing matching's fuzzy-title fallback (`token_sort_ratio >=
  75`, or `>= 35` as a sanity floor on an otherwise-exact number match) is
  this script's own heuristic, not an official metric. It is reused
  identically across all 12 contracts, so the comparison between
  contracts is fair even if the absolute recall/typing numbers might shift
  a few points under a different threshold.
- All numbers in sections 4-6 are scored over the 12 DOCX contracts; the
  PDF run for contract 7 is reported separately in section 6 and is not
  pooled into any of the aggregate figures or the mark table.

## 12. Task 6.3: database and end-to-end check

Run against the real database and the real Extend API, with the user's
explicit go-ahead, on 2026-11-18. This section was added after an
independent audit correctly found that task 6.3's results had never been
written down anywhere durable — they had only been reported in chat. Every
number below is taken directly from the two live runs' own tool output, not
reconstructed from memory.

### 12.0 First run found a real, blocking bug — not a pass

The first attempt at this task uploaded three real seed contracts
(`01_saas_msa_own_clean.docx`, `03_saas_msa_hipaa_counterparty_hospital_red.docx`,
`06_dpa_gdpr_own_clean.docx`) through the live API. **All three ended
`status=failed, status_reason=extraction_failed`** — none reached `ready`.

Root cause, confirmed by direct reproduction: `app/db/repositories/field_repo.py
::replace_extracted` wrote a raw Python `datetime.date` object (returned by
`fields.validate_value` for any date-kind field, e.g. `effective_date`)
straight into the `contract_field.value` JSONB column. psycopg has no
default JSON encoder for `date`, so the `INSERT` raised
`TypeError: Object of type date is not JSON serializable` inside the single
ingest transaction, which rolled back; the broad `except Exception` in
`ingest.py::run_ingest` caught it, mapped it to the generic
`extraction_failed` reason, and marked the contract `failed`. **This was
completely silent** — `ingest.py` had no `logging` import at all, so no
trace of the real error reached the server log. Virtually every real
contract has at least one date field, so this bug would have crashed every
real ingest.

A secondary consequence: `ingest_run.credits_used` was `null` on all three
runs, not because Extend failed to report usage (it did — the raw
`extract.json` stored in the bucket showed real credit figures for all
three) but because the crash happened before the line that reads
`extract_run.usage` into `credits_used` ever ran.

The duplicate-upload check (409), the corrupt-file check (ends `failed`
with a reason), and `scripts.check_partition.py` before/after all passed
cleanly on this first run — only the parts of the task that depended on a
contract reaching `ready` could not be exercised.

The three failed test contracts were deleted from the database afterward.

### 12.1 Fix applied

- `app/db/repositories/field_repo.py`: added a `_json_safe()` helper that
  converts `datetime.date`/`datetime.datetime` to an ISO string before
  storage, applied in both `replace_extracted` and `set_user_value`.
- `app/services/document_processing/ingest.py`: added `logging.getLogger`
  and a `logger.exception(...)` call in the failure-handling path, so this
  class of bug is visible in the server log going forward, never silently
  swallowed again.
- Two new regression tests added to `tests/unit/test_dp_repositories.py`
  (`test_replace_extracted_coerces_date_values_to_iso_strings`,
  `test_set_user_value_coerces_date_values_to_iso_strings`), both passing.
- Full backend suite re-confirmed clean after the fix before re-running 6.3.

### 12.2 Second run: the fix worked, with real (non-vacuous) evidence

Three fresh uploads, same three files. **All three reached `status=ready`**
within 30 seconds of polling each. No tracebacks in the server log.

Direct proof the date fix specifically works, not just "the transaction
didn't crash": `contract_field.value` for `effective_date` was stored as an
ISO string (e.g. `'2026-03-03'`), and `contract_metadata.effective_date`
held the matching `datetime.date` — the JSONB write of a date-bearing field
round-trips correctly.

Per-contract checks, each against a real query result:

| Check | Result |
|---|---|
| One `contract_version`, `version_number=1` | PASS, all three |
| Every `clause` row has non-null `contract_version_id` | PASS, 0 null rows (own: 123 clauses, counterparty: 127, DPA: 77) |
| Plan §7.5 pt 7: `contract.canonical_text` == current version's text, non-empty | PASS — own 23,902 chars, counterparty 23,580, DPA 24,038, all exact matches |
| Plan §7.5 pt 8: `contract.counterparty_id` == `contract_party` role=`counterparty`, or both null | PASS, but **vacuously**: `OWN_ORG_NAMES` was not set in this test environment's `.env`, so every party resolved to role `other` and `counterparty_id` stayed null on all three (confirmed via the `own_org_not_configured` warning on each `ingest_run`). The "both null" branch of the invariant held; the "actually resolved" branch was not exercised. This is a test-environment config gap (the setting exists and works, per the earlier real-DB migration verification which did resolve a counterparty using `own_org_names=["Halcyon Care"]`), not a code defect. |
| Plan §7.5 pt 9 (light check: nothing changes after `ready`) | PASS on a re-read — clause counts and canonical_text length unchanged |
| `clause_embedding` rows for every eligible level-1 clause (excluding `preamble`/`signature_block`) | PASS — own 33/33, counterparty 31/31, DPA 19/19 |
| `ingest_run` row with `processor_version`, `parse_engine_version`, `credits_used` | PASS, and **credits_used is now populated**: own=9.8, counterparty=9.8, DPA=8.4, all `status='succeeded'`. (Previously this was exactly the crash point; now it completes.) |

Duplicate upload (re-uploading `01_saas_msa_own_clean.docx`): **409
`duplicate_file`** with the correct `existing_contract_id`. PASS.

Corrupt file: a minimal zip containing a `word/document.xml` entry with
garbage (non-DOCX-schema) content passed upload validation, reached Extend,
and Extend itself returned `ExtendRunFailed: FAILED_TO_PROCESS_FILE` — caught
by the new `logger.exception`, with a full traceback visible in the log
(not swallowed), and the contract ended **`status=failed,
status_reason=extraction_failed`**. PASS.

Cascade delete: the DPA contract was deleted via `DELETE FROM contract
WHERE id=...`, relying on DB-level `ON DELETE CASCADE`. Every child table
that actually had rows went from its pre-delete count to zero: `contract_version`
1→0, `clause` 77→0, `contract_metadata` 1→0, `contract_field` 10→0,
`contract_party` 2→0, `ingest_run` 1→0, `clause_embedding` 19→0.
`contract_signatory` had 0 rows on all three contracts to begin with (no
signatory was extracted for these particular documents), so its cascade was
confirmed by reading the model's `ondelete="CASCADE"` definition, not by
data in this run.

`scripts.check_partition.py` passed both before and after (6/6 checks each
time). The backend server was started and stopped cleanly. No API key was
printed or logged at any point in either run.

Credits consumed: 9.8 + 9.8 + 8.4 = 28.0 confirmed for the three successful
ingests, plus a small, unrecorded amount for the corrupt-file Extend call
that failed before producing output.

### 12.3 Post-verification cleanup

After both runs, the two real contracts still live in the database
(`e716b81f...`, `d4718b47...`) and all four test contracts' storage objects
(10 objects total: the three real `.docx` uploads plus their `extract.json`/
`parse.json` raw responses, plus the one corrupt-file blob) were deleted —
both the DB rows (cascade) and the orphaned S3-compatible storage objects
(there is no cascade between the database and the bucket; the objects had
to be deleted directly via the storage client). Confirmed afterward: the
`contract` table is back to exactly 111 rows (the pre-existing playbook
corpus, untouched throughout), `scripts.check_partition.py` passes 6/6, and
the full suite is clean: 1675 backend + 164 seed tests, 0 failures.

### 12.4 What this section does and does not prove

This proves the new ingest pipeline works end-to-end against the real
database and the real Extend API for ordinary, well-formed contracts, and
that its failure paths (duplicate, corrupt file) behave as designed. It
does **not** re-measure the plan §2 accuracy marks (field accuracy, section
recall, typing accuracy) against the full 12-contract corpus — see section
13.4 below for what "complete" does and does not mean as a result.

## 13. Close-out (task 6.4)

Task 6.4 (`document_processing_implementation.md` section "6.4 Removal proof
and close-out") ran the four searches from `document_processing_plan.md`
section 11.3, confirmed the five deleted files and the two removed
dependencies are gone, ran both suites one final time, and ran the removal
guard test explicitly. This section is a read-only verification append; no
code, migration or database write was made.

### 13.1 The four searches (run literally as plan 11.3 specifies them)

Run from `backend/`, exactly as written in plan 11.3 (`app tests scripts seed
pyproject.toml` for search 1; `app tests scripts seed` for searches 2-3;
`app db tests ../frontend/lib ../frontend/components ../frontend/app` for
search 4):

**Search 1** — `pdfplumber|spacy|en_core_web|dateutil`: 5 raw hits, all of
them lines *inside* `tests/unit/test_no_legacy_document_processing.py`
itself (its own pattern string, docstring and function name — the file
necessarily names every pattern it searches for). **Zero hits outside that
one file**, including zero in `seed/` and zero in `pyproject.toml`.

**Search 2** — the old DTOs/functions pattern: 15 non-self hits (i.e.
outside the guard file), all of them exactly the lines the guard file's own
`_SEARCH_2_ALLOWED` allowlist already documents and justifies: `ProcessedContract`
named in a schema docstring explaining it is *not* reused, `extract_metadata`
used as a plain parameter/variable name in the new `mapping.py`/`pipeline.py`
(a different concept from the deleted `extraction.extract_metadata()`
function), `_source_format_from_filename` named in an explanatory comment in
`repository/service.py`, and `classify_contract_type`/`ParsedDocument`/
`SegmentedClause` named only in tests that assert the old name is *absent*
(`test_context_capture.py`, `test_determinism.py`). Zero hits in `seed/`.

**Search 3** — `document_processing\.(parsers|extraction|service|segmentation|clause_types)`:
1 non-self hit, in `tests/unit/test_dp_clause_typing.py`, asserting
`"document_processing.clause_types" not in sys.modules` — a guard, not an
import. Zero hits in `seed/`.

**Search 4** — `financial_fields|milestone_dates|notice_period_days`: 35
non-self hits, all matching the guard file's own `_SEARCH_4_ALLOWED`
allowlist: the legitimate, unrelated `SmartSearchFilters.notice_period_days`
field and its prompt/test coverage, the new Tier-1 `notice_period_days`
`FieldDef` in `fields.py`, explanatory comments in `contract.py` and
`documents.py` naming the removed attributes, migration-018/019 SQL-render
tests exercising the downgrade path (which legitimately still writes the old
column names as raw SQL text), and this task's own removal-guard tests
naming the removed attributes to assert they are gone. The frontend
directories (`../frontend/lib`, `../frontend/components`, `../frontend/app`)
all exist and produced zero hits (search 4's plan scope never included
`seed/`, so there is no seed-scope question for this search).

**Disposition — do not read "prints nothing" literally.** None of the four
searches literally prints nothing: each one necessarily matches the removal
guard test file itself (`tests/unit/test_no_legacy_document_processing.py`),
which has to name every pattern it searches for in its own pattern strings,
docstrings and allowlist comments, plus (for searches 2 and 4) a small number
of legitimate new-pipeline names that happen to share a substring with a
deleted one. **Zero hits are unexplained or new.** Every single non-self hit
above is accounted for by an exact-line entry in that test's own
`_SEARCH_{1,2,3,4}_ALLOWED` frozensets, and running that test explicitly
(section 13.3 below) confirms mechanically that nothing outside those exact
allowlisted lines exists in `app`, `tests`, `scripts`, `db`, or the frontend
directories. This is the same disposition task 5.1 established when it wrote
the guard test: the real proof-of-removal mechanism is the allowlisted guard
test passing, not a bare `grep | wc -l == 0`, because the guard file is
necessarily self-referential and a few new-pipeline names legitimately reuse
old substrings for unrelated concepts.

**Scope note — seed exclusion.** Plan 11.3's literal grep scope for searches
1-3 includes `seed`; search 4 never included `seed`. The removal guard test
(`tests/unit/test_no_legacy_document_processing.py`), by contrast, does not
scan `seed` at all for any of the four searches — by design, per its own
docstring and `test_seed_isolation.py`'s rule that application-side guards
must not even read into the seed package. Run here as plain shell greps (not
as a test), the literal plan-11.3 scope was used, including `seed` for
searches 1-3. The practical effect of this scope difference is nil today:
searches 1-3 produced zero hits inside `seed/` (shown above), so including
or excluding `seed` changes none of the four searches' outcome. The
discrepancy is a scope difference in the test's enforcement surface going
forward (a future regression introduced only inside `seed/` would not be
caught by the guard test, only by `seed/`'s own corpus test and a manual
check like this one), not a finding against the current tree.

### 13.2 Deleted files and removed dependencies

The five files `document_processing_plan.md` section 11.2 marks for
deletion are confirmed absent on disk:
`app/services/document_processing/parsers.py`,
`app/services/document_processing/extraction.py`,
`app/services/document_processing/service.py`,
`app/services/document_processing/segmentation.py`,
`app/services/document_processing/clause_types.py` — all five `ABSENT`.

`pdfplumber` and `spacy` are absent from `backend/pyproject.toml` and from
`backend/uv.lock` (both greps: zero matches).

**Environment check, two methods, because the shared `.venv` was found to
be stale:**

1. *Lock/pyproject grep (primary, version-independent):* as above — neither
   package is declared anywhere in the dependency manifests.
2. *Disposable isolated venv (confirmatory):* built fresh with `uv venv`
   in the scratchpad directory (not the shared `backend/.venv`, to avoid
   disturbing other sessions that may still be using it), then
   `uv sync --all-groups --frozen` against the current `uv.lock`. A first
   pass used Python 3.11 and installed 92 packages with neither
   `pdfplumber` nor `spacy` present (`importlib.util.find_spec` returned
   `None` for both). The isolated venv was torn down and never written to
   through anything but `uv sync`.

   **A real finding surfaced during this check:** the shared, long-lived
   `backend/.venv` (Python 3.13) still has `pdfplumber`, `spacy`, *and*
   `en_core_web_sm` installed as stale leftovers — `importlib.util.find_spec`
   found all three there with real file paths under
   `backend/.venv/lib/python3.13/site-packages/`. None of them are declared
   in `pyproject.toml` or `uv.lock` (confirmed above), and the four searches
   in 13.1 confirm nothing in the application imports them, so they are
   dead weight, not a live dependency — but it means the 1675-pass run
   quoted in earlier sections of this document, and the first full-suite
   run in this close-out, both actually executed with those packages
   physically present in `sys.path`, not absent. Per the ground rules for
   this task, the shared `.venv` was **not** `uv sync`'d or otherwise
   modified (other sessions on this machine may depend on its current
   state). Instead, a **second** isolated venv was built fresh on Python
   3.13 (matching the shared venv's interpreter version) via the same
   `uv venv` + `uv sync --all-groups --frozen` technique, confirmed via
   `importlib.util.find_spec` that `pdfplumber`, `spacy` and
   `en_core_web_sm` are all `None` (truly absent) in that venv, and the
   full backend suite and the seed suite were both re-run inside it (results
   below). That isolated venv was torn down afterward. This satisfies plan
   11.3's "the full test suite passes with `pdfplumber` and `spacy` absent
   from the environment" criterion for real, rather than relying on the
   shared `.venv`'s state.

### 13.3 Final suite runs

All of the following were run both in the shared `backend/.venv` and,
because of the stale-package finding in 13.2, independently reproduced in
the isolated, confirmed-clean Python 3.13 venv. Results were identical in
both:

- **Full backend suite** (`pytest -q` from `backend/`): **1675 passed, 0
  failed.** The implementation doc's older ground-rule exception ("apart
  from the 4 known `test_llm_batch` failures") no longer applies — those
  failures do not exist in the current tree; the suite is fully clean.
- **Seed suite** (`pytest -q seed/tests` from `backend/`): **164 passed, 0
  failed.**
- **Removal guard test, run explicitly**
  (`pytest -q tests/unit/test_no_legacy_document_processing.py`): **5
  passed** — `test_deleted_files_do_not_exist`,
  `test_search_1_no_pdfplumber_spacy_en_core_web_dateutil`,
  `test_search_2_no_old_dtos_or_functions`,
  `test_search_3_no_import_of_deleted_modules`,
  `test_search_4_no_legacy_metadata_field_reads` all pass, mechanically
  confirming the disposition in 13.1 for the `app`/`tests`/`scripts`/`db`/
  frontend scope.

### 13.4 Summary

**Precision note, added after an independent audit correctly flagged the
first version of this summary as overstated** (the original wording below
asserted "complete and verified" without qualification; an audit agent found
no §6.3 evidence existed anywhere in this document at the time, which was
true — task 6.3 had been run, twice, with the user watching, but its
results had only been reported in chat, never written down here. Section 12
above fixes that gap with the full evidence from both runs.):

The document-processing REBUILD ITSELF is complete: the old pipeline's five
files, two dependencies, and all referencing code, tests and columns are
removed and guarded against regression (section 11.3's intent is met via
the allowlisted removal-guard test passing cleanly, per the scope note in
13.1); the full backend suite (1675 passed) and seed suite (164 passed) are
both fully clean with zero failures, in an environment independently
confirmed free of `pdfplumber`, `spacy` and `en_core_web_sm`; and section 12
now records, with real query results, that the new pipeline was proven
end-to-end against the live database and the live Extend API, including
three real contracts reaching `ready`, every plan §7.5 invariant checked
against real (non-vacuous, where the data allowed it) rows, cascade delete
confirmed on every child table that had rows, and duplicate/corrupt-file
handling both confirmed with visible logging.

**What "complete" does NOT mean here, stated plainly so it is not read as
more than it is:** the plan §2 accuracy marks are NOT all met on the full
12-contract corpus (section 4 above: 3 of 5 marks NOT MET, 2 never
evaluated at full-corpus scale). Section 9's proposed fixes were confirmed
working on a targeted 4-contract sample, not re-run on the full 12. This is
a known, disclosed, and consciously accepted gap, not an oversight: the
user was told this directly, in these terms, and explicitly chose to
proceed through phases 3-6 anyway rather than require a full-corpus re-run
first. "Complete and verified" in this document means the REBUILD — the
code, the schema, the removal, the live pipeline mechanics — is done and
proven; it does NOT mean every accuracy mark in plan section 2 is met on
the full corpus. A future full-corpus re-run (re-running `evaluate_ingest.py`
against all 12 contracts with the current, fixed code) would answer that
question for real; it has not been done.

### 13.5 Playbook task 5.4 is now unblocked

`playbook_implementation.md` task 5.4, "End-to-end verification" (depends on
4.5, 4.6, 4.10, 5.1, 5.2; uploads the 12 corpus contracts through the API and
compares findings against `expected.yaml`), can now run. It was blocked on
the document-processing rebuild because the upload API's response shape
changed under that rebuild — a synchronous response became `202 Accepted`
plus polling to `ready`/`failed` — and task 5.4's own corpus-upload step
depends on that shape. Section 12 now records real evidence that the new
`202` + polling flow works against the live API with real contracts, and
this task (6.4) confirms the rebuild is fully closed out, so task 5.4 is
clear to run without any further document-processing dependency
outstanding. It is cost-bearing (uses the model) and task 5.4's own text
says to confirm with the user before running it.
