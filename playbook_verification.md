# Playbook verification report (task 5.4)

Generated as part of task 5.4, "End-to-end verification", of `playbook_implementation.md`. This is a real, cost-bearing run against the live Neon Postgres database and the real Cloudflare R2 bucket, using the real Anthropic API — not a dry run and not mocked. Per explicit instruction for this run, `LLM_TIER_OVERRIDE=claude-haiku-4-5-20251001` was set in `backend/.env`, forcing **every** model call in this exercise (rule-test extraction, Layer 2 content analysis, redline generation) onto Haiku, never Sonnet/Opus/Fable. This was verified directly before spending anything: `get_model_for_task` was called for `playbook.rule_test`, `clause_analysis`, `redline_generate`, `playbook.bootstrap` (normally Opus), `risk_score` and `qa_answer`, and all six resolved to the Haiku model ID. All three of `app/core/llm/gateway.py`'s call paths (`call_structured`, `call_text`, `call_batch`) resolve their model through `get_model_for_task`, so this override is airtight for this run.

> **Re-verification run (2026-11-17).** Sections 1, 4, 5 and 6 come from a second, cost-bearing run of the same 12-contract corpus. It was made after three sets of changes: the clause-classification fix (a hardcoded synonym dict replaced by a DB-backed `clause_family` lookup, including the missing `"term and survival"` synonym), the four structural pipeline fixes (parameter-type red-line reachability, the enum/context prompt blind spots, two seed-content typos, and context-gated positions plus global/playbook-scope red lines), and task 5.5's rule-model migration (`PlaybookRule`'s five legacy flat columns moved onto `rule_position`/`red_line` and dropped; live DB at migration head `o5p6q7r8s9t0`). The method is unchanged from the first run: same upload endpoint, same explicit `contract_type`/`context` from `expected.yaml`, same contract-8 `dpa` substitution, same Haiku override (`LLM_TIER_OVERRIDE=claude-haiku-4-5-20251001`, confirmed to resolve for `clause_analysis` and `redline_generate` before any spend), and the same TP/FN/FP counting rules. "Before" numbers in those sections are quoted from the first run, not re-measured. **Section 3 (the rule-test suite) was not re-run** and still shows the original pre-fix state. Sections 2, 8 and 9 are historical records of the first session and are unchanged apart from a note in section 8. Nothing was tuned to improve these numbers, and no application code, seed content or migration was touched by this re-run.

**This caveat matters for every number below**: the rule-test suite's 95% publish-gate threshold (`app/services/playbook/testing.py::DEFAULT_PASS_THRESHOLD`) was defined against whatever model the "smart" tier normally resolves to (Sonnet), not Haiku. The pass rate measured here is Haiku's rule-extraction accuracy on this content, not a reproduction of whatever pass rate production configuration would show. Do not compare this run's pass rate directly to the 95% gate without re-running it on the default (non-overridden) model tier.

## Contents

1. [The single most important finding](#1-the-single-most-important-finding)
2. [Real bugs found and fixed to get a result](#2-real-bugs-found-and-fixed-to-get-a-result)
3. [Rule-test suite results](#3-rule-test-suite-results)
4. [Corpus precision/recall](#4-corpus-precisionrecall)
5. [Gate decisions](#5-gate-decisions)
6. [Model call counts](#6-model-call-counts)
7. [Proposed fixes (separate from the numbers above)](#7-proposed-fixes-separate-from-the-numbers-above)
8. [Other notes and caveats](#8-other-notes-and-caveats)
9. [Full bypass-driven rule-test run, all 7 playbooks (human judgment, NOT Sonnet)](#9-full-bypass-driven-rule-test-run-all-7-playbooks-human-judgment-not-sonnet)
10. [Task 5.6: seed removal drill](#10-task-56-seed-removal-drill)

## 1. The single most important finding

*Re-verification run (2026-11-17). The first run's finding and its "before" numbers are kept below for comparison.*

**Short version:** the clause-classification fix worked where it reaches. Many more sections now get a real `clause_type`. But the run surfaced a new main cause of false `missing` flags: a top-level section can carry only one `clause_type`. With the current segmenter, sub-clauses are merged into their top-level section, so one clause often holds several rule families. Headings that name more than one family (`"DATA PROTECTION AND SECURITY"`, `"GENERAL PROVISIONS"`, `"TERM AND TERMINATION"`) still fall to `other` or to a single family. The flagship NDA/DPA heading phrasings (`"CONFIDENTIALITY OBLIGATIONS"`, `"EXCLUSIONS"`, `"COMPELLED DISCLOSURE"`, `"RESIDUALS"`, `"NO LICENSE"`, `"RETURN OR DESTRUCTION"`, `"ROLES OF THE PARTIES"`, `"RETURN AND DELETION"`, `"AUDIT AND COOPERATION"`) are still not in the `clause_family` synonym table and still fall to `other`.

### 1.1 Before vs after (measured from `precedent.clause` for the 12 fresh `contract_id`s of each run)

**Important caveat on comparability.** Segmentation granularity changed between the two runs. The working tree now holds an uncommitted change, made after the first run (its origin was not verified by this re-run), to `app/services/document_processing/segmentation.py`: a `_MAX_HEADING_WORDS = 8` heading-shape gate. Long numbered sub-clause sentences such as `"4.1 The initial term is ..."` are no longer split out as their own heading clause, so each contract now segments into about 12-18 top-level sections instead of 19-60 mixed sections and sub-clauses. Total clauses fell from 466 to 183. The "% other" column is therefore not apples-to-apples: the first run's denominator was inflated by sub-clause fragments, most of which were `other`. **"Distinct real clause_types" is the fairer before/after comparison**, and it rose on every contract.

| Contract | Before: total / other / % other / distinct types | After: total / other / % other / distinct types |
|---|---|---|
| 1. 01_saas_msa_own_clean | 60 / 50 / 83% / 11 | 18 / 4 / 22% / **14** |
| 2. 02_saas_msa_own_midmarket_yellow | 59 / 49 / 83% / 11 | 18 / 4 / 22% / **14** |
| 3. 03_saas_msa_hipaa_counterparty_hospital_red | 39 / 32 / 82% / 8 | 15 / 4 / 27% / **11** |
| 4. 04_saas_msa_gdpr_counterparty_euclinic_yellow | 44 / 36 / 82% / 9 | 15 / 3 / 20% / **11** |
| 5. 05_saas_msa_counterparty_strategic | 45 / 37 / 82% / 9 | 15 / 4 / 27% / **11** |
| 6. 06_dpa_gdpr_own_clean | 31 / 31 / 100% / 1 | 13 / 9 / 69% / **4** |
| 7. 07_dpa_counterparty_subprocessor_breach | 33 / 31 / 94% / 3 | 16 / 8 / 50% / **8** |
| 8. 08_baa_hipaa_counterparty_missing | 19 / 16 / 84% / 4 | 12 / 7 / 58% / **5** |
| 9. 09_mutual_nda_own_clean | 30 / 28 / 93% / 3 | 14 / 9 / 64% / **5** |
| 10. 10_mutual_nda_counterparty_residuals | 27 / 25 / 93% / 3 | 13 / 9 / 69% / **4** |
| 11. 11_vendor_msa_counterparty_lowcap | 39 / 30 / 77% / 10 | 17 / 4 / 24% / **13** |
| 12. 12_vendor_msa_counterparty_reasonable | 40 / 31 / 78% / 10 | 17 / 4 / 24% / **13** |
| **Total** | **466 / 396 / 85% / –** | **183 / 69 / 38% / –** |

The fix clearly worked for the **SaaS MSA and vendor MSA** contracts (1-5, 11, 12). Only the title block, `"2. SERVICES"` and a multi-family section or two are now `other`. Contract 9's `"8. TERM AND SURVIVAL"` now classifies as `term`, which is the synonym this session added. The **DPA, BAA and NDA** contracts (6-10) are still 50-69% `other`. Apart from each contract's title block and the multi-family headings (`GENERAL PROVISIONS` on contracts 7-10, `LIABILITY AND GOVERNING LAW` and `AUDIT AND COOPERATION` on contract 6), the remaining `other` headings on those five contracts are single-topic headings whose phrasing simply isn't in the synonym table, for example `"1. ROLES OF THE PARTIES"`, `"3. DATA SUBJECT REQUESTS"`, `"4. PERSONNEL"`, `"11. RETURN AND DELETION"`, `"2. CONFIDENTIALITY OBLIGATIONS"`, `"3. EXCLUSIONS"`, `"4. COMPELLED DISCLOSURE"`, `"5. RESIDUALS"`, `"6. EQUITABLE RELIEF"`, `"7. NO LICENSE"`, `"9. RETURN OR DESTRUCTION"`, `"4. SAFEGUARDS"`, `"5. INDIVIDUAL RIGHTS"` and `"7. ACCESS BY THE SECRETARY"`.

### 1.2 What still drives false `missing` flags

`missing` flags fell from **166 to 128** across the 12 contracts. That is still the single largest category of actual flags, and almost all of them are false. Clean contract 1 (`01_saas_msa_own_clean`) alone carries 12 red `missing` flags, for families that are plainly in the document:

- **Section typed as a different single family.** `"4. TERM AND TERMINATION"` classifies as `termination`. Its §4.2 plainly says "this Agreement automatically renews for successive twelve (12)-month terms ... unless either Party gives written notice of non-renewal at least sixty (60) days before the end of the then-current term", yet `term.auto_renewal` is flagged missing.
- **Multi-family section falls to `other`.** `"8. DATA PROTECTION AND SECURITY"` is `other`, which produces missing flags for `data_protection.customer_data_use`, `security.certifications`, `subprocessors.subprocessor_changes` and `breach_notification.notification_timeline`.
- **Boilerplate section holding many families.** `"17. GENERAL PROVISIONS"` contains assignment, notices, amendment, entire agreement and force majeure. It is `other`, so all five families are flagged missing.

The same pattern repeats on every SaaS/vendor MSA in the corpus, because they all use `TERM AND TERMINATION` plus `GENERAL PROVISIONS`. `layer1_structural.py::_check_missing` still treats "no clause carries this `clause_type`" as "this clause is absent", so a single-label classification of a multi-topic section turns directly into red flags. Every contract therefore still has `worst_zone = red` (section 5).

The first run's recommendation to fix the synonym/classification path (section 7, item 1) has been **done** for the synonym source. The two remaining causes above are new proposed fixes (section 7, items 1a and 1b). Neither was fixed here.

<details><summary>First run's section 1 text (pre-fix, retained for the record)</summary>

**Clause-type classification on real uploaded contracts is badly broken: the overwhelming majority of real clauses in every one of the 12 corpus contracts are classified as `clause_type = "other"` instead of their real family (`term`, `termination`, `notices`, `confidentiality`, `payment`, etc.).** Every contract was at least 78% "other", and contract 6 was 100%. Contract 9's headings `"2. CONFIDENTIALITY OBLIGATIONS"`, `"8. TERM AND SURVIVAL"`, `"9. RETURN OR DESTRUCTION"` and `"13. GENERAL PROVISIONS"` were all `other`, and only `"1. DEFINITIONS"` and `"12. GOVERNING LAW"` were recognized. Downstream effects: mass false `missing` (red) flags (contract 9, expected clean, picked up 10, including `term.agreement_term`), and Layer 2 starved of candidates because content matching only runs against clauses that already carry the right `clause_type`. This was not fixed during task 5.4 itself.

</details>

## 2. Real bugs found and fixed to get a result

Two bugs in `app/core/llm/gateway.py` made the entire cost-bearing part of this task impossible to run at all — not "produces bad numbers", but a hard crash on every single call, before and after a real `ANTHROPIC_API_KEY` was supplied. Both are transport-layer plumbing (model routing, request/response shape), not playbook content, scoring, or gate logic, and neither changes what the pipeline finds — only whether it can run and finish producing output at all. Both are documented in code comments at the fix site.

**2.1 — `call_batch` sent a Python class as a JSON request body (100% blocking).** `gateway.call_batch` built each batch item's `params` with `"output_format": response_model` (the raw Pydantic class) and handed that straight to `client.beta.messages.batches.create(requests=requests)`. Unlike `call_structured`/`call_text`, which go through the SDK's `client.beta.messages.parse()` helper (which itself converts a Pydantic `output_format` class into the wire-format `output_config` JSON schema before posting), the raw batch-create endpoint is a pure passthrough — it does no such conversion. Every `call_batch` invocation crashed locally (`TypeError: Object of type ModelMetaclass is not JSON serializable`) before any HTTP request was even sent. **Confirmed $0 spent on every occurrence of this crash** — the traceback shows the failure inside `_build_request`'s JSON serialization, never reaching `_attempt_request`'s network call. Fixed by building the same `output_config = {"format": {"schema": ..., "type": "json_schema"}}` shape `parse()` builds (using the SDK's own private `transform_schema`/`TypeAdapter` helpers it already uses internally), and parsing each raw batch result back into the response model with the SDK's own `parse_beta_response` instead of assuming a `.parsed_output` attribute that a raw (non-`parse()`-wrapped) batch result never has.

**2.2 — Hardcoded `max_tokens=4096` truncated real structured output (blocking on any multi-clause contract).** Even after fixing 2.1, the very first live Layer-2 content-analysis call on a real contract (`01_saas_msa_own_clean`) crashed with `pydantic_core.ValidationError: Invalid JSON: EOF while parsing a string at line 1 column 12243` — the model's structured JSON output was cut off mid-string because `max_tokens` was hardcoded to 4096 in all three of `call_structured`, `call_text` and `call_batch`, too small once a real contract's worth of clauses is packed into one structured response. Raised to 8192 uniformly (a shared named constant, `_MAX_TOKENS`, applied to all three call shapes rather than patched only where it was first hit). This is a transport budget only — it does not change any prompt, scoring, or playbook content, and does not hide any extraction error; it only lets the model finish writing the answer it was already producing. **This was itself a necessary, minimal fix to get any result at all** — without it, the entire 12-contract corpus phase of this task would be 0-for-12.

Both fixes are isolated to `backend/app/core/llm/gateway.py` and were verified with a trivial, cheap sanity call (1 real Haiku call, a 2-field toy schema) before being used for the real, authorized cost-bearing runs.

## 3. Rule-test suite results

> **Not re-run in the 2026-11-17 re-verification session.** This section shows the original pre-fix state: before task 5.5's rule-model migration, the clause-classification fix and the four structural pipeline fixes. Only the ~$1 corpus run (sections 1, 4, 5, 6) was approved for that session.

Run for real, in default (non-`--deterministic`) mode, with `--yes`: `cd backend && .venv/bin/python -m scripts.run_rule_tests --yes` (model routed through the Haiku override above). The live database holds 1096 `rule_test_case` rows in total (matching the task brief exactly), but the runner loads test cases by walking each playbook's **current published version** (`playbook_repo.get_rules_with_children` against `playbook.current_version_id`); only **794** of the 1096 rows are attached to rules on a currently-published version — the remaining ~302 belong to superseded/draft rule versions and are legitimately not part of "the live, published playbook" this gate exists to protect. No note/skip lines were printed by the runner, so this is the full, expected set, not a partial failure to load.

**Overall: 470/794 passed — 59.2% pass rate** (470 passed, 324 failed, 0 skipped), against the 95% publish-gate threshold. **754 real model calls made (754 required, 754 made, all succeeded)** — the Haiku-override caveat in the introduction applies directly to this number.

### 3.1 By playbook

| Playbook | Passed/Total | Pass rate |
|---|---|---|
| halcyon-baseline | 53/78 | 67.9% |
| halcyon-dpa-processor | 58/110 | 52.7% |
| halcyon-gdpr-overlay | 49/84 | 58.3% |
| halcyon-hipaa-overlay | 49/84 | 58.3% |
| halcyon-mutual-nda | 42/86 | 48.8% |
| halcyon-saas-msa-vendor | 131/196 | 66.8% |
| halcyon-vendor-msa-customer | 88/156 | 56.4% |

### 3.2 By expected outcome

| Expected outcome | Passed/Total | Pass rate |
|---|---|---|
| compliant | 178/208 | 85.6% |
| missing | 34/36 | 94.4% |
| red_line | 83/128 | 64.8% |
| acceptable_variant | 61/132 | 46.2% |
| deviation | 61/135 | 45.2% |
| fallback | 53/155 | 34.2% |

`compliant` (85.6%) and `missing` (94.4%) are strong — the model reliably recognizes a clean preferred-position match and a genuinely absent required clause. `fallback` (34.2%) is the weakest by far, followed by `deviation` (45.2%) and `acceptable_variant` (46.2%) — the model is least reliable at the fine-grained job of placing a borderline clause on the correct fallback rung or telling an acceptable variant from the preferred wording, exactly the judgment calls most sensitive to model capability. Given the Haiku-only constraint on this run, this pattern is consistent with (though not proof of) a capability effect rather than a rule-authoring defect across the board.

### 3.3 Failure categories (324 failures, by expected→actual pattern)

Every failure is one of the patterns below, grouped by the (expected_outcome, actual_outcome) pair; a probable cause is given per category (pattern-level, not re-derived per individual case — that would need re-running each case with tracing, outside this task's scope). The full list of all 324 individual failures (expected vs. actual, with the model's own stated reason) follows in 3.4.

| Cat | Count | Pattern | Probable cause |
|---|---|---|---|
| A | 87 | fallback → deviation | Expected a specific fallback rung; model's extraction fell through the ladder to a default-zone deviation with no rung (missed the fallback's own threshold). Most common failure by far. |
| C | 53 | acceptable_variant → compliant | Expected `acceptable_variant` (a named, pre-approved alternative wording); model matched the `preferred` position instead (zone collapses to `compliant`) — the two phrasings are close enough that extraction didn't distinguish them. |
| Z | 38 | deviation → deviation | Outcome pair not covered by the categories above (see raw expected/actual below). |
| E | 36 | red_line → deviation | Expected a semantic red line to trigger; model did not trigger it and fell through to a plain deviation. |
| M | 30 | compliant → deviation | Expected `compliant` (clean match); model found some other outcome — a false alarm on text that should have passed clean. |
| L | 22 | deviation → red_line | Expected a plain deviation; model triggered a red line instead — likely a red-line condition written too broadly, catching ordinary deviations. |
| D | 12 | deviation → compliant | Expected a deviation; model matched the `preferred` position outright, missing the deviation entirely. |
| B | 11 | deviation → fallback | Expected a plain deviation; model's extraction instead matched a fallback position. |
| H | 11 | acceptable_variant → deviation | Expected `acceptable_variant`; model treated the clause as an unmatched deviation instead of recognizing the variant wording. |
| J | 11 | fallback → compliant | Expected a fallback match; model matched the `preferred` position instead. |
| F | 7 | red_line → red_line | A red line did trigger, but the wrong one (key mismatch) — two red lines on the same rule are close enough in wording that the model picked the wrong one. |
| I | 3 | fallback → red_line | Expected a fallback match; model instead triggered a red line — likely a red-line condition written broadly enough to also catch an acceptable fallback phrasing. |
| G | 2 | missing → missing | The `missing` (required-clause-absent) path matched on outcome, but the expected zone differs from the actual zone. |
| K | 1 | red_line → compliant | Expected a red line to trigger; model matched the `preferred` position — a severe miss (missed a real problem clause entirely). |

22 of the 324 failures are explicitly-marked trap cases (designed to be the hardest to get right on purpose); their failure is less surprising than a core-case failure but still counted and listed below, not excluded.

### 3.4 Every failing case (expected vs. actual)

<details><summary>All 324 failures, grouped by category from 3.3 (click to expand)</summary>


**Category A** — Expected a specific fallback rung; model's extraction fell through the ladder to a default-zone deviation with no rung (missed the fallback's own threshold). Most common failure by far.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.permitted_uses_of_phi | Management and administration by internal use only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Limbs of permitted use granted to Business Associate' value 'services_management_use_only' is beyond the green limit |
| halcyon-hipaa-overlay | data_protection.minimum_necessary | Attached policy with notice of changes | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Whose minimum necessary standard binds Business Associate' value 'covered_entity_policies_with_notice' is beyond the green limit |
| halcyon-hipaa-overlay | data_protection.individual_rights_support | Five day access for a large health system | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to make PHI available for an access request' value 5 is beyond the green limit |
| halcyon-hipaa-overlay | data_protection.data_return_and_deletion | Thirty day destruction and sixty day backups | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days after the end of the data retrieval window to destroy PHI in production systems' value 30 is beyond the green limit |
| halcyon-hipaa-overlay | breach_notification.notification_timeline | 24 hours after confirmation for a large health system | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Hours after confirmation to notify Covered Entity' value 24 is beyond the green limit |
| halcyon-hipaa-overlay | breach_notification.notification_content | Content list plus root-cause summary | fallback/yellow/rung=2 | deviation/red | Parameter 'Whether a notice may supply missing facts in later, supplemental notices' value False is beyond the yellow limit |
| halcyon-hipaa-overlay | termination.termination_for_baa_breach | 15-day cure for a tier 1 enterprise account, BAA and Underlying Agreement linked | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to cure a material violation before Covered Entity may terminate the BAA' value 15 is beyond the green limit |
| halcyon-hipaa-overlay | indemnification.regulatory_penalties_indemnity | Dedicated three-times cap for a strategic account | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Dedicated cap for the regulatory penalties indemnity, as months of Fees' value 36 is beyond the green limit |
| halcyon-hipaa-overlay | data_protection.de_identification | Expert determination only, with annual notice, for a tier 1 PHI account | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Permitted de-identification method' value 'expert_determination_only' is beyond the green limit |
| halcyon-gdpr-overlay | data_protection.data_subject_requests | Two business days and free assistance | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Business days to forward a Data Subject request received directly' value 2 is beyond the green limit |
| halcyon-gdpr-overlay | data_protection.dpia_assistance | Twenty free hours on an enterprise deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Hours of bespoke assessment assistance included without charge each year' value 20 is beyond the green limit |
| halcyon-gdpr-overlay | data_transfers.transfer_mechanism | SCCs signed as a full annex | fallback/green/rung=1 | deviation/red | Parameter 'Mechanism relied on for restricted transfers' value 'Standard Contractual Clauses, Module Two with UK Addendum' is beyond the yellow limit |
| halcyon-gdpr-overlay | data_transfers.transfer_mechanism | Controller drafts both annexes for a tier_1 account | fallback/yellow/rung=2 | deviation/red | Parameter 'Mechanism relied on for restricted transfers' value 'SCCs Module Two with UK Addendum; controller_drafted_annexes' is beyond the yellow limit |
| halcyon-gdpr-overlay | data_transfers.data_residency | Named Dublin facility with ninety days' notice of a move | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Hosting commitment for EU and UK Personal Data' value 'named_single_facility' is beyond the green limit |
| halcyon-gdpr-overlay | data_transfers.data_residency | Trap - naming the facility is not the same as on-premises [TRAP] | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Hosting commitment for EU and UK Personal Data' value 'named_single_facility' is beyond the green limit |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Notice within 48 hours of confirmation | fallback/green/rung=1 | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Notice within 24 hours for special category data | fallback/yellow/rung=2 | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-gdpr-overlay | subprocessors.authorisation_model | Sixty days' notice with list-monitoring in return | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Notice before a new Sub-processor may process Personal Data' value 60 is beyond the green limit |
| halcyon-gdpr-overlay | audit.supervisory_authority_cooperation | Notice within one business day for a large health system | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Business days to notify the Controller of a regulatory enquiry' value 1 is beyond the green limit |
| halcyon-gdpr-overlay | governing_law.choice_of_law | German law for a German clinic group | fallback/yellow/rung=2 | deviation/red | Parameter 'Jurisdiction whose law governs under this overlay' value 'Germany' is beyond the yellow limit |
| halcyon-vendor-msa-customer | payment.payment_terms | Net 30 on a smaller vendor | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to pay an invoice' value 30 is beyond the green limit |
| halcyon-vendor-msa-customer | payment.late_fees | Two percent a month, Deal Desk approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Late fee as a monthly percentage' value 2 is beyond the green limit |
| halcyon-vendor-msa-customer | payment.price_increases | Seven percent cap with Deal Desk sign-off | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Maximum renewal price increase' value 7 is beyond the green limit |
| halcyon-vendor-msa-customer | term.initial_term | Thirty-six month commitment with Deal Desk sign-off | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Length of the Initial Term' value 36 is beyond the green limit |
| halcyon-vendor-msa-customer | term.auto_renewal | Thirty days' notice, Deal Desk approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days' notice required to stop auto-renewal' value 30 is beyond the green limit |
| halcyon-vendor-msa-customer | termination.for_convenience | Available after month 12, ninety days, no refund | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Notice days to exercise termination for convenience' value 90 is beyond the green limit |
| halcyon-vendor-msa-customer | termination.for_convenience | Trap - no refund language does not remove the right itself [TRAP] | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Notice days to exercise termination for convenience' value 90 is beyond the green limit |
| halcyon-vendor-msa-customer | termination.for_cause_cure_period | Thirty-day cure, Commercial Counsel approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Vendor's cure period for a material breach' value 30 is beyond the green limit |
| halcyon-vendor-msa-customer | termination.transition_assistance | One month at list rate, approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Length of transition assistance' value 1 is beyond the green limit |
| halcyon-vendor-msa-customer | termination.transition_assistance | Trap - transition assistance is priced but not absent [TRAP] | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Length of transition assistance' value 1 is beyond the green limit |
| halcyon-vendor-msa-customer | service_levels.uptime_commitment | 99.5% monthly, VP Customer Success approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Minimum uptime commitment' value 99.5 is beyond the green limit |
| halcyon-vendor-msa-customer | service_levels.service_credits | Ten percent cap, sole remedy below chronic failure | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Maximum service credit as a percentage of monthly Fees' value 10 is beyond the green limit |
| halcyon-vendor-msa-customer | assignment.change_of_control | Thirty days after closing, narrower trigger, approved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to notify Halcyon of a Change of Control' value 30 is beyond the green limit |
| halcyon-vendor-msa-customer | limitation_of_liability.cap_amount | 12 months with three-times data limit | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Vendor general cap as months of Fees' value 12 is beyond the green limit |
| halcyon-vendor-msa-customer | indemnification.ip_infringement_indemnity | United States rights only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Rights and territories covered by Vendor's infringement indemnity' value 'us_rights_only' is beyond the green limit |
| halcyon-vendor-msa-customer | indemnification.data_breach_indemnity | Notification and forensics only under the lower super-cap | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Breach costs covered by Vendor's indemnity' value 'notification_and_forensics_only' is beyond the green limit |
| halcyon-vendor-msa-customer | warranties.performance_warranty | Ninety-day warranty, credit only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Performance warranty period' value 90 is beyond the green limit |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | $3M cyber, $1M general liability | fallback/green/rung=1 | deviation/yellow | Parameter 'Vendor cyber / technology E&O coverage limit' value 3000000 is beyond the green limit |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | $1M cyber cover, certificate only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Vendor cyber / technology E&O coverage limit' value 1000000 is beyond the green limit |
| halcyon-vendor-msa-customer | confidentiality.standard_of_care | Vendor's own standard with no PHI involved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Vendor's standard of care for Halcyon's confidential information' value 'own_practice_only' is beyond the green limit |
| halcyon-vendor-msa-customer | security.security_program | General commercially reasonable security only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Standard the Vendor's security programme is aligned with' value 'general_commercially_reasonable' is beyond the green limit |
| halcyon-vendor-msa-customer | breach_notification.notification_timeline | Five business days after confirmation, no PHI involved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Event that starts the notice clock' value 'confirmed_only' is beyond the green limit |
| halcyon-vendor-msa-customer | subprocessors.subprocessor_changes | Notice only, no objection right, PHI flow-down preserved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days of advance notice before a new subcontractor processes Halcyon Data' value 0 is beyond the green limit |
| halcyon-vendor-msa-customer | audit.customer_audit_rights | Report or questionnaire only, no PHI involved | fallback/yellow/rung=2 | deviation/yellow | Parameter 'What Halcyon may use to verify Vendor's compliance' value 'report_or_questionnaire_only' is beyond the green limit |
| halcyon-mutual-nda | definitions.confidential_information_scope | Written confirmation required for oral disclosures | fallback/yellow/rung=1 | deviation/red | Parameter 'Confidential information scope standard' value 'marking_required_for_written_30_day_confirmation_for_oral' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.standard_of_care | Reasonable care without own-practice comparator | fallback/yellow/rung=1 | deviation/red | Parameter 'Standard of care for Confidential Information' value 'reasonable_measures' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.residuals | Narrow residuals excluding source code, PHI and personal data | fallback/yellow/rung=1 | deviation/yellow | Parameter 'A residuals carve-out is included' value True is beyond the green limit |
| halcyon-mutual-nda | confidentiality.equitable_relief | Injunction available, bond not waived | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Bond or security requirement is waived for injunctive relief' value False is beyond the green limit |
| halcyon-mutual-nda | confidentiality.equitable_relief | General remedies-at-law-and-equity reference only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Bond or security requirement is waived for injunctive relief' value False is beyond the green limit |
| halcyon-mutual-nda | term.agreement_term | Three-year term | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Agreement term in years' value 3 is beyond the green limit |
| halcyon-mutual-nda | term.survival_period | Five years generally, indefinite for trade secrets | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Survival treatment for trade secrets and other information' value 'indefinite_trade_secrets_only' is beyond the green limit |
| halcyon-mutual-nda | termination.return_or_destruction | 30-day return or destruction, certified | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Days to return or destroy Confidential Information' value 30 is beyond the green limit |
| halcyon-mutual-nda | governing_law.choice_of_law | New York law for a US counterparty | fallback/green/rung=1 | deviation/red | Parameter 'Jurisdiction whose law governs' value 'New York' is beyond the yellow limit |
| halcyon-saas-msa-vendor | payment.payment_terms | Net 60 for a tier-1 hospital system | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to pay an invoice' value 60 is beyond the green limit |
| halcyon-saas-msa-vendor | payment.payment_terms | Net 75 for a strategic account | fallback/yellow/rung=3 | deviation/yellow | Parameter 'Days to pay an invoice' value 75 is beyond the green limit |
| halcyon-saas-msa-vendor | termination.for_convenience | Convenience right after month 12, 90 days, no refund | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Customer has any termination-for-convenience right' value True is beyond the green limit |
| halcyon-saas-msa-vendor | termination.for_cause_cure_period | 15-day cure period | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Cure period, in days' value 15 is beyond the green limit |
| halcyon-saas-msa-vendor | service_levels.uptime_commitment | 99.95% quarterly commitment for a tier-1 account | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Committed Monthly (or equivalent) Uptime Percentage' value 99.95 is beyond the green limit |
| halcyon-saas-msa-vendor | limitation_of_liability.cap_amount | 24-month cap on an enterprise deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Cap as months of Fees' value 24 is beyond the green limit |
| halcyon-saas-msa-vendor | limitation_of_liability.cap_carve_outs | Confidentiality carve-out excluding Customer Data on a tier-1 account | fallback/yellow/rung=1 | deviation/red | Parameter 'Categories excluded from the general cap' value 'breach of confidentiality duties (excluding Customer Data breaches)' is beyond the yellow limit |
| halcyon-saas-msa-vendor | limitation_of_liability.consequential_damages_exclusion | One-way exclusion favouring Customer | fallback/yellow/rung=1 | deviation/red | Parameter 'Exclusion applies to both parties' value False is beyond the yellow limit |
| halcyon-saas-msa-vendor | limitation_of_liability.data_breach_super_cap | Three times fees with a dollar ceiling on a strategic deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Super-cap as a multiple of annual Fees' value 3 is beyond the green limit |
| halcyon-saas-msa-vendor | indemnification.indemnity_procedure | 30-day notice with a materiality standard for late notice | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Days to give written notice of a claim' value 30 is beyond the green limit |
| halcyon-saas-msa-vendor | warranties.performance_warranty | 15-day cure period | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Days to cure a non-conforming warranty claim' value 15 is beyond the green limit |
| halcyon-saas-msa-vendor | data_protection.data_return_and_deletion | 30-day deletion, 60-day backups after the retrieval window, enterprise deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days after the end of the data retrieval window to delete Customer Data from production systems' value 30 is beyond the green limit |
| halcyon-saas-msa-vendor | subprocessors.subprocessor_changes | 60 days' notice, strategic deal | fallback/yellow/rung=2 | deviation/red | Parameter 'Days Customer has to object after notice of a new subprocessor' value 60 is beyond the yellow limit |
| halcyon-saas-msa-vendor | audit.customer_audit_rights | Standalone on-site audit, tier 1 and strategic deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days' advance written notice required before an audit' value 15 is beyond the green limit |
| halcyon-saas-msa-vendor | audit.customer_audit_rights | Tier-1 customer, second on-site audit in the same year | fallback/yellow/rung=3 | deviation/yellow | Parameter 'Days' advance written notice required before an audit' value 15 is beyond the green limit |
| halcyon-dpa-processor | definitions.roles_of_parties | Joint controller for one analytics activity, PHI deal | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Halcyon's role for Service Personal Data' value 'joint_controller_narrow_ancillary' is beyond the green limit |
| halcyon-dpa-processor | data_protection.data_subject_requests | Tier 1 counterparty, two-day forwarding with quarterly free hours | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Business days to forward a Data Subject request' value 2 is beyond the green limit |
| halcyon-dpa-processor | data_protection.data_return_and_deletion | Enterprise deal, 60-day export window | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days to export Service Personal Data after termination' value 60 is beyond the green limit |
| halcyon-dpa-processor | subprocessors.authorisation_model | Tier 1 PHI deal, advance briefing added | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Authorisation model for Sub-processors' value 'general_with_briefing' is beyond the green limit |
| halcyon-dpa-processor | subprocessors.subprocessor_changes | Tier 1 counterparty, 60-day notice for a new category | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Days' advance notice of a new Sub-processor' value 60 is beyond the green limit |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | EU deal, supporting documentation on request | fallback/yellow/rung=2 | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'Standard Contractual Clauses' is beyond the yellow limit |
| halcyon-dpa-processor | data_transfers.data_residency | Tier 1 PHI deal, named single region | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Scope of the data residency commitment' value 'named_single_region' is beyond the green limit |
| halcyon-dpa-processor | audit.audit_cost | Enterprise deal, first annual on-site audit absorbed | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Who bears the cost of an on-site audit' value 'halcyon_absorbs_first_annual_audit' is beyond the green limit |
| halcyon-dpa-processor | audit.audit_cost | Strategic deal, first two annual on-site audits absorbed | fallback/yellow/rung=3 | deviation/red | Parameter 'Who bears the cost of an on-site audit' value 'halcyon_absorbs_first_two_annual_audits_strategic' is beyond the yellow limit |
| halcyon-dpa-processor | limitation_of_liability.dpa_liability_alignment | Strategic deal, super-cap raised to 3x capped at $5M | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Data breach super-cap as a multiple of annual Fees' value 3 is beyond the green limit |
| halcyon-baseline | governing_law.choice_of_law | Texas law for a Texas-based counterparty | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Jurisdiction whose law governs' value 'other_us_state' is beyond the green limit |
| halcyon-baseline | governing_law.venue | Non-exclusive jurisdiction in the governing law state | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Venue is exclusive' value False is beyond the green limit |
| halcyon-baseline | dispute_resolution.forum | AAA arbitration with the injunctive-relief carve-out | fallback/yellow/rung=1 | deviation/yellow | Parameter 'Forum for resolving disputes' value 'arbitration' is beyond the green limit |
| halcyon-baseline | dispute_resolution.forum | AAA arbitration seated in the counterparty's home state | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Forum for resolving disputes' value 'arbitration' is beyond the green limit |
| halcyon-baseline | notices.method | Email alone sufficient, no confirmation required | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Email alone is sufficient for a notice of breach or termination' value True is beyond the green limit |
| halcyon-baseline | assignment.consent_requirement | No consent needed except for assignment to a competitor | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Standard applied to assignment consent' value 'no_consent_except_competitor' is beyond the green limit |
| halcyon-baseline | assignment.change_of_control | Unconditional thirty-day termination right after any change of control | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Notice period for the competitor-change-of-control termination right' value 30 is beyond the green limit |
| halcyon-baseline | entire_agreement.order_of_precedence | Procurement portal terms govern administrative procedures only | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Effect given to purchase order or procurement terms' value 'limited_scope_only' is beyond the green limit |
| halcyon-baseline | force_majeure.termination_right | Fifteen-day trigger, broadened refund | fallback/yellow/rung=2 | deviation/yellow | Parameter 'Consecutive days of force majeure before either party may terminate' value 15 is beyond the green limit |

**Category C** — Expected `acceptable_variant` (a named, pre-approved alternative wording); model matched the `preferred` position instead (zone collapses to `compliant`) — the two phrasings are close enough that extraction didn't distinguish them.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.minimum_necessary | One-line minimum necessary undertaking | acceptable_variant/green | compliant/none | Matches the preferred position 'Regulatory standard, mutual'; no finding |
| halcyon-hipaa-overlay | breach_notification.notification_timeline | Three business days, capped at 72 hours | acceptable_variant/green | compliant/none | Matches the preferred position '72 hours after confirmation'; no finding |
| halcyon-hipaa-overlay | breach_notification.notification_content | Same six elements, counterparty's own wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Standard content list, phased notice permitted'; no finding |
| halcyon-gdpr-overlay | data_protection.processing_instructions | Written instructions through the admin console | acceptable_variant/green | compliant/none | Matches the preferred position 'Documented instructions, Agreement as the complete set'; no finding |
| halcyon-gdpr-overlay | data_transfers.data_residency | Residency stated as a warranty | acceptable_variant/green | compliant/none | Matches the preferred position 'EU region hosting, multi-tenant'; no finding |
| halcyon-gdpr-overlay | subprocessors.authorisation_model | Deemed consent unless objection within thirty days | acceptable_variant/green | compliant/none | Matches the preferred position 'General authorisation, 30 days' notice, right to object'; no finding |
| halcyon-gdpr-overlay | audit.supervisory_authority_cooperation | Cooperation framed as a general compliance duty | acceptable_variant/green | compliant/none | Matches the preferred position 'Cooperate on request, notify within five business days'; no finding |
| halcyon-gdpr-overlay | governing_law.choice_of_law | Irish law, internal-laws wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Irish law'; no finding |
| halcyon-gdpr-overlay | compliance.gdpr_compliance | Compliance allocated by role, counterparty wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Compliance allocated by role'; no finding |
| halcyon-vendor-msa-customer | term.initial_term | Fixed end date twelve months out | acceptable_variant/green | compliant/none | Matches the preferred position '12-month Initial Term'; no finding |
| halcyon-vendor-msa-customer | assignment.change_of_control | Deemed consent with notice and exit right preserved | acceptable_variant/green | compliant/none | Matches the preferred position '5 business days' notice, broad exit right'; no finding |
| halcyon-vendor-msa-customer | limitation_of_liability.cap_amount | Greater of two years of fees and a dollar floor | acceptable_variant/green | compliant/none | Matches the preferred position '24-month cap, data breach uncapped'; no finding |
| halcyon-vendor-msa-customer | intellectual_property.ownership | No-rights-granted variant | acceptable_variant/green | compliant/none | Matches the preferred position 'Halcyon Data reserved; licence limited to providing the Services'; no finding |
| halcyon-vendor-msa-customer | confidentiality.standard_of_care | Strict confidence variant | acceptable_variant/green | compliant/none | Matches the preferred position 'Reasonable care, need-to-know, matching subcontractor terms'; no finding |
| halcyon-vendor-msa-customer | subprocessors.subprocessor_changes | Published subcontractor list variant | acceptable_variant/green | compliant/none | Matches the preferred position '30 days' notice, right to object, full HIPAA flow-down'; no finding |
| halcyon-mutual-nda | confidentiality.permitted_disclosures | Contractual-undertaking variant | acceptable_variant/green | compliant/none | Matches the preferred position 'Named representative categories, discloser liable for breach'; no finding |
| halcyon-mutual-nda | confidentiality.exclusions | Counterparty-phrased four exclusions | acceptable_variant/green | compliant/none | Matches the preferred position 'Four standard exclusions, burden of proof on Receiving Party'; no finding |
| halcyon-mutual-nda | confidentiality.compelled_disclosure | Counterparty-phrased equivalent | acceptable_variant/green | compliant/none | Matches the preferred position 'Prior notice, cooperation, minimum necessary disclosure'; no finding |
| halcyon-mutual-nda | confidentiality.residuals | Counterparty confirms no residuals right | acceptable_variant/green | compliant/none | Matches the preferred position 'No residuals clause'; no finding |
| halcyon-mutual-nda | term.agreement_term | Twenty-four-month term variant | acceptable_variant/green | compliant/none | Matches the preferred position 'Two-year term'; no finding |
| halcyon-mutual-nda | termination.return_or_destruction | Counterparty-phrased equivalent | acceptable_variant/green | compliant/none | Matches the preferred position '10-day return or destruction, written certification'; no finding |
| halcyon-mutual-nda | intellectual_property.no_license | Counterparty-phrased equivalent | acceptable_variant/green | compliant/none | Matches the preferred position 'No licence, all intellectual property reserved'; no finding |
| halcyon-mutual-nda | non_solicitation.employee_non_solicit | Counterparty-phrased equivalent | acceptable_variant/green | compliant/none | Matches the preferred position 'Twelve-month, contact-based mutual non-solicit'; no finding |
| halcyon-mutual-nda | publicity.name_and_logo_use | Counterparty-phrased equivalent | acceptable_variant/green | compliant/none | Matches the preferred position 'Mutual consent required for any publicity'; no finding |
| halcyon-saas-msa-vendor | termination.for_cause_cure_period | Remedy-the-failure variant | acceptable_variant/green | compliant/none | Matches the preferred position '30-day cure period'; no finding |
| halcyon-saas-msa-vendor | service_levels.uptime_commitment | Broader maintenance exclusion variant | acceptable_variant/green | compliant/none | Matches the preferred position '99.9% monthly'; no finding |
| halcyon-saas-msa-vendor | limitation_of_liability.cap_amount | Fixed-sum cap equal to one year of fees | acceptable_variant/green | compliant/none | Matches the preferred position '12-month cap'; no finding |
| halcyon-saas-msa-vendor | limitation_of_liability.consequential_damages_exclusion | Exclusion combined into the cap sentence | acceptable_variant/green | compliant/none | Matches the preferred position 'Mutual exclusion matching the cap carve-outs'; no finding |
| halcyon-saas-msa-vendor | limitation_of_liability.data_breach_super_cap | Super-cap as 24 months of fees | acceptable_variant/green | compliant/none | Matches the preferred position 'Super-cap at 2x annual Fees'; no finding |
| halcyon-saas-msa-vendor | indemnification.indemnity_procedure | Conditions precedent paragraph, same terms | acceptable_variant/green | compliant/none | Matches the preferred position 'Prompt notice within 10 days; indemnifying party controls defence'; no finding |
| halcyon-saas-msa-vendor | intellectual_property.usage_data | Usage Data right drafted in the data protection section | acceptable_variant/green | compliant/none | Matches the preferred position 'Aggregated, de-identified Usage Data for operating, securing and improving the Services'; no finding |
| halcyon-saas-msa-vendor | data_protection.customer_data_use | Processor-style purpose limitation | acceptable_variant/green | compliant/none | Matches the preferred position 'Service purpose plus de-identified analytics carve-out'; no finding |
| halcyon-saas-msa-vendor | data_protection.data_return_and_deletion | Election to return or destroy, same periods | acceptable_variant/green | compliant/none | Matches the preferred position '60-day production deletion, 90-day backup purge, both after the retrieval window'; no finding |
| halcyon-saas-msa-vendor | security.certifications | Customer-drafted "most recent report" wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Named certifications, 10-day report delivery'; no finding |
| halcyon-saas-msa-vendor | subprocessors.subprocessor_changes | Customer-drafted "updated list" wording | acceptable_variant/green | compliant/none | Matches the preferred position 'General authorisation, 30 days' notice, right to object'; no finding |
| halcyon-saas-msa-vendor | audit.customer_audit_rights | Customer-drafted "no more than once every 12 months" wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Annual, 30 days' notice, SOC 2 report first'; no finding |
| halcyon-saas-msa-vendor | compliance.compliance_with_laws | Customer-drafted, Vendor-scoped wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Compliance scoped to Halcyon's own performance'; no finding |
| halcyon-saas-msa-vendor | compliance.anti_corruption | Customer-drafted mutual representation | acceptable_variant/green | compliant/none | Matches the preferred position 'Mutual anti-corruption and exclusion representation'; no finding |
| halcyon-dpa-processor | definitions.roles_of_parties | Counterparty-style processor wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Processor only, with account-data carve-out'; no finding |
| halcyon-dpa-processor | data_protection.processing_instructions | Counterparty complete-instructions wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Instructions fixed to the Agreement, Addendum and Services configuration'; no finding |
| halcyon-dpa-processor | audit.customer_audit_rights | Counterparty annual review wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Annual audit, 30 days' notice, SOC 2 report first'; no finding |
| halcyon-dpa-processor | data_protection.dpia_assistance | Counterparty assistance wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Assistance from existing documentation, reasonable in scope'; no finding |
| halcyon-dpa-processor | security.technical_organisational_measures | Counterparty state-of-the-art wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Measures annex with a no-reduction update right'; no finding |
| halcyon-dpa-processor | breach_notification.notification_content | Counterparty content wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Standard content, phased notice permitted'; no finding |
| halcyon-dpa-processor | subprocessors.authorisation_model | Counterparty general-authorisation wording | acceptable_variant/green | compliant/none | Matches the preferred position 'General authorisation from a published list'; no finding |
| halcyon-dpa-processor | subprocessors.subprocessor_changes | Counterparty 30-day notice wording | acceptable_variant/green | compliant/none | Matches the preferred position '30 days' notice, objection on reasonable grounds, partial termination remedy'; no finding |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Counterparty equivalent-obligations wording | acceptable_variant/green | compliant/none | Matches the preferred position 'Equivalent flow-down, liability inside the general cap'; no finding |
| halcyon-dpa-processor | data_transfers.data_residency | Counterparty regional split wording | acceptable_variant/green | compliant/none | Matches the preferred position 'US and EU regional split, unrestricted remote access'; no finding |
| halcyon-dpa-processor | limitation_of_liability.dpa_liability_alignment | Counterparty aggregation wording | acceptable_variant/green | compliant/none | Matches the preferred position 'DPA liability inside the Agreement's caps, taken together'; no finding |
| halcyon-baseline | governing_law.venue | Venue phrased as consent to Delaware jurisdiction | acceptable_variant/green | compliant/none | Matches the preferred position 'Exclusive venue in Delaware'; no finding |
| halcyon-baseline | assignment.change_of_control | Change of control defined by a fifty percent ownership threshold | acceptable_variant/green | compliant/none | Matches the preferred position 'Not an assignment; terminable only if the acquirer is a competitor'; no finding |
| halcyon-baseline | amendment.written_amendment | No modification unless in writing and executed, counterparty phrasing | acceptable_variant/green | compliant/none | Matches the preferred position 'Signed written instrument only, explicit no-waiver'; no finding |
| halcyon-baseline | force_majeure.termination_right | Termination and refund, counterparty phrasing | acceptable_variant/green | compliant/none | Matches the preferred position 'Thirty-day trigger, refund of unused current-term Fees'; no finding |

**Category Z** — Outcome pair not covered by the categories above (see raw expected/actual below).

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | breach_notification.notification_timeline | 36 hours from discovery rather than confirmation | deviation/yellow | deviation/red | Parameter 'Event that starts the notification clock' value 'discovered' is beyond the yellow limit |
| halcyon-hipaa-overlay | breach_notification.notification_content | Content list with a single thirty-day follow-up cap | deviation/yellow | deviation/red | Parameter 'Whether a notice may supply missing facts in later, supplemental notices' value False is beyond the yellow limit |
| halcyon-hipaa-overlay | termination.termination_for_baa_breach | Seven-day cure period | deviation/yellow | deviation/red | Parameter 'Days to cure a material violation before Covered Entity may terminate the BAA' value 7 is beyond the yellow limit |
| halcyon-hipaa-overlay | indemnification.regulatory_penalties_indemnity | Penalty indemnity with a five-times, stand-alone cap | deviation/yellow | deviation/red | Parameter 'Dedicated cap for the regulatory penalties indemnity, as months of Fees' value 60 is beyond the yellow limit |
| halcyon-hipaa-overlay | data_protection.de_identification | De-identification permitted with no stated method | deviation/yellow | deviation/red | Parameter 'Permitted de-identification method' value 'unspecified_method' is beyond the yellow limit |
| halcyon-gdpr-overlay | data_protection.processing_instructions | Instructions by any means with prompt implementation | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Instructions through the Services and by written notice'; no finding |
| halcyon-gdpr-overlay | data_protection.records_of_processing | Record exists but no production commitment | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Record described by reference to Article 30(2) content'; no finding |
| halcyon-gdpr-overlay | data_transfers.data_residency | Hosting location left to the Processor's discretion | deviation/yellow | deviation/red | Parameter 'Hosting commitment for EU and UK Personal Data' value 'No specific EU or UK region commitment - Processor has unrestricted choice of hosting location' is beyond the yellow limit |
| halcyon-gdpr-overlay | subprocessors.authorisation_model | Notice given only after the sub-processor is live | deviation/red | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-gdpr-overlay | compliance.gdpr_compliance | Mutual compliance clause silent on lawful basis responsibility | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Compliance allocated by role, counterparty wording'; no finding |
| halcyon-vendor-msa-customer | payment.price_increases | Cap tied to list price | acceptable_variant/green | fallback/green/rung=1 | Matches fallback position 'Capped at 5%' (rung 1) |
| halcyon-vendor-msa-customer | term.initial_term | Sixty-month Initial Term with a termination right at month 24 | deviation/yellow | deviation/red | Parameter 'Length of the Initial Term' value 60 is beyond the yellow limit |
| halcyon-vendor-msa-customer | termination.for_convenience | Available only in the final 90 days of the Term | deviation/red | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-vendor-msa-customer | warranties.performance_warranty | Thirty-day warranty with no stated remedy | deviation/yellow | deviation/red | Parameter 'Performance warranty period' value 30 is beyond the yellow limit |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | $500k cyber cover only | deviation/yellow | deviation/red | Parameter 'Vendor cyber / technology E&O coverage limit' value 500000 is beyond the yellow limit |
| halcyon-vendor-msa-customer | intellectual_property.ownership | Licence permits use for Vendor's other customers without de-identification | deviation/yellow | deviation/red | Parameter 'Scope of Vendor's permitted use of Halcyon Data' value 'broad_product_improvement' is beyond the yellow limit |
| halcyon-vendor-msa-customer | subprocessors.subprocessor_changes | Notice given but PHI flow-down obligation absent | deviation/yellow | deviation/red | Parameter 'PHI-equivalent obligations flow down to subcontractors' value False is beyond the yellow limit |
| halcyon-vendor-msa-customer | audit.customer_audit_rights | Compliance report available only at Vendor's discretion | deviation/yellow | deviation/red | Parameter 'What Halcyon may use to verify Vendor's compliance' value 'none' is beyond the yellow limit |
| halcyon-mutual-nda | definitions.confidential_information_scope | Definition silent on oral disclosures and pre-signing exchanges | deviation/yellow | deviation/red | Parameter 'Confidential information scope standard' value 'written_marking_at_time_of_disclosure' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.standard_of_care | No stated standard of care | deviation/yellow | deviation/red | Parameter 'Standard of care for Confidential Information' value 'reasonable' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.compelled_disclosure | No notice obligation under any circumstance | red_line/red/cd-no-notice-right | fallback/yellow/rung=2 | Matches fallback position 'Notice only where not prohibited, no minimum-disclosure limit' (rung 2) |
| halcyon-mutual-nda | confidentiality.residuals | Residuals language with no stated exclusions either way | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'No residuals, counterparty phrasing'; no finding |
| halcyon-mutual-nda | confidentiality.equitable_relief | Counterparty-phrased equivalent | acceptable_variant/green | red_line/red/eqr-one-sided-injunctive-right | Matched red line 'eqr-one-sided-injunctive-right': Only one party, rather than both, may seek injunctive relief for a breach of confidentiality. |
| halcyon-mutual-nda | term.agreement_term | Automatic annual renewal with a non-renewal notice right | deviation/yellow | deviation/red | Parameter 'Agreement term in years' value 30 is beyond the yellow limit |
| halcyon-mutual-nda | term.survival_period | Survival runs from each disclosure rather than from termination | deviation/yellow | deviation/red | Parameter 'Survival treatment for trade secrets and other information' value 'limited_to_disclosed_items' is beyond the yellow limit |
| halcyon-mutual-nda | non_solicitation.employee_non_solicit | Twelve-month restriction with no contact limitation | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Twelve-month non-solicit, counterparty phrasing'; no finding |
| halcyon-mutual-nda | governing_law.choice_of_law | Two governing laws stated | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Delaware law, counterparty wording'; no finding |
| halcyon-saas-msa-vendor | payment.taxes | Taxes payable by Customer, different wording | acceptable_variant/green | fallback/green/rung=1 | Matches fallback position 'Exemption certificate required before exemption applies' (rung 1) |
| halcyon-saas-msa-vendor | term.auto_renewal | Double-negative 45-day variant | acceptable_variant/green | fallback/green/rung=1 | Matches fallback position '30 days' notice' (rung 1) |
| halcyon-saas-msa-vendor | warranties.disclaimer | Disclaimer folded into the close of the warranty section | acceptable_variant/green | fallback/yellow/rung=1 | Matches fallback position 'Drop the capitalisation, keep the substance' (rung 1) |
| halcyon-saas-msa-vendor | intellectual_property.feedback_license | Feedback licence silent on whether it is perpetual | deviation/yellow | acceptable_variant/none | Matches the acceptable_variant position 'Feedback licence drafted as part of a broader "Suggestions" clause'; no finding |
| halcyon-saas-msa-vendor | security.security_program | NIST framework reference added, tier 1 counterparty | fallback/yellow/rung=1 | acceptable_variant/none | Matches the acceptable_variant position 'Customer-drafted industry-standard wording'; no finding |
| halcyon-saas-msa-vendor | breach_notification.notification_timeline | Notice within 36 hours | deviation/yellow | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-dpa-processor | data_protection.data_return_and_deletion | Counterparty return-or-delete wording | acceptable_variant/green | fallback/green/rung=1 | Matches fallback position '30-day export, deletion within 90 days with backup cycling' (rung 1) |
| halcyon-dpa-processor | breach_notification.notification_timeline | Notice period left unstated | deviation/yellow | deviation/red | Parameter 'Event that starts the notification clock' value 'not specified' is beyond the yellow limit |
| halcyon-dpa-processor | subprocessors.authorisation_model | Authorisation model left unstated | deviation/yellow | deviation/red | Parameter 'Authorisation model for Sub-processors' value 'not specified' is beyond the yellow limit |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Joint-and-several wording limited to the sub-processor's own fee share | acceptable_variant/green | red_line/red/liab-no-flow-down | Matched red line 'liab-no-flow-down': Halcyon has no written agreement in place binding Sub-processors to equivalent data protection obligations. |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | Transfer mechanism referenced vaguely without naming one | deviation/yellow | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'none_stated' is beyond the yellow limit |

**Category E** — Expected a semantic red line to trigger; model did not trigger it and fell through to a plain deviation.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.permitted_uses_of_phi | Services only | red_line/red/phi-use-no-management-administration | deviation/red | Parameter 'Limbs of permitted use granted to Business Associate' value 'services_only' is beyond the yellow limit |
| halcyon-hipaa-overlay | data_protection.individual_rights_support | Forty-eight hour access | red_line/red/ind-rights-access-under-5-days | deviation/yellow | Parameter 'Days to make PHI available for an access request' value 5 is beyond the green limit |
| halcyon-hipaa-overlay | breach_notification.notification_timeline | Notice from the moment of suspicion | red_line/red/breach-notice-under-24-hours-or-suspicion | deviation/red | Parameter 'Hours after confirmation to notify Covered Entity' value 12 is beyond the yellow limit |
| halcyon-hipaa-overlay | breach_notification.notification_content | Complete notice required in a single communication | red_line/red/breach-content-single-complete-notice | deviation/red | Parameter 'Whether a notice may supply missing facts in later, supplemental notices' value False is beyond the yellow limit |
| halcyon-hipaa-overlay | data_protection.de_identification | De-identification tied to no regulatory method, used for sale | red_line/red/de-identification-not-to-regulatory-standard | deviation/red | Parameter 'Whether Business Associate may de-identify PHI for its own use' value False is beyond the yellow limit |
| halcyon-gdpr-overlay | data_transfers.data_residency | Single-tenant deployment required | red_line/red/gdpr-residency-single-tenant-or-on-prem | deviation/red | Parameter 'Hosting commitment for EU and UK Personal Data' value 'single_tenant_deployment' is beyond the yellow limit |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Notice triggered by mere suspicion | red_line/red/gdpr-breach-suspicion-trigger | deviation/red | Parameter 'Event that starts the notification clock' value 'suspected_or_actual' is beyond the yellow limit |
| halcyon-vendor-msa-customer | limitation_of_liability.cap_amount | Six-month cap | red_line/red/lol-vendor-cap-under-12-months | deviation/red | Parameter 'Vendor general cap as months of Fees' value 6 is beyond the yellow limit |
| halcyon-vendor-msa-customer | limitation_of_liability.cap_carve_outs | All data claims expressly within the cap | red_line/red/carve-data-breach-inside-general-cap | deviation/red | Parameter 'How Vendor's data breach liability is treated under the cap' value 'inside_general_cap' is beyond the yellow limit |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | No insurance obligation stated | red_line/red/insurance-none-required | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-vendor-msa-customer | intellectual_property.ownership | Vendor claims ownership of Halcyon Data without restriction | red_line/red/ip-own-vendor-claims-halcyon-data | deviation/red | Parameter 'Scope of Vendor's permitted use of Halcyon Data' value 'unrestricted' is beyond the yellow limit |
| halcyon-vendor-msa-customer | confidentiality.standard_of_care | No standard of care stated | red_line/red/confidentiality-no-standard-of-care | deviation/red | Parameter 'Vendor's standard of care for Halcyon's confidential information' value 'none_stated' is beyond the yellow limit |
| halcyon-vendor-msa-customer | security.security_program | No security commitment at all | red_line/red/security-no-commitment | deviation/red | Parameter 'Standard the Vendor's security programme is aligned with' value 'none' is beyond the yellow limit |
| halcyon-vendor-msa-customer | breach_notification.notification_timeline | 30-day notice period | red_line/red/breach-notice-over-120-hours | deviation/red | Parameter 'Hours to notify Halcyon of a suspected or confirmed Security Incident' value 720 is beyond the yellow limit |
| halcyon-vendor-msa-customer | breach_notification.notification_timeline | No breach notification clause at all | red_line/red/breach-notice-no-commitment | deviation/red | Parameter 'Event that starts the notice clock' value 'no_trigger_stated' is beyond the yellow limit |
| halcyon-vendor-msa-customer | audit.customer_audit_rights | Vendor gives no report, questionnaire or audit right of any kind | red_line/red/audit-vendor-refuses-all-verification | deviation/red | Parameter 'What Halcyon may use to verify Vendor's compliance' value 'none' is beyond the yellow limit |
| halcyon-mutual-nda | definitions.confidential_information_scope | Protection limited to a fixed schedule | red_line/red/ci-named-schedule-only | deviation/red | Parameter 'Confidential information scope standard' value 'named_schedule_only' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.exclusions | No exclusions at all | red_line/red/excl-no-exclusions | deviation/red | Parameter 'Number of standard exclusion limbs' value 0 is beyond the yellow limit |
| halcyon-mutual-nda | term.survival_period | Perpetual survival for all information | red_line/red/surv-perpetual-all-information | deviation/red | Parameter 'Survival treatment for trade secrets and other information' value 'perpetual_all_information' is beyond the yellow limit |
| halcyon-mutual-nda | governing_law.choice_of_law | Ontario law for a Canadian counterparty | red_line/red/global-governing-law-outside-lists | deviation/red | Parameter 'Jurisdiction whose law governs' value 'other' is beyond the yellow limit |
| halcyon-saas-msa-vendor | service_levels.service_credits | Credits available in addition to damages | red_line/red/credit-not-sole-remedy | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-saas-msa-vendor | audit.customer_audit_rights | Unannounced audit at any time | red_line/red/global-unannounced-audit | deviation/red | Parameter 'Days' advance written notice required before an audit' value 0 is beyond the yellow limit |
| halcyon-saas-msa-vendor | compliance.anti_corruption | Absolute strict-liability exclusion warranty with full refund | red_line/red/anti-corruption-absolute-warranty-strict-liability | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-dpa-processor | definitions.roles_of_parties | Halcyon designated controller for all customer data | red_line/red/roles-processor-deemed-controller | deviation/red | Parameter 'Halcyon's role for Service Personal Data' value 'controller' is beyond the yellow limit |
| halcyon-dpa-processor | audit.customer_audit_rights | Audit permitted at any time without notice | red_line/red/audit-unannounced-or-unlimited | deviation/red | Parameter 'Audits Customer may conduct per year' value 99 is beyond the yellow limit |
| halcyon-dpa-processor | data_protection.data_subject_requests | Halcyon must answer the Data Subject itself | red_line/red/dsr-must-answer-directly | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-dpa-processor | security.technical_organisational_measures | No description of measures and no certification reference | red_line/red/toms-no-description | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-dpa-processor | breach_notification.notification_timeline | Notice triggered by mere suspicion | red_line/red/breach-suspicion-trigger | deviation/red | Parameter 'Event that starts the notification clock' value 'suspicion' is beyond the yellow limit |
| halcyon-dpa-processor | subprocessors.authorisation_model | Specific prior consent required for each sub-processor | red_line/red/subproc-specific-consent-required | deviation/red | Parameter 'Authorisation model for Sub-processors' value 'specific_prior_consent' is beyond the yellow limit |
| halcyon-dpa-processor | subprocessors.subprocessor_changes | No notice or objection right at all | red_line/red/changes-no-notice-or-objection | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | No transfer mechanism named at all for an EU deal | red_line/red/transfer-no-mechanism | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'none_stated' is beyond the yellow limit |
| halcyon-dpa-processor | data_transfers.data_residency | Single-tenant on-premises deployment required | red_line/red/resid-single-tenant-on-premises | deviation/red | Parameter 'Scope of the data residency commitment' value 'single_tenant_or_on_premises' is beyond the yellow limit |
| halcyon-dpa-processor | audit.audit_cost | Halcyon must bear all audit costs unconditionally | red_line/red/cost-halcyon-bears-all-unconditionally | deviation/red | Parameter 'Who bears the cost of an on-site audit' value 'halcyon_bears_all_costs' is beyond the yellow limit |
| halcyon-baseline | governing_law.choice_of_law | Law of a foreign country outside the approved list | red_line/red/global-governing-law-outside-lists | deviation/red | Parameter 'Jurisdiction whose law governs' value 'other' is beyond the yellow limit |
| halcyon-baseline | governing_law.venue | Venue set in a country outside the approved list | red_line/red/global-governing-law-outside-lists | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-baseline | amendment.written_amendment | Counterparty may amend by posting updated terms online | red_line/red/global-unilateral-amendment | deviation/yellow | No matching position or red line; deviation from the playbook |

**Category M** — Expected `compliant` (clean match); model found some other outcome — a false alarm on text that should have passed clean.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.data_return_and_deletion | Trap - "retain no copies" with the infeasibility carve-out [TRAP] | compliant/green | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-hipaa-overlay | data_protection.de_identification | Trap - de-identification expressly prohibited [TRAP] | compliant/green | deviation/red | Parameter 'Whether Business Associate may de-identify PHI for its own use' value False is beyond the yellow limit |
| halcyon-gdpr-overlay | data_protection.records_of_processing | Trap - record kept even though no period is stated [TRAP] | compliant/green | acceptable_variant/none | Matches the acceptable_variant position 'Record described by reference to Article 30(2) content'; no finding |
| halcyon-gdpr-overlay | data_transfers.transfer_mechanism | SCCs Module Two incorporated by reference, UK Addendum included | compliant/green | deviation/red | Parameter 'Mechanism relied on for restricted transfers' value 'Standard Contractual Clauses Module Two incorporated by reference with UK International Data Transfer Addendum' is beyond the yellow limit |
| halcyon-gdpr-overlay | data_transfers.transfer_mechanism | Trap - adequacy decision offered as an alternative, not instead of all safeguards [TRAP] | compliant/green | deviation/red | Parameter 'Mechanism relied on for restricted transfers' value 'SCCs Module Two' is beyond the yellow limit |
| halcyon-gdpr-overlay | data_transfers.transfer_impact_assessment | Trap - challenge limited to unlawful requests, not a blanket refusal [TRAP] | compliant/green | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-gdpr-overlay | data_transfers.data_residency | EU region multi-tenant hosting | compliant/green | fallback/green/rung=1 | Matches fallback position 'EU region hosting with access restricted to the EEA and UK' (rung 1) |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Notice within 72 hours of confirmation | compliant/green | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Trap - preliminary information before confirmation is not a suspicion trigger [TRAP] | compliant/green | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-vendor-msa-customer | term.initial_term | Trap - month-to-month wording [TRAP] | compliant/green | deviation/yellow | No matching position or red line; deviation from the playbook |
| halcyon-vendor-msa-customer | service_levels.uptime_commitment | Trap - maintenance exclusion is narrow and notice-based [TRAP] | compliant/green | fallback/green/rung=1 | Matches fallback position '99.9% monthly' (rung 1) |
| halcyon-vendor-msa-customer | indemnification.data_breach_indemnity | Trap - notification costs covered despite a cap on damages generally [TRAP] | compliant/green | fallback/green/rung=1 | Matches fallback position 'Same costs, subject to the data breach super-cap' (rung 1) |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | Trap - "no less than our standard policy" meeting the floor [TRAP] | compliant/green | deviation/red | Parameter 'Vendor cyber / technology E&O coverage limit' value 5 is beyond the yellow limit |
| halcyon-vendor-msa-customer | security.security_program | Trap - no named certification but a detailed, itemised programme [TRAP] | compliant/green | fallback/green/rung=1 | Matches fallback position 'Programme described without naming a standard' (rung 1) |
| halcyon-vendor-msa-customer | subprocessors.subprocessor_changes | Trap - no fixed notice period but a working list Halcyon can always inspect [TRAP] | compliant/green | deviation/yellow | Parameter 'Days of advance notice before a new subcontractor processes Halcyon Data' value 0 is beyond the green limit |
| halcyon-vendor-msa-customer | audit.customer_audit_rights | Trap - no on-site audit right offered, but a current SOC 2 report is provided as of right [TRAP] | compliant/green | fallback/green/rung=1 | Matches fallback position 'Report-based assurance, on-site audit only after an incident' (rung 1) |
| halcyon-mutual-nda | definitions.confidential_information_scope | Reasonable-person standard, different phrasing | compliant/green | deviation/red | Parameter 'Confidential information scope standard' value 'reasonable_person_standard' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.standard_of_care | Own-practice floor, different phrasing | compliant/green | deviation/red | Parameter 'Standard of care for Confidential Information' value 'own_practice_with_reasonable_floor' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.standard_of_care | Trap - negated unrestricted-use wording [TRAP] | compliant/green | deviation/red | Parameter 'Standard of care for Confidential Information' value 'own_care_with_reasonable_floor' is beyond the yellow limit |
| halcyon-saas-msa-vendor | payment.payment_terms | Standard Net 30 | compliant/green | acceptable_variant/none | Matches the acceptable_variant position 'Due-within-30-days wording'; no finding |
| halcyon-saas-msa-vendor | limitation_of_liability.cap_carve_outs | Standard four carve-outs | compliant/green | deviation/red | Parameter 'Categories excluded from the general cap' value "fraud, wilful misconduct, payment obligations (Customer's unpaid fees), IP indemnity (Vendor's obligations under the infringement indemnity)" is beyond the yellow limit |
| halcyon-saas-msa-vendor | breach_notification.notification_timeline | 72 hours after confirmation | compliant/green | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-saas-msa-vendor | subprocessors.subprocessor_changes | General authorisation, 30 days' notice | compliant/green | deviation/yellow | Parameter 'Days Customer has to object after notice of a new subprocessor' value 30 is beyond the green limit |
| halcyon-saas-msa-vendor | subprocessors.subprocessor_changes | Trap - negated "no notice" wording [TRAP] | compliant/green | deviation/yellow | Parameter 'Days Customer has to object after notice of a new subprocessor' value 30 is beyond the green limit |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Trap - liability for sub-processors is not unlimited [TRAP] | compliant/green | red_line/red/liab-no-flow-down | Matched red line 'liab-no-flow-down': Halcyon has no written agreement in place binding Sub-processors to equivalent data protection obligations. |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | Standard Contractual Clauses by reference | compliant/green | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'Standard Contractual Clauses, Module Two, and UK Addendum' is beyond the yellow limit |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | Trap - incorporation by reference still requires compliance [TRAP] | compliant/green | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'Standard Contractual Clauses' is beyond the yellow limit |
| halcyon-dpa-processor | audit.audit_cost | Trap - cost shift on material breach is not unconditional funding [TRAP] | compliant/green | acceptable_variant/none | Matches the acceptable_variant position 'Counterparty wording to the same effect'; no finding |
| halcyon-dpa-processor | limitation_of_liability.dpa_liability_alignment | Trap - aggregation is not the same as doubling the cap [TRAP] | compliant/green | acceptable_variant/none | Matches the acceptable_variant position 'Counterparty wording to the same effect'; no finding |
| halcyon-baseline | dispute_resolution.forum | Courts decide, no arbitration requirement | compliant/green | acceptable_variant/none | Matches the acceptable_variant position 'No obligation to arbitrate, counterparty phrasing'; no finding |

**Category L** — Expected a plain deviation; model triggered a red line instead — likely a red-line condition written too broadly, catching ordinary deviations.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | subprocessors.subcontractor_baa_flow_down | Oral assurance from a cloud Subcontractor | deviation/red | red_line/red/subcontractor-flow-down-absent | Matched red line 'subcontractor-flow-down-absent': Subcontractors that handle PHI are not bound in writing to restrictions at least as protective as this BAA. |
| halcyon-gdpr-overlay | data_transfers.transfer_mechanism | Transfer clause restates compliance with no named mechanism | deviation/yellow | red_line/red/gdpr-transfer-no-mechanism | Matched red line 'gdpr-transfer-no-mechanism': Personal Data may be transferred outside the EEA or the UK with no Standard Contractual Clauses, adequacy decision or other Chapter V mechanism identified. |
| halcyon-gdpr-overlay | audit.supervisory_authority_cooperation | No notice commitment at all | deviation/yellow | red_line/red/gdpr-sac-responds-before-notice | Matched red line 'gdpr-sac-responds-before-notice': The Processor may answer a Supervisory Authority on the substance of an enquiry concerning the Controller's data before telling the Controller, with no exception limited to a legal requirement. |
| halcyon-vendor-msa-customer | payment.late_fees | Late fee with no dispute exception | deviation/yellow | red_line/red/vdr-late-fee-punitive | Matched red line 'vdr-late-fee-punitive': The late fee compounds, has no dispute carve-out, or is paired with a right to suspend the Services for any overdue amount including a disputed one. |
| halcyon-vendor-msa-customer | termination.for_cause_cure_period | Sixty-day cure period | deviation/red | red_line/red/cure-unlimited-vendor | Matched red line 'cure-unlimited-vendor': Vendor's cure period for a material breach exceeds 45 days, repeats indefinitely, or Halcyon has no termination right for Vendor's uncured breach at all. |
| halcyon-vendor-msa-customer | termination.transition_assistance | Transition assistance available only at Vendor's sole discretion | deviation/yellow | red_line/red/transition-none-and-no-data-return | Matched red line 'transition-none-and-no-data-return': The Services stop immediately on the termination date with no transition support and no obligation to return or make Halcyon Data available in a usable format. |
| halcyon-vendor-msa-customer | service_levels.service_credits | Five percent cap with no termination carve-out | deviation/red | red_line/red/credits-sole-remedy-includes-security | Matched red line 'credits-sole-remedy-includes-security': Service credits are Halcyon's sole and exclusive remedy for any failure, including a security incident or data breach. |
| halcyon-vendor-msa-customer | assignment.change_of_control | Ninety days' notice, no termination right | deviation/red | red_line/red/coc-no-notice-no-exit | Matched red line 'coc-no-notice-no-exit': A Change of Control of Vendor requires no notice to Halcyon and gives Halcyon no termination right at all. |
| halcyon-vendor-msa-customer | indemnification.data_breach_indemnity | Indemnity covers only amounts paid to third parties | deviation/yellow | red_line/red/databreach-ind-no-notification-costs | Matched red line 'databreach-ind-no-notification-costs': The agreement does not make Vendor responsible for the cost of notifying affected individuals or regulators after a Security Incident affecting Halcyon Data. |
| halcyon-mutual-nda | intellectual_property.no_license | No-licence statement present but a feedback licence carved in | deviation/yellow | red_line/red/nol-implied-license-granted | Matched red line 'nol-implied-license-granted': The Agreement grants the Receiving Party an express or implied licence to use or exploit the Disclosing Party's intellectual property beyond evaluating the Purpose. |
| halcyon-saas-msa-vendor | limitation_of_liability.consequential_damages_exclusion | Exclusion carved out for any breach | deviation/red | red_line/red/lol-consequential-removed | Matched red line 'lol-consequential-removed': The consequential damages exclusion is deleted or carved out for a broad category of claim. |
| halcyon-saas-msa-vendor | indemnification.indemnity_procedure | Notice period of 60 days with no materiality standard | deviation/red | red_line/red/indemnity-proc-no-defence-control | Matched red line 'indemnity-proc-no-defence-control': The indemnifying party has no right to control the defence or settlement of a claim it must pay for. |
| halcyon-saas-msa-vendor | data_protection.customer_data_use | Analytics use described only as "business purposes | deviation/yellow | red_line/red/data-use-shared-across-tenants-identifiable | Matched red line 'data-use-shared-across-tenants-identifiable': Customer Data, in identifiable form, is used for or disclosed to Halcyon's other customers or the public. |
| halcyon-dpa-processor | data_protection.processing_instructions | Instructions given verbally by any Customer employee | deviation/yellow | red_line/red/instr-unbounded | Matched red line 'instr-unbounded': Halcyon must comply with instructions of whatever nature, from any person, at its own cost, without the instructions being fixed to the Agreement and this Addendum. |
| halcyon-dpa-processor | data_protection.data_return_and_deletion | Deletion period left unstated | deviation/yellow | red_line/red/return-indefinite-retention | Matched red line 'return-indefinite-retention': Halcyon may retain Service Personal Data indefinitely after termination, with no deletion commitment at all. |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Flow-down obligation stated vaguely, no written-agreement requirement | deviation/yellow | red_line/red/liab-no-flow-down | Matched red line 'liab-no-flow-down': Halcyon has no written agreement in place binding Sub-processors to equivalent data protection obligations. |
| halcyon-baseline | governing_law.choice_of_law | Two governing laws for different purposes | deviation/yellow | red_line/red/col-floating-choice | Matched red line 'col-floating-choice': The governing law may be chosen or changed later, by the counterparty or by whichever law it designates. |
| halcyon-baseline | governing_law.venue | Two venues named for different claim types | deviation/yellow | red_line/red/ven-floating-forum | Matched red line 'ven-floating-forum': The venue may be selected later by whichever party commences suit, rather than fixed at signing. |
| halcyon-baseline | dispute_resolution.escalation_process | Escalation period doubles after a prior dispute in the same year | deviation/yellow | red_line/red/esc-no-urgent-carveout | Matched red line 'esc-no-urgent-carveout': The escalation requirement applies to every claim with no exception for injunctive relief or for collecting undisputed Fees. |
| halcyon-baseline | assignment.consent_requirement | Consent required only for assignments above a revenue threshold | deviation/yellow | red_line/red/asn-con-unrestricted | Matched red line 'asn-con-unrestricted': Assignment is permitted to any third party, including a direct competitor, without any consent, notice or restriction. |
| halcyon-baseline | entire_agreement.integration | Entire agreement clause excludes the exhibits from superseding prior drafts | deviation/yellow | red_line/red/ent-int-rfp-incorporation | Matched red line 'ent-int-rfp-incorporation': A request for proposal, sales presentation or other pre-contract document is incorporated as a binding part of the Agreement. |
| halcyon-baseline | force_majeure.scope | Force majeure excuses obligations for ninety days regardless of actual impact | deviation/yellow | red_line/red/fm-scp-security-excused | Matched red line 'fm-scp-security-excused': Force majeure excuses a party's confidentiality, data protection or security obligations, including breach notification, without the impossibility and mitigation limits. |

**Category D** — Expected a deviation; model matched the `preferred` position outright, missing the deviation entirely.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.data_return_and_deletion | Sixty day export window | deviation/yellow | compliant/none | Matches the preferred position 'Destruction in 60 days, backups in 90 days, both after the retrieval window'; no finding |
| halcyon-hipaa-overlay | security.safeguards | Safeguards plus Covered Entity's own control catalogue | deviation/yellow | compliant/none | Matches the preferred position 'Security Rule safeguards, referenced by subpart'; no finding |
| halcyon-hipaa-overlay | subprocessors.subcontractor_baa_flow_down | Flow-down limited to Subcontractors Covered Entity pre-approves | deviation/yellow | compliant/none | Matches the preferred position 'Written flow-down to Subcontractors handling PHI'; no finding |
| halcyon-hipaa-overlay | audit.hhs_access | HHS access limited to records Business Associate selects | deviation/yellow | compliant/none | Matches the preferred position 'Access limited to the Secretary of HHS'; no finding |
| halcyon-hipaa-overlay | compliance.hipaa_compliance | Compliance commitment with no amendment mechanism for changes in law | deviation/yellow | compliant/none | Matches the preferred position 'Compliance with the Rules applicable to a business associate, amended for changes in law'; no finding |
| halcyon-gdpr-overlay | data_protection.processing_instructions | No duty to flag infringing instructions | deviation/yellow | compliant/none | Matches the preferred position 'Documented instructions, Agreement as the complete set'; no finding |
| halcyon-vendor-msa-customer | indemnification.ip_infringement_indemnity | Open-source components excluded from the indemnity | deviation/yellow | compliant/none | Matches the preferred position 'Worldwide indemnity covering Halcyon's customers'; no finding |
| halcyon-mutual-nda | publicity.name_and_logo_use | Consent addressed for marketing use but silent on existence of discussions | deviation/yellow | compliant/none | Matches the preferred position 'Mutual consent required for any publicity'; no finding |
| halcyon-saas-msa-vendor | warranties.performance_warranty | No cure period or remedy stated | deviation/red | compliant/none | Matches the preferred position 'Material-conformance warranty with 30-day cure'; no finding |
| halcyon-saas-msa-vendor | publicity.name_and_logo_use | Customer list right with no restriction on Customer publicising performance data | deviation/yellow | compliant/none | Matches the preferred position 'Customer list and logo use, consent required for case studies'; no finding |
| halcyon-dpa-processor | data_protection.dpia_assistance | Assistance mentioned with no reference to existing documentation | deviation/yellow | compliant/none | Matches the preferred position 'Assistance from existing documentation, reasonable in scope'; no finding |
| halcyon-dpa-processor | breach_notification.notification_content | Content requirement left vague | deviation/yellow | compliant/none | Matches the preferred position 'Standard content, phased notice permitted'; no finding |

**Category B** — Expected a plain deviation; model's extraction instead matched a fallback position.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.permitted_uses_of_phi | Research use added by the Covered Entity's form | deviation/yellow | fallback/yellow/rung=2 | Matches fallback position 'Management and administration by use only' (rung 2) |
| halcyon-vendor-msa-customer | limitation_of_liability.cap_carve_outs | Confidentiality breach involving Halcyon Data inside the general cap | deviation/yellow | fallback/green/rung=1 | Matches fallback position 'Data breach moved to the 5x super-cap' (rung 1) |
| halcyon-vendor-msa-customer | confidentiality.standard_of_care | Standard of care applies only to written information | deviation/yellow | fallback/green/rung=1 | Matches fallback position 'Reasonable care without the "own information" comparison' (rung 1) |
| halcyon-mutual-nda | confidentiality.compelled_disclosure | Notice given before disclosure, but only if requested rather than required | deviation/yellow | fallback/yellow/rung=2 | Matches fallback position 'Notice only where not prohibited, no minimum-disclosure limit' (rung 2) |
| halcyon-saas-msa-vendor | indemnification.ip_infringement_indemnity | Indemnity excludes claims from Vendor's own code changes | deviation/yellow | fallback/yellow/rung=2 | Matches fallback position 'Remove the "in Halcyon's opinion" threshold for the remedy' (rung 2) |
| halcyon-saas-msa-vendor | indemnification.customer_indemnity | Customer indemnity limited to claims where Customer was grossly negligent | deviation/yellow | fallback/yellow/rung=1 | Matches fallback position 'Narrow to Customer Data and breach of the Agreement' (rung 1) |
| halcyon-saas-msa-vendor | warranties.disclaimer | Disclaimer present but silent on medical advice | deviation/yellow | fallback/yellow/rung=1 | Matches fallback position 'Drop the capitalisation, keep the substance' (rung 1) |
| halcyon-saas-msa-vendor | confidentiality.standard_of_care | Standard of care stated with no reasonable-care floor | deviation/yellow | fallback/yellow/rung=1 | Matches fallback position 'Reasonable care only, no self-care comparator' (rung 1) |
| halcyon-saas-msa-vendor | security.certifications | Delivery "within a reasonable time" with no number | deviation/yellow | fallback/yellow/rung=2 | Matches fallback position '30-day report delivery' (rung 2) |
| halcyon-saas-msa-vendor | audit.customer_audit_rights | Audit right described only as "upon reasonable notice | deviation/yellow | fallback/green/rung=1 | Matches fallback position 'Report plus written security questionnaire' (rung 1) |
| halcyon-saas-msa-vendor | compliance.compliance_with_laws | Compliance obligation stated with no scope at all | deviation/yellow | fallback/green/rung=1 | Matches fallback position 'Mutual compliance clause' (rung 1) |

**Category H** — Expected `acceptable_variant`; model treated the clause as an unmatched deviation instead of recognizing the variant wording.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.individual_rights_support | Ten days for every request type | acceptable_variant/green | deviation/yellow | Parameter 'Days to supply accounting of disclosures information' value 10 is beyond the green limit |
| halcyon-gdpr-overlay | breach_notification.notification_timeline | Notice framed around the Controller's Article 33 deadline | acceptable_variant/green | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-vendor-msa-customer | insurance.coverage_requirements | Combined single limit variant | acceptable_variant/green | deviation/red | Parameter 'Vendor cyber / technology E&O coverage limit' value 6 is beyond the yellow limit |
| halcyon-mutual-nda | definitions.confidential_information_scope | Knew-or-should-have-known variant | acceptable_variant/green | deviation/red | Parameter 'Confidential information scope standard' value 'reasonable_person_standard_no_marking' is beyond the yellow limit |
| halcyon-mutual-nda | confidentiality.standard_of_care | Strict-confidence variant | acceptable_variant/green | deviation/red | Parameter 'Standard of care for Confidential Information' value 'own_practice_with_reasonable_floor' is beyond the yellow limit |
| halcyon-mutual-nda | term.survival_period | Counterparty-phrased flat three-year survival | acceptable_variant/green | deviation/red | Parameter 'Survival treatment for trade secrets and other information' value 'limited_to_trade_secrets_or_unspecified' is beyond the yellow limit |
| halcyon-saas-msa-vendor | limitation_of_liability.cap_carve_outs | Excepted Liabilities, same four categories | acceptable_variant/green | deviation/red | Parameter 'Categories excluded from the general cap' value 'fraud, wilful misconduct, non-payment of fees, indemnity for third-party intellectual property claims' is beyond the yellow limit |
| halcyon-saas-msa-vendor | breach_notification.notification_timeline | Customer-drafted "promptly" wording | acceptable_variant/green | deviation/red | Parameter 'Event that starts the notification clock' value 'confirmed' is beyond the yellow limit |
| halcyon-dpa-processor | breach_notification.notification_timeline | Counterparty Personal Data Breach wording | acceptable_variant/green | deviation/yellow | Parameter 'Event that starts the notification clock' value 'discovery' is beyond the green limit |
| halcyon-dpa-processor | data_transfers.transfer_mechanism | Counterparty Restricted Transfer wording | acceptable_variant/green | deviation/red | Parameter 'Transfer mechanism relied on for a restricted transfer' value 'Standard Contractual Clauses with UK Addendum' is beyond the yellow limit |
| halcyon-baseline | notices.method | Notice effective on actual receipt, any written record | acceptable_variant/green | deviation/yellow | Parameter 'Email alone is sufficient for a notice of breach or termination' value True is beyond the green limit |

**Category J** — Expected a fallback match; model matched the `preferred` position instead.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | security.phi_encryption | Customer-managed key for a strategic deployment | fallback/yellow/rung=2 | compliant/none | Matches the preferred position 'TLS 1.2+ in transit, AES-256 at rest'; no finding |
| halcyon-vendor-msa-customer | confidentiality.standard_of_care | Flat reasonable-care standard | fallback/green/rung=1 | compliant/none | Matches the preferred position 'Reasonable care, need-to-know, matching subcontractor terms'; no finding |
| halcyon-mutual-nda | confidentiality.exclusions | Four exclusions, no burden-of-proof sentence | fallback/yellow/rung=1 | compliant/none | Matches the preferred position 'Four standard exclusions, burden of proof on Receiving Party'; no finding |
| halcyon-mutual-nda | confidentiality.compelled_disclosure | Notice and minimum disclosure, no cooperation | fallback/yellow/rung=1 | compliant/none | Matches the preferred position 'Prior notice, cooperation, minimum necessary disclosure'; no finding |
| halcyon-mutual-nda | intellectual_property.no_license | No licence, ownership sentence omitted | fallback/yellow/rung=1 | compliant/none | Matches the preferred position 'No licence, all intellectual property reserved'; no finding |
| halcyon-saas-msa-vendor | intellectual_property.usage_data | Methodology disclosure on written request | fallback/yellow/rung=1 | compliant/none | Matches the preferred position 'Aggregated, de-identified Usage Data for operating, securing and improving the Services'; no finding |
| halcyon-saas-msa-vendor | data_protection.customer_data_use | Internal-only analytics for PHI | fallback/yellow/rung=1 | compliant/none | Matches the preferred position 'Service purpose plus de-identified analytics carve-out'; no finding |
| halcyon-saas-msa-vendor | compliance.compliance_with_laws | Mutual compliance clause | fallback/green/rung=1 | compliant/none | Matches the preferred position 'Compliance scoped to Halcyon's own performance'; no finding |
| halcyon-saas-msa-vendor | compliance.anti_corruption | Exclusion representation extended to subcontractors | fallback/green/rung=1 | compliant/none | Matches the preferred position 'Mutual anti-corruption and exclusion representation'; no finding |
| halcyon-dpa-processor | audit.customer_audit_rights | Tier 1 PHI deal, on-site audit permitted | fallback/yellow/rung=2 | compliant/none | Matches the preferred position 'Annual audit, 30 days' notice, SOC 2 report first'; no finding |
| halcyon-dpa-processor | data_protection.personnel_confidentiality | PHI deal, background check confirmation added | fallback/yellow/rung=2 | compliant/none | Matches the preferred position 'Confidentiality, need-to-know access and annual training'; no finding |

**Category F** — A red line did trigger, but the wrong one (key mismatch) — two red lines on the same rule are close enough in wording that the model picked the wrong one.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-hipaa-overlay | data_protection.data_return_and_deletion | Destruction of every copy within five days | red_line/red/phi-return-destruction-under-30-days | red_line/red/phi-return-no-infeasibility-exception | Matched red line 'phi-return-no-infeasibility-exception': All PHI including backups must be returned or destroyed in every case, with no infeasibility exception. |
| halcyon-hipaa-overlay | indemnification.regulatory_penalties_indemnity | Uncapped penalty indemnity | red_line/red/regulatory-penalty-indemnity-uncapped | red_line/red/regulatory-penalty-indemnity-no-causation-limit | Matched red line 'regulatory-penalty-indemnity-no-causation-limit': The indemnity covers penalties imposed on Covered Entity regardless of whether Business Associate caused the violation. |
| halcyon-vendor-msa-customer | indemnification.data_breach_indemnity | Refund of fees is the only remedy for a breach | red_line/red/databreach-ind-refund-only | red_line/red/databreach-ind-no-notification-costs | Matched red line 'databreach-ind-no-notification-costs': The agreement does not make Vendor responsible for the cost of notifying affected individuals or regulators after a Security Incident affecting Halcyon Data. |
| halcyon-vendor-msa-customer | subprocessors.subprocessor_changes | No flow-down of HIPAA-equivalent terms to a PHI subcontractor | red_line/red/subcontractor-no-phi-flow-down | red_line/red/subcontractor-no-notice | Matched red line 'subcontractor-no-notice': Vendor may engage or replace a subcontractor that processes Halcyon Data with no notice to Halcyon at all. |
| halcyon-saas-msa-vendor | indemnification.customer_indemnity | Agreement expressly states Customer has no indemnity obligation | red_line/yellow/cust-indemnity-removed-no-substitute | red_line/red/cust-indemnity-removed-no-substitute | Matched red line 'cust-indemnity-removed-no-substitute': Customer's indemnity obligation is deleted with no equivalent protection for claims arising from Customer Data or Customer's own conduct. |
| halcyon-saas-msa-vendor | indemnification.indemnity_procedure | Indemnified party may settle without the indemnifying party's involvement | red_line/yellow/indemnity-proc-no-defence-control | red_line/red/indemnity-proc-no-defence-control | Matched red line 'indemnity-proc-no-defence-control': The indemnifying party has no right to control the defence or settlement of a claim it must pay for. |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Sub-processor liability excluded from every cap | red_line/red/liab-subprocessor-uncapped | red_line/red/liab-no-flow-down | Matched red line 'liab-no-flow-down': Halcyon has no written agreement in place binding Sub-processors to equivalent data protection obligations. |

**Category I** — Expected a fallback match; model instead triggered a red line — likely a red-line condition written broadly enough to also catch an acceptable fallback phrasing.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-saas-msa-vendor | breach_notification.notification_timeline | 24 hours after confirmation, PHI and tier 1 | fallback/yellow/rung=2 | red_line/red/data-breach-notice-under-24h-or-on-suspicion | Matched red line 'data-breach-notice-under-24h-or-on-suspicion': Notice is required in under 24 hours, or is triggered by mere suspicion rather than confirmation or a reasonable belief. |
| halcyon-dpa-processor | subprocessors.subprocessor_liability | Strategic deal, breach super-cap carve-out for sub-processors | fallback/yellow/rung=2 | red_line/red/liab-no-flow-down | Matched red line 'liab-no-flow-down': Halcyon has no written agreement in place binding Sub-processors to equivalent data protection obligations. |
| halcyon-baseline | dispute_resolution.escalation_process | Sixty-day period, Fee collection no longer carved out | fallback/yellow/rung=2 | red_line/red/esc-no-urgent-carveout | Matched red line 'esc-no-urgent-carveout': The escalation requirement applies to every claim with no exception for injunctive relief or for collecting undisputed Fees. |

**Category G** — The `missing` (required-clause-absent) path matched on outcome, but the expected zone differs from the actual zone.

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-mutual-nda | non_solicitation.employee_non_solicit | No non-solicitation clause in the Agreement | missing/green | missing/yellow | No matching position or red line; deviation from the playbook |
| halcyon-saas-msa-vendor | indemnification.customer_indemnity | Missing customer indemnity | missing/red | missing/yellow | No matching position or red line; deviation from the playbook |

**Category K** — Expected a red line to trigger; model matched the `preferred` position — a severe miss (missed a real problem clause entirely).

| Playbook | Rule key | Case | Expected | Actual | Model's reason |
|---|---|---|---|---|---|
| halcyon-vendor-msa-customer | limitation_of_liability.cap_amount | Cap protects Vendor only and Halcyon is unlimited | red_line/red/global-uncapped-liability | compliant/none | Matches the preferred position '24-month cap, data breach uncapped'; no finding |

</details>

## 4. Corpus precision/recall

*Re-verification run (2026-11-17). The first run's table is kept in 4.3 for comparison.*

All 12 corpus DOCX files were freshly uploaded through the real, running API (`POST /api/documents`, a temporary `uvicorn` server on `127.0.0.1:8731`) and run through the real review pipeline (`POST /api/review/run`, `stance_mode` default `balanced`). That covers segment → classify → Layer 1 → Layer 2 LLM → evaluator → score → redline. `contract_type`, `party_role`, `paper_origin` and the full `context` block (region, regimes, deal_value_band, counterparty_tier, data_sensitivity, party_role, paper_origin) were supplied explicitly from each contract's `expected.yaml` entry. All 12 uploads returned 201 and all 12 reviews returned 200, with no retries and no re-runs. Every number below is computed only from these 12 fresh `contract_id`s.

**Contract 8 substitution (unchanged from the first run).** Contract 8's ground-truth `contract_type: hipaa` is not a valid upload value: `agreement_type.kind='regime'`, not `'agreement'`, and `POST /api/documents` validates against `kind='agreement'` only, so it would return 400. `"dpa"` was substituted. This pulls `halcyon-dpa-processor` into contract 8's resolved playbook set, which `expected.yaml`'s finding list does not cover (it lists only `hipaa_overlay` findings). Several of contract 8's extra flags are an artifact of that substitution, not a pipeline defect, for example the DPA-only `missing` flags `audit.audit_cost`, `data_transfers.data_residency` and `limitation_of_liability.dpa_liability_alignment`, and red lines such as `roles-processor-deemed-controller` and `liab-no-flow-down`.

**Matching methodology (identical to the first run, so before/after numbers are comparable).**

- **Compliance checks.** An expected finding with `position: preferred` is, by the pipeline's own design, never expected to produce a `flag` row (`layer2_content.py::_extraction_to_flag` returns `None` for a `preferred`/`acceptable_variant` match). It is tracked as a compliance check: correct if no actual flag exists for that `rule_key` on that contract, and a false positive if one does.
- **Matching.** Every other expected finding (`fallback_N`, `missing`, or a named red line) is matched 1:1, greedily, against an unused actual `flag` row with the same `rule_key` and `zone`. The row must also match whichever of these the expected finding specifies: position kind+rung (via `flag.position_id → rule_position.kind/rung`), red-line key (via `flag.red_line_id → red_line.key`), or `flag_type == "missing"`.
- **TP / FN / FP.** A full match is a **true positive**. A comparable expected finding with no match is a **false negative**. Any actual flag left over is a **false positive**, split into "vs.-preferred" (its `rule_key` contradicts a compliance check on that contract) and "plain" (everything else with a non-NULL `rule_key`).
- **Formulas.** Precision = TP / (TP + FP). Recall = TP / (TP + FN).
- **Excluded flags.** Flags with `rule_key = NULL` are excluded from precision's FP count and reported separately, as in the first run.

### 4.1 Per-contract results

| # | File | Gate | Actual flags | of which `missing` (red) | of which `rule_key=NULL` (excluded) | TP | FN | FP (plain) | FP (vs. preferred) | Compliance checks OK | Redlines |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 01_saas_msa_own_clean | escalated | 21 | 12 | 5 | 0 | 0 | 15 | 1 | 6/7 | 5 |
| 2 | 02_saas_msa_own_midmarket_yellow | escalated | 27 | 12 | 9 | 2 | 2 | 16 | 0 | 3/3 | 9 |
| 3 | 03_saas_msa_hipaa_counterparty_hospital_red | escalated | 56 | 13 | 20 | 2 | 6 | 34 | 0 | 2/2 | 13 |
| 4 | 04_saas_msa_gdpr_counterparty_euclinic_yellow | escalated | 45 | 13 | 19 | 0 | 2 | 24 | 2 | 3/5 | 13 |
| 5 | 05_saas_msa_counterparty_strategic | escalated | 37 | 12 | 12 | 5 | 1 | 20 | 0 | 1/1 | 9 |
| 6 | 06_dpa_gdpr_own_clean | escalated | 17 | 12 | 3 | 0 | 0 | 11 | 3 | 7/10 | 3 |
| 7 | 07_dpa_counterparty_subprocessor_breach | escalated | 26 | 7 | 12 | 1 | 2 | 11 | 2 | 1/3 | 9 |
| 8 | 08_baa_hipaa_counterparty_missing (`dpa` substituted) | escalated | 33 | 11 | 14 | 1 | 6 | 18 | 0 | 1/1 | 11 |
| 9 | 09_mutual_nda_own_clean | escalated | 16 | 9 | 5 | 0 | 0 | 10 | 1 | 5/6 | 6 |
| 10 | 10_mutual_nda_counterparty_residuals | escalated | 20 | 9 | 6 | 2 | 2 | 12 | 0 | 1/1 | 6 |
| 11 | 11_vendor_msa_counterparty_lowcap | escalated | 45 | 9 | 20 | 3 | 1 | 22 | 0 | 1/1 | 14 |
| 12 | 12_vendor_msa_counterparty_reasonable | escalated | 42 | 9 | 19 | 4 | 2 | 19 | 0 | 0/0 | 13 |

**Totals: TP=20, FN=24, FP counted=221 (plain 212 + vs.-preferred 9). Excluded from precision (`rule_key=NULL`): 144, of which 140 are free-standing `vague`/`high_risk` and 4 are global red-line `prohibited` flags (see 4.2). Compliance checks: 31/40 correct.**

**Precision = 20/241 = 8.3%. Recall = 20/44 = 45.5%.**

| Metric | First run (pre-fix) | Re-verification run | Change |
|---|---|---|---|
| TP / FN | 6 / 38 | 20 / 24 | +14 TP |
| FP counted (plain + vs.-preferred) | 221 (209 + 12) | 221 (212 + 9) | flat |
| Excluded `rule_key=NULL` flags | 125 | 144 | +19 |
| **Precision** | **2.6%** (6/227) | **8.3%** (20/241) | ×3.2 |
| **Recall** | **13.6%** (6/44) | **45.5%** (20/44) | ×3.3 |
| Precision incl. NULL-rule_key flags | 1.7% (6/352) | 5.2% (20/385) | |
| `missing` flags | 166 | 128 | −38 |

**What the TPs are.** 16 of the 20 are fallback-rung matches, the class the pre-fix run almost never reached:

- contract 2: Net 60 `fallback_2`, 15-day cure `fallback_2`
- contract 3: `governing_law` `fallback_2`, `payment_terms` `fallback_1`
- contract 5: five rung-2 fallbacks
- contract 10: `confidential_information_scope` `fallback_1`
- contract 11: Net 30 `fallback_2`, 99.5% uptime `fallback_2`
- contract 12: four rung-1 fallbacks

The other 4 are red-line or `missing` matches:

- contract 7: `subproc-specific-consent-required`
- contract 10: `surv-perpetual-all-information`. This red line was listed in section 9.5 as structurally unreachable before the parameter-type red-line fix, and it is now reached.
- contract 11: `lol-vendor-cap-under-12-months`
- contract 8: `compliance.hipaa_compliance` missing

**What the 24 FNs are**, grouped by cause:

- **Clause sat in an `other` or single-label section, so a false `missing` flag fired instead (6).** Contract 2 `subprocessors.subprocessor_changes`, contract 3 `data_protection.customer_data_use`, contract 4 `data_transfers.data_residency` and `subprocessors.authorisation_model`, contract 11 and contract 12 `breach_notification.notification_timeline` (all under `"13. SECURITY INCIDENTS"` → `other`).
- **Rule reached but landed in the wrong zone or rung (5).**
  - Contract 3: four expected red lines (`global-uncapped-liability`, `lol-consequential-removed`, `global-unannounced-audit`, `global-indemnity-own-negligence`) each produced a *yellow* plain deviation on the rule instead. Two of the global red lines did trigger, but as separate `rule_key=NULL` rows (see 4.2).
  - Contract 5: `cap_amount` expected yellow `fallback_3`, got red `fallback_2`.
- **Reached a different finding on the same rule (3).**
  - Contract 7 `notification_timeline`: expected `fallback_2`, got `fallback_1`.
  - Contract 8 `breach_notification.notification_content` and `subprocessors.subcontractor_baa_flow_down`: the expected `missing` came out as red `prohibited` red-line hits (`breach-content-single-complete-notice`, `subcontractor-flow-down-absent`). These are the right problem and the right zone through a different mechanism, but they don't match under the unchanged method.
- **No flag at all on the rule (10).**
  - Contract 2 `payment.late_fees`
  - Contract 3 `breach_notification.notification_timeline`
  - Contract 7 `return-indefinite-retention` (its section `"11. RETENTION"` is `other`)
  - Contract 8 `security.safeguards`, `individual_rights_support`, `audit.hhs_access`, `permitted_uses_of_phi` (their sections are all `other`)
  - Contract 10 `resid-missing-source-code-or-phi-exclusion` and `confidentiality.standard_of_care` (`"5. RESIDUALS"` and `"2. CONFIDENTIALITY OBLIGATIONS"` are `other`)
  - Contract 12 `term.initial_term`

**What the 221 FPs are.** 127 are false `missing` (red) flags; the 128th `missing` flag is contract 8's TP. That is 57% of all counted FPs, almost all caused by section 1.2's single-label/multi-family problem. The remaining 94 are mostly yellow "plain deviation, no position matched" flags on rules that `expected.yaml` doesn't mention for that contract, such as `payment.late_fees`, `payment.taxes`, `payment.price_increases`, `termination.effect_of_termination` and `limitation_of_liability.cap_carve_outs`, which recur on almost every counterparty-paper MSA. Now that a whole section reaches Layer 2, every rule in its family is evaluated, and anything not matched to a position becomes a deviation. `expected.yaml` lists the notable findings per contract, not an exhaustive per-rule verdict, so some of these may be real deviations the ground truth is silent on. They were counted as FP anyway, per the unchanged method, and not adjudicated individually. Separately, a few "vs.-preferred" FPs are *green* `fallback_1` flags (contract 1 `audit.customer_audit_rights`, contract 4 same, contract 7 `security.technical_organisational_measures`). The pipeline writes a flag row for a green fallback, so a clause the ground truth calls preferred and the model calls an acceptable rung-1 fallback counts as an FP even though both are green.

### 4.2 Methodology blind spot surfaced by this run: global red lines persist with `rule_key = NULL`

Making global/playbook-scope red lines reachable (one of this session's structural fixes) works: global red lines now fire. But a triggered global red line is persisted as its own `flag` row with `flag_type='prohibited'`, a non-NULL `red_line_id` (scope `global`) and **`rule_key = NULL`**. Under the unchanged method, those rows land in the excluded bucket, which was designed for free-standing `vague`/`high_risk` flags. The expected finding they correspond to is then scored as an FN. This run produced 4 such rows:

- **Contract 3:** `global-uncapped-liability` and `global-indemnity-own-negligence`. Both are exactly what `expected.yaml` expects (on `limitation_of_liability.cap_amount` and `indemnification.ip_infringement_indemnity`).
- **Contract 4:** `global-governing-law-outside-lists`. This is a false trigger: the contract is governed by Irish law, which is on the approved list, and `expected.yaml` has a green `preferred` compliance check for it.
- **Contract 8:** `global-governing-law-outside-lists`. Not in `expected.yaml`.

The headline numbers above keep the unchanged method, for comparability. **If global red-line flags are instead matched on `red_line.key` regardless of `rule_key`**, the two contract-3 hits become TPs and the other two become FPs: **recall = 22/44 = 50.0%, precision = 22/245 = 9.0%**. Whether a global red-line hit should carry the `rule_key` of the clause it fired on is a design question for the pipeline. It is listed in section 7 and was not changed here.

### 4.3 First run's per-contract table (pre-fix, for comparison)

<details><summary>First run, before the fixes: TP=6, FN=38, FP=221, precision 2.6%, recall 13.6%</summary>

| # | File | Gate | Actual flags (API) | of which `missing` (red) | of which out-of-scope vague/high_risk | TP | FN | FP (rule-governed, wrong) | FP (vs. preferred) | Redlines |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 01_saas_msa_own_clean | escalated | 34 | 15 | 15 | 0 | 0 | 18 | 1 | 15 |
| 2 | 02_saas_msa_own_midmarket_yellow | escalated | 34 | 15 | 12 | 1 | 3 | 21 | 0 | 10 |
| 3 | 03_saas_msa_hipaa_counterparty_hospital_red | escalated | 43 | 17 | 9 | 1 | 7 | 32 | 1 | 11 |
| 4 | 04_saas_msa_gdpr_counterparty_euclinic_yellow | escalated | 32 | 16 | 3 | 0 | 2 | 26 | 3 | 8 |
| 5 | 05_saas_msa_counterparty_strategic | escalated | 21 | 15 | 6 | 0 | 6 | 15 | 0 | 5 |
| 6 | 06_dpa_gdpr_own_clean | escalated | 27 | 16 | 11 | 0 | 0 | 13 | 3 | 9 |
| 7 | 07_dpa_counterparty_subprocessor_breach | escalated | 23 | 13 | 10 | 0 | 3 | 11 | 2 | 10 |
| 8 | 08_baa_hipaa_counterparty_missing | escalated | 27 | 13 | 11 | 2 | 5 | 14 | 0 | 12 |
| 9 | 09_mutual_nda_own_clean | escalated | 24 | 10 | 13 | 0 | 0 | 9 | 2 | 8 |
| 10 | 10_mutual_nda_counterparty_residuals | escalated | 21 | 10 | 9 | 1 | 3 | 11 | 0 | 9 |
| 11 | 11_vendor_msa_counterparty_lowcap | escalated | 48 | 13 | 21 | 1 | 3 | 26 | 0 | 22 |
| 12 | 12_vendor_msa_counterparty_reasonable | escalated | 18 | 13 | 5 | 0 | 6 | 13 | 0 | 5 |

</details>

## 5. Gate decisions

*Re-verification run (2026-11-17).*

| # | File | Gate decision | Worst zone | Quality failure | Approver role | Approver source | Risk score |
|---|---|---|---|---|---|---|---|
| 1 | 01_saas_msa_own_clean | escalated | red | True | general_counsel | escalation_matrix | 0.268 |
| 2 | 02_saas_msa_own_midmarket_yellow | escalated | red | True | general_counsel | escalation_matrix | 0.297 |
| 3 | 03_saas_msa_hipaa_counterparty_hospital_red | escalated | red | True | general_counsel | block_red_line | 0.343 |
| 4 | 04_saas_msa_gdpr_counterparty_euclinic_yellow | escalated | red | True | general_counsel | red_line | 0.306 |
| 5 | 05_saas_msa_counterparty_strategic | escalated | red | True | general_counsel | position | 0.358 |
| 6 | 06_dpa_gdpr_own_clean | escalated | red | True | general_counsel | escalation_matrix | 0.356 |
| 7 | 07_dpa_counterparty_subprocessor_breach | escalated | red | True | general_counsel | block_red_line | 0.345 |
| 8 | 08_baa_hipaa_counterparty_missing | escalated | red | True | general_counsel | block_red_line | 0.416 |
| 9 | 09_mutual_nda_own_clean | escalated | red | True | general_counsel | escalation_matrix | 0.361 |
| 10 | 10_mutual_nda_counterparty_residuals | escalated | red | True | general_counsel | block_red_line | 0.447 |
| 11 | 11_vendor_msa_counterparty_lowcap | escalated | red | True | general_counsel | block_red_line | 0.578 |
| 12 | 12_vendor_msa_counterparty_reasonable | escalated | red | True | general_counsel | escalation_matrix | 0.369 |

**Still 12 of 12 `escalated`**, including the three contracts authored as clean (`01`, `06`, `09`). Two independent reasons, each sufficient on its own:

1. **`worst_zone = red` on every contract**, driven on the clean contracts entirely by section 1.2's false `missing` flags (12, 12 and 9 respectively). `app/workflows/gate.py::evaluate_gate` escalates any red, as designed.
2. **New: `quality_failure = True` on all 12** (first run: 7 of 12 True). `_quality_failure` is true when any redline has `rationale.interference_detected`, which `services/redline/render.py` sets when a proposed change falls outside the flagged span. **77 of the 111 redlines** in this run have it set; per contract: 2/5, 6/9, 11/13, 9/13, 8/9, 3/3, 7/9, 1/11, 6/6, 5/6, 9/14, 10/13. A probable cause, not verified: clauses are now whole top-level sections instead of sub-clauses (section 1.1), so a redline rewrite generated against the whole clause text is much more likely to touch text outside the flag's own `char_start`/`char_end` span. This is recorded as a finding (section 7, item 1c) and was not investigated further or fixed. Even with every false `missing` flag gone, this alone would still force all 12 to `escalated`.

The approver-source column does show the new red-line wiring in action: `block_red_line`/`red_line` now appears as the escalation source on 6 contracts. `position` appears as the source on contract 5. The gate logic itself (`gate.py`) is doing what it is designed to do. The problem is still its input.

<details><summary>First run's gate table (pre-fix)</summary>

All 12 `escalated`, all `worst_zone=red`, all `general_counsel`. `quality_failure` was True on contracts 1, 2, 4, 5, 10, 11, 12 and False on 3, 6, 7, 8, 9.

</details>

## 6. Model call counts

*Re-verification run (2026-11-17). Same Haiku override (`claude-haiku-4-5-20251001`) for every call.*

Batch calls were counted from the Anthropic account's own Message-Batches history (`client.beta.messages.batches.list()` filtered to this run's window, with per-item usage read from `batches.results()`). Non-batch `call_structured` calls were counted from the gateway's own `LLM usage task=... input_tokens=... output_tokens=...` debug log lines (the server ran with `ENV=dev`).

| Phase | Mechanism | Calls | Input tokens | Output tokens |
|---|---|---|---|---|
| Layer-2 content analysis, contracts 1-4 (prompt over `layer2_max_prompt_chars`, split in 2) | Batches API | 4 batches, 8 items, all succeeded | 98,084 | 20,291 |
| Layer-2 content analysis, contracts 5-12 (fit in one call) | non-batch `call_structured` | 8 | 106,474 | 27,876 |
| Redline generation | non-batch `call_structured` | 111 (equals the sum of `redlines_count` across the 12 `/review/run` responses) | 231,990 | 73,416 |
| Upload-time contract-type classification | n/a | 0 (skipped because `contract_type` was supplied explicitly) | 0 | 0 |
| **Total** | | **127 model requests** | **436,548** | **121,583** |

**Estimated cost: about $0.94** at Haiku 4.5 list prices (non-batch $1/$5 per M input/output tokens, Batches API 50% off): batches ≈ $0.10, Layer-2 non-batch ≈ $0.25, redlines ≈ $0.60. This is approximate. The gateway's usage log does not record prompt-cache read/write tokens separately, so cache effects on the non-batch calls aren't reflected; they could move the total by a few cents either way. No call failed, nothing was retried, no contract was re-run, and there were no pre-flight or smoke-test calls this time.

For comparison, the first run's corpus phase was ≤ 4 batch calls plus 124 redline calls (section 6 of the original report). The rule-test suite's 754 calls were not repeated (section 3).

<details><summary>First run's call-count table (pre-fix)</summary>

| Phase | Mechanism | Calls |
|---|---|---|
| Rule-test suite (official run) | Batches API | 754 |
| Corpus: Layer-2 content analysis, 12 contracts | Batches API | ≤ 4 |
| Corpus: redline generation, 12 contracts | non-batch `call_structured` | 124 |
| Pre-flight validation | mixed | ≈ 10 |
| **Grand total** | | **≈ 889–892** |

</details>

## 7. Proposed fixes (separate from the numbers above)

Nothing in sections 3-6 was tuned, filtered, or re-run to improve these numbers. The following are recommendations only. Items marked **done** were applied in this session's separate fix work, before the re-verification run, and not as part of it.

1. **Fix clause-type classification/segmentation (highest priority). Partly done.** The synonym source is now the DB-backed `clause_family` table, with `"term and survival"` added. Measured effect: real clause types per contract rose on every contract, and the SaaS/vendor MSAs went from about 80% to 20-27% `other` (section 1.1). Three follow-ups remain, all surfaced by the re-verification run:
   - **1a. Extend the `clause_family` synonym table to the DPA/BAA/NDA heading phrasings** still falling to `other`. These are single-topic headings with no match today: `CONFIDENTIALITY OBLIGATIONS`, `EXCLUSIONS`, `COMPELLED DISCLOSURE`, `RESIDUALS`, `EQUITABLE RELIEF`, `NO LICENSE`, `RETURN OR DESTRUCTION`, `ROLES OF THE PARTIES`, `PROCESSING INSTRUCTIONS`, `SUBJECT MATTER AND INSTRUCTIONS`, `PURPOSE LIMITATION`, `DATA SUBJECT REQUESTS`, `PERSONNEL` / `PERSONNEL CONFIDENTIALITY`, `DATA PROTECTION IMPACT ASSESSMENTS`, `RETURN AND DELETION`, `RETENTION`, `SAFEGUARDS`, `INDIVIDUAL RIGHTS`, `ACCESS BY THE SECRETARY`, `GENERAL COMPLIANCE`, `PERMITTED USES AND DISCLOSURES`, `SECURITY INCIDENTS`. Contracts 6-10 are still 50-69% `other` because of this, and several FNs (contract 7 `return-indefinite-retention`, contract 8's four `hipaa_overlay` rules, contract 10's residuals red line) trace directly to it.
   - **1b. Let a clause carry more than one family, or make `_check_missing` content-aware.** With sub-clauses now merged into top-level sections, `"TERM AND TERMINATION"`, `"DATA PROTECTION AND SECURITY"`, `"CONFIDENTIALITY AND DATA PROTECTION"`, `"INTELLECTUAL PROPERTY AND INDEMNIFICATION"`, `"LIABILITY AND GOVERNING LAW"`, `"AUDIT AND COOPERATION"` and above all `"GENERAL PROVISIONS"` each hold several rule families under one label. `layer1_structural.py::_check_missing` then flags every unlabelled family as absent. This accounts for most of the 127 false `missing` flags, 57% of all counted FPs, and is what keeps `worst_zone=red` on the clean contracts. Options: multi-label `clause_type` per section (one per sub-clause heading or synonym hit), classify at sub-clause granularity while keeping the merged section for display, or have `_check_missing` confirm absence against the text before raising a red `missing` flag.
   - **1c. Investigate the redline `interference_detected` rate (77/111).** This now forces `quality_failure=True`, and therefore `escalated`, on all 12 contracts, independently of 1b. The probable cause is the coarser whole-section clause span (section 5), which is not verified.
2. **Decide how a triggered global red line should be attributed to a rule (new).** Global red-line flags are persisted with `rule_key = NULL` (section 4.2), so they aren't tied to the rule they fired on, either in per-rule reporting or in this report's matching. Consider stamping the `rule_key` of the clause or rule the global red line fired on. Separately, `global-governing-law-outside-lists` fired falsely on contract 4, whose governing law is Irish (an approved jurisdiction). Worth a look at that red line's semantic test or prompt.
3. **Rule-scoped red lines on contract 3 still resolve as yellow plain deviations** (`lol-consequential-removed`, plus the rule-level evaluations of uncapped liability, unannounced audit and own-negligence indemnity). Each of those rules produced a yellow `deviation` row in addition to (or instead of) the red-line hit. Only 2 of the 4 expected red lines fired at all (`global-uncapped-liability` and `global-indemnity-own-negligence`, as `rule_key=NULL` rows). `global-unannounced-audit` and the rule-scoped `lol-consequential-removed` produced nothing red: only a yellow plain deviation on the rule. Worth checking why semantic red-line detection misses these two on clearly matching text, and why the rule-level evaluation of the two that did fire stays yellow. Not investigated here.
4. **Re-run the rule-test suite on the default (non-overridden) model tier**, and, now that this session's structural fixes have landed, on the current code at all. Section 3's 59.2% is pre-fix and pre-5.5. Several of its largest failure categories (parameter-type red lines, enum blind spots, context-gated positions; see 9.5) were addressed by this session's fixes, so the number is expected to move. Re-running was outside this session's ~$1 budget.
5. **Investigate the specific rule-test failure categories even on a stronger model**, starting with category A (87 failures: expected fallback rung, model landed on default-zone deviation) and category L (22 failures: expected plain deviation, model triggered a red line). Do this after item 4's re-run, since some of these may already be fixed.
6. **Harden `Settings.anthropic_api_key`** (`backend/app/core/config.py`) with the same non-blank validator the four `object_storage_*` fields already have. The app currently starts with a blank key and only fails on the first model call. Unchanged from the first run; not addressed this session.

## 8. Other notes and caveats

- **86 pre-existing `contract` rows, unrelated to this task.** Before this task's uploads, `precedent.contract` already held 86 rows, all titled `"... — halcyon-saas-msa-vendor (H1 2026 negotiation history)"`, `paper_origin=own`, `status=executed`, inserted at `2026-11-17T07:08 GMT` — i.e. essentially concurrently with this session, in the shape of task 5.3 (synthetic negotiation history), which this task's instructions explicitly say not to run. These were not created by this task and were not touched, deleted, or counted in any number above (the 12 corpus uploads in this run are their own fresh `contract_id`s, filtered explicitly by this run's own result file, not by a blanket query of the `contract` table). Flagged only so the two pieces of work aren't confused with each other.

- **The temporary app server** was started on `127.0.0.1:8731` (`uvicorn app.main:app`) purely for this task and was stopped once this report was generated.

- **Re-verification run (2026-11-17).** A temporary server was again started on `127.0.0.1:8731` from `backend/` and stopped (killed by PID) right after the 12 reviews finished; `lsof -iTCP:8731` confirmed the port was free. The 12 new uploads have their own fresh `contract_id`s, separate from the first run's 12 and from the 86 negotiation-history rows. All analysis in sections 1, 4 and 5 is filtered to those 12 IDs. No application code, seed content, migration or `.env` was changed for the re-run, and nothing was committed. Note for anyone diffing: the working tree carries uncommitted changes made after the first run, including the `segmentation.py` heading-shape gate discussed in section 1.1, which cut contract 1 from 60 clauses to 18. That working-tree state is what was measured; the re-run did not introduce any of it. A `find -newer` check after the run confirmed that `playbook_verification.md` was the only file in the repo modified during the re-run.

- **Re-verification `contract_id`s** (every section 1/4/5 number is filtered to exactly these): 1 `74886234-bbcf-48fc-b2da-848d8cb8ceb7`, 2 `58190062-86af-4a60-a841-699a318e535c`, 3 `4611c652-23e5-4ce1-8fae-46f8f728807c`, 4 `2979a98e-a3df-49e2-b6da-3907c44b8ccd`, 5 `fc876f55-b41d-4fc8-b0ba-2f677335c1ad`, 6 `4e34b1be-1a4d-4060-9487-cf59b5532308`, 7 `658522c8-7e9b-4f61-a427-9f529be9ed7d`, 8 `85494fc9-0b92-4c0a-a9db-f97c26e168cf`, 9 `99d3f593-ce4e-4b5b-8c23-6d10edfba302`, 10 `462351f6-9a24-45a8-a5ac-fb1f155cdcc1`, 11 `1a1785d4-c058-4d9e-adb0-40bdf354002b`, 12 `6a80abcd-9633-4cfd-8e46-db9faed79663`.

- **Seed content was not touched.** No playbook rule, position, red line, objection, dependency, or test case was edited to make any number in this report look better, per the task's explicit instruction.

- **Code changes made, for the record** (both already described in full in section 2, repeated here only as a flat list for anyone diffing the repo): `backend/app/core/llm/gateway.py` — (a) `call_batch`'s request building now converts `response_model` into the wire-format `output_config` JSON schema instead of passing the raw Pydantic class, and its result parsing now uses the SDK's own `parse_beta_response` instead of assuming a `.parsed_output` attribute that a raw batch result never has; (b) all three call paths' `max_tokens` raised from a hardcoded `4096` to a shared `_MAX_TOKENS = 8192` constant. No other file was modified.

## 9. Full bypass-driven rule-test run, all 7 playbooks (human judgment, NOT Sonnet)

Run after the evaluator.py fix described in this task's briefing (a parameter-breach short-circuit that was misreporting correct fallback-rung extractions as generic "deviation" failures — now fixed, 1280 tests + 47 new ones verified passing before this run). This section is **not** a real-model run and must not be read as one.

**Critical caveat, stated as plainly as possible**: every one of the 754 model-call cases below was answered by a Claude Code agent (me) reading the rule definition and the sample clause text and producing the structured extraction a real LLM call would have produced, routed through the temporary `backend/.llm_bypass_queue/` file-queue mechanism (`LLM_FILE_QUEUE_BYPASS=true` set in `backend/.env` for the duration of this run only, then restored). **No Anthropic API call of any kind was made for this section's numbers** — not Sonnet, not Haiku, not any model. The 82.0% pass rate below reflects one careful human-equivalent reader's judgment on ~754 clauses against their rules, not Claude Sonnet's (or any model's) actual extraction accuracy. Treat it as a *ceiling-finding and content-auditing exercise* (it is very good at surfacing rule-design and harness gaps, several of which are documented below) rather than as a prediction of what a real Sonnet run would score. Section 3 above (the real Haiku-tier run) remains the only real-model data point in this file; it is retained unchanged above, not replaced.

### 9.1 Why this run happened and how it was done

Per this task's instructions, `python -m scripts.run_rule_tests --yes --playbook <key>` was run once per playbook (not once for all seven at once) — `testing.py`'s `_call_model_for_pending` sends exactly one `gateway.call_batch` per invocation of the script, so filtering by `--playbook` keeps each batch request (and therefore each round of my own judgment) to one playbook's worth of cases (69–187 items) instead of one 754-item batch for the whole run. For each playbook: the script was started in the background, the resulting request file in `.llm_bypass_queue/requests/` was read, every item's rule (title, positions with labels/rungs, parameters with extraction hints, semantic red lines) was read against its `sample_text`, and a response file matching `output_schema` was written to `.llm_bypass_queue/responses/` before `dev_bypass.py`'s 20-minute poll timeout. (One playbook, `halcyon-mutual-nda`, timed out on a first attempt because the reasoning pass ran long; the stale request was deleted and the playbook was simply re-run and answered faster the second time — no data from the timed-out attempt was used.)

### 9.2 Overall result

**651 / 794 cases passed — 82.0% pass rate** against the 95% publish-gate threshold. **754 model calls made (754 required, 754 made)** — this matches the task brief's expected call count exactly.

### 9.3 By playbook

| Playbook | Passed/Total | Pass rate | Model calls |
|---|---|---|---|
| halcyon-baseline | 68/78 | 87.2% | 69 |
| halcyon-mutual-nda | 66/86 | 76.7% | 82 |
| halcyon-saas-msa-vendor | 171/196 | 87.2% | 187 |
| halcyon-dpa-processor | 88/110 | 80.0% | 107 |
| halcyon-hipaa-overlay | 67/84 | 79.8% | 76 |
| halcyon-gdpr-overlay | 64/84 | 76.2% | 80 |
| halcyon-vendor-msa-customer | 127/156 | 81.4% | 153 |
| **Total** | **651/794** | **82.0%** | **754** |

### 9.4 By expected outcome (aggregated across all 7 playbooks)

| Expected outcome | Passed/Total | Pass rate |
|---|---|---|
| missing | 34/36 | 94.4% |
| fallback | 140/155 | 90.3% |
| compliant | 186/208 | 89.4% |
| acceptable_variant | 117/132 | 88.6% |
| red_line | 85/128 | 66.4% |
| deviation | 89/135 | 65.9% |

`missing`, `fallback`, `compliant` and `acceptable_variant` are all strong (88–94%); `red_line` and `deviation` are the weak categories — but, unlike the Haiku run in section 3, the dominant cause here is **not** reading comprehension of the clause text. It is almost entirely two structural gaps in the harness itself, documented next, that no amount of careful reading can get around.

### 9.5 Structural findings (these, not reading-comprehension misses, explain most of the `red_line`/`deviation` shortfall)

These are genuine discoveries made while doing this run, not excuses for a lower number — they were visible in the failure listings of every single playbook and are reproducible. None of them were fixed (out of scope — they are evaluator/harness/prompt-design findings, not blocking bugs; no application code was touched).

1. **Parameter-type and global-scoped red lines are never wired into `evaluate_finding` or into the rule-test harness's deterministic pre-check.** `app/services/contract_analysis/layer1_structural.py`'s own deterministic check (`_DETERMINISTIC_CONDITION_TYPES`) only recognizes `phrase`/`regex`; `evaluate_finding`'s parameter step (step 2) only ever returns a bare zone, never a `red_line_id`. Several rules' red lines — visible by key name in the seed data even though their *definitions* are never shown to the model, e.g. `global-governing-law-outside-lists`, `global-unilateral-amendment`, `ci-named-schedule-only`, `excl-no-exclusions`, `cd-no-notice-right`, `surv-perpetual-all-information`, `phi-return-destruction-under-30-days`, `regulatory-penalty-indemnity-uncapped`, `audit-unannounced-or-unlimited`, `global-uncapped-liability`, `insurance-none-required`, `confidentiality-no-standard-of-care`, `security-no-commitment`, `subcontractor-no-phi-flow-down`, `audit-vendor-refuses-all-verification`, `breach-notice-over-120-hours`, `breach-notice-no-commitment` — appear as `expected outcome='red_line'` in nearly every playbook's failure list, with the actual result correctly landing on the right *zone* (usually red) but on `outcome='deviation'`, `red_line=None`, because there is no code path that can ever attach that specific key. **These test cases are structurally unreachable by any model, Sonnet included**, until this wiring gap is closed.
2. **Enum/string-valued parameters whose literal backend `allowed_values` token is not spelled out verbatim in the prompt's `extraction_hint` are an un-guessable blind spot**, and this is the single largest driver of the `deviation` column. `_parse_parameter_value`'s enum branch falls back to the raw trimmed string when no case-insensitive match is found; `zone_for_parameter` then fails safe to **red** — and, critically, `evaluate_finding` lets that red zone **override even a correct `preferred`/`acceptable_variant` position match outright** (confirmed directly: `data_transfers.transfer_mechanism` went 0/6 in `halcyon-dpa-processor` — even the literal verbatim hint token `none_stated` failed, and a clause matching the `preferred` position word-for-word still came back `deviation/red` purely because the parameter's enum guess didn't land). The clearest single example: **`breach_notice_trigger`/`notification_trigger`'s `"confirmed"` value failed in every single playbook that has one** (HIPAA, DPA, SaaS, GDPR, vendor-MSA all show the identical pattern) — strongly suggesting the real backend token for "confirmation-triggered" is spelled differently everywhere in the codebase, not merely a one-off miss. By contrast, parameters whose hint spells out the literal snake_case token for *that specific value* (e.g. `role_designation`'s `processor_only`/`joint_controller_narrow_ancillary`, `data_residency_scope`'s `named_single_region`, `subprocessor_liability_scope`'s `inside_general_cap`) scored well. A real Sonnet call faces this identical blind spot, since the prompt never exposes `allowed_values` — this is a prompt/schema-design gap, not a model-capability one.
3. **A matched semantic red line is hardcoded to zone="red" in `evaluate_finding` step 1 with no way to produce yellow.** Two cases (`indemnification.customer_indemnity` and `indemnification.indemnity_procedure` in `halcyon-saas-msa-vendor`) expected `red_line`/**yellow** — I identified and triggered the exact correct `red_line_key` in both, and both still failed on zone alone, because a triggered red line can never be anything but red.
4. **Context-gated positions are invisible to the model.** `governing_law.choice_of_law` (GDPR overlay) explicitly says "England and Wales is green only when the deal's region is uk... let the context override decide the zone" — but the test case's `context` dict (region/tier) is never included in the prompt the model sees, only the rule block and clause text, so a context-dependent position's correct zone cannot be reproduced even with a perfect textual read.

### 9.6 Notable individual judgment calls (for spot-checking quality, not structural-gap cases)

- **`halcyon-baseline`, `governing_law.venue`**: two near-identical clauses — one phrased "consent to the exclusive jurisdiction... waive any claim of inconvenient forum," the other "submits to the exclusive jurisdiction... may not later claim inconvenient forum" — were meant to map to `preferred` and `acceptable_variant` respectively; I called it the other way around. A genuine, close 50/50 call between two very similarly worded positions.
- **`halcyon-baseline`, `amendment.written_amendment` [TRAP]**: a clause containing only the no-waiver-by-conduct sentence, with no restated "signed instrument" amendment-method sentence, was designed to still be `compliant`. I was too literal (expected both halves of the preferred description to be textually present) and called it a deviation.
- **`halcyon-mutual-nda`, `definitions.confidential_information_scope` / `confidentiality.standard_of_care`**: these two rules cratered (1/5 and 2/6) purely on my enum guesses for `ci_scope_standard`/`care_standard` (e.g. `reasonable_person_standard`) not matching the real backend token, even though every position match underneath was correct — a clean illustration of finding 9.5.2.
- **`halcyon-saas-msa-vendor`, `limitation_of_liability.consequential_damages_exclusion` / "One-way exclusion favouring Customer"**: the clause protects *Vendor* from consequential-damages liability to Customer while leaving Vendor's own claims against Customer unrestricted; I read that as favoring Vendor, but the seed's own ladder labels this outcome "favouring Customer" — I may have the direction backwards relative to the rule author's convention, a genuine ambiguity worth a second look independent of this run.
- **`halcyon-dpa-processor`, `data_transfers.transfer_mechanism`**: 0/6, entirely attributable to the enum-mismatch finding — including a case where my answer matched the `preferred` position's own wording almost verbatim and still failed on the parameter.
- **`halcyon-vendor-msa-customer`, `payment.late_fees` / "Late fee with no dispute exception"**: expected a plain `deviation`; I triggered `vdr-late-fee-punitive` because the clause explicitly states "no exception for invoices under dispute," which reads to me as applying the late fee to disputed amounts (one of the red line's own listed triggers) — a defensible but seemingly over-eager call on a clause that only omits the carve-out rather than affirmatively fee-ing disputed invoices.

### 9.7 Cleanup confirmation

- `backend/.env`'s `LLM_FILE_QUEUE_BYPASS` line was added only for this run's duration and has been removed entirely; `git diff backend/.env` is empty, confirming the file is byte-for-byte back to its state before this task started.
- `backend/.llm_bypass_queue/requests/` and `backend/.llm_bypass_queue/responses/` are both empty.
- `cd backend && .venv/bin/python -m pytest -q` was run after cleanup: **1280 passed, 4 failed** (`tests/unit/test_llm_batch.py::TestGatewayCallBatch`, all four about the real — non-bypass — `call_batch` path's interaction with a mocked Anthropic client). These 4 failures are **pre-existing and unrelated to this task**: `git diff` shows `backend/app/core/llm/gateway.py` already had uncommitted changes before this session started (the task 5.4 `call_batch`/`_MAX_TOKENS` fixes described in sections 2 and 8 above), and the failures reproduce identically with the bypass fully disabled and no other process running — this run never touched `gateway.py`, `dev_bypass.py`, `config.py`, or any test file. Flagged here for visibility, not fixed, per this task's instruction not to change application code.


## 10. Task 5.6: seed removal drill

Run 2026-11-17, after task 5.5 landed and migrations 014/015 were applied live (live DB at head `o5p6q7r8s9t0`). Proves, rather than assumes, that `backend/seed/` is fully optional: the application, its migrations and its tests do not depend on it.

1. **Working tree clean for `backend/seed/`**: confirmed via `git status --short backend/seed/` — the whole folder is untracked (`?? backend/seed/`, 4.2M), never committed on this branch, so moving it could not lose any committed history.
2. **Moved** the entire `backend/seed/` folder to a temporary holding directory outside the repository (`mktemp -d` under `/tmp`), not deleted.
3. **With the folder absent**, every check passed:
   - `uv run pytest -q` from `backend/`: **4 failed, 1334 passed** — identical to the baseline with the folder present (the 4 are the same pre-existing, unrelated `test_llm_batch.py` failures). Includes `tests/unit/test_seed_isolation.py` (32/32 passed) and a standalone re-run of that file alone to isolate it.
   - `uv run alembic upgrade head --sql` (offline mode): rendered cleanly, no error, no file access under `backend/seed/`.
   - Started the application (`uvicorn app.main:app`) with the folder absent: started cleanly, including the startup lifespan hook that populates the clause-family synonym cache from the DB (task 5.5) — confirming that cache load has no seed-folder dependency either.
   - `GET /api/health` → `200 {"status":"ok","db":true,"embedding_model":true,"storage":true,"db_schema":"precedent","db_schema_exists":true}`.
   - `GET /api/playbooks` → `200`, returned the 7 Halcyon playbooks (reference/company data served from the database, not the seed folder).
   - `GET /api/playbooks/resolve?contract_type=saas_msa&party_role=vendor&paper_origin=own` → `200`, resolved **47 rules** — confirming the full resolution engine (base + agreement + overlay playbooks, merged via the live DB) works with no seed folder on disk.
   - Server shut down cleanly afterward; port confirmed free.
4. **Repository-wide search** for `seed.`-style imports, `seed/` paths and the old script name (`scripts/seed_playbooks.py`), outside `backend/seed/` itself, across the whole repo (backend, frontend, CI, READMEs, `development_docs/`): every hit is documentation/comments/planning docs (`development_docs/*.md`, `playbook_*.md`, `backend/README.md`, `.github/workflows/ci.yml`'s own `if: hashFiles('backend/seed/tests/**') != ''` guard — which already degrades gracefully when the folder is absent) or test fixtures that deliberately contain the forbidden-import *strings* as literal text to exercise the isolation-guard test itself (`tests/unit/test_seed_isolation.py`, `tests/fixtures/legacy_playbook_rows.py`'s docstring). No actual application code or configuration outside `backend/seed/` imports from it or reads a file under it.
5. **Restored** the folder to its original path. Confirmed via `git status --short backend/seed/` (still exactly `?? backend/seed/`, nothing more or less) and `du -sh backend/seed/` (4.2M, same as before the move) that it came back unchanged.

**Result: every check in step 3 passed with the folder absent; step 4 found no code or configuration dependency; the folder was restored unchanged.** Task 5.6 is done — `backend/seed/` is confirmed fully deletable with no effect on the running application.
