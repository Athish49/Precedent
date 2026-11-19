# Playbook implementation: from current state to target state

This document is the work breakdown for moving the playbook from what exists today (`playbook_status.md`) to the target design (`playbook_plan.md`). Each task is written so a sub-agent can pick it up with no other briefing.

**Every agent must read first:** sections 1 to 5 of this document, and `playbook_plan.md` section 3 (data model).

## 1. Ground rules

- **Repository:** work on the local `main` branch. Do not create worktrees. Do not push. Commit only when the user asks.
- **Database:** `backend/.env` points at a remote Postgres. Do not run migrations or the seed against it without the user's go-ahead. Write and test against mocked sessions, as the existing unit tests do.
- **Partitioning:** the database and storage accounts are shared with other projects. Everything this project creates goes in the `precedent` namespace (section 1.1). No task may create a table, view, file or vector outside it. Tasks 0.3 to 0.7 put this in place and must finish before any migration in phase 1.
- **Cloud only:** no local database and no local file storage, even temporarily (`playbook_plan.md` section 10.4). Do not add SQLite, a local Postgres, a Docker database, a local folder backend or browser storage. Scripts do not write project data to disk. Unit tests use in-memory doubles and mocks.
- **Seed isolation:** all seed code, content and seed tests live in `backend/seed/` and nowhere else. Application code never imports from it (section 3.0). Tasks that touch seed code also run `pytest seed/tests`.
- **Tests:** run `cd backend && .venv/bin/python -m pytest -q` before reporting a task done. The suite must stay green. The 84 playbook-related tests that pass today are the baseline.
- **Migrations are serial.** Only one agent writes a migration at a time. Check the head with `.venv/bin/alembic heads` and set `down_revision` to it. Existing files run `001` to `009`.
- **Legacy columns stay until task 5.5.** `preferred_language`, `acceptable_variations`, `prohibited_terms`, `fallback_language` and `escalation_threshold` remain readable so existing code keeps working during the transition.
- **Synthetic content only.** Halcyon Care is fictional. Do not use real company names as parties. Write clause language from scratch; do not copy published templates or real contracts.
- **File ownership.** A content task owns exactly the files it lists. Do not edit another task's file; report the problem instead.
- **Reporting.** Finish with: files changed, test result, each "Done when" item marked met or not met, and anything left open.

### 1.1 Project partitioning

The full rules are in `playbook_plan.md` section 10. What every agent needs to know:

**Current state**, checked read-only on 2026-11-16:

| Store | State |
|---|---|
| Neon Postgres, database `neondb`, pooled endpoint | 16 application tables, 6 views and `alembic_version`, all in `public`. All tables have 0 rows. Migration head is `i9j0k1l2m3n4` (`009`). The seed has not been run. No other project's objects are present |
| pgvector | Extension `vector` 0.8.0 in `public`; shared, leave in place |
| Cloudflare R2 | Not configured. Files go to `/tmp/precedent-storage` through a local fallback backend, which must be removed. The folder holds one 2-byte health-check file and no contract files. Keys have no project prefix |
| Local databases | None. No SQLite, local Postgres or Docker database anywhere in the project |
| Qdrant | Not used by this project |

**Rules for all tasks:**

1. The namespace comes from the `PROJECT_NAMESPACE` setting, value `precedent`. Never hard-code the schema or prefix anywhere else.
2. New models inherit the schema from the shared metadata. Do not set a schema on individual tables.
3. Migrations do not name a schema in `op.create_table` and similar calls. The migration environment sets the search path to the project schema for the duration of the migration.
4. Hand-written SQL, including views, names the schema explicitly using the setting.
5. Unqualified foreign-key strings such as `"playbook.id"` are fine: they resolve inside the project schema.
6. Never create, drop or alter anything in `public`, and never touch the `vector` extension.
7. Storage code passes logical keys such as `contracts/{id}/{filename}`. The backend adds the prefix.
8. Scripts that write data call the namespace guard from task 0.6 first.
9. There is no local storage backend to fall back to. Code that stores a file needs the cloud bucket configured; tests use the in-memory double from task 0.3.
10. Files under `backend/seed/` are source kept in git. Anything generated from them at run time goes to the database or the bucket, not to disk.

## 2. The company: Halcyon Care, Inc.

All playbook content is written from this company's point of view.

| Fact | Value |
|---|---|
| Entity | Halcyon Care, Inc., a Delaware corporation, headquartered in Boston, Massachusetts |
| EU entity | Halcyon Care Ireland Ltd, Dublin |
| Product | Halcyon Engage: patient engagement and care coordination software (appointment reminders, secure messaging, intake forms, care-plan tracking). Integrates with hospital record systems over HL7 FHIR |
| Model | Multi-tenant SaaS, annual subscription, invoiced annually in advance |
| Customers | About 310: US hospital systems and physician groups (HIPAA covered entities) and EU private clinic groups |
| Size | 430 employees; $72M annual recurring revenue; median contract $165k a year; largest $2.4M |
| Hosting | AWS `us-east-1` and `us-west-2` for US customers; `eu-west-1` for EU customers |
| Certifications | SOC 2 Type II, ISO 27001, HITRUST r2 |
| Insurance | Cyber and technology errors and omissions: $10M aggregate. General liability: $2M |
| Regulatory position | Business associate under HIPAA; processor under GDPR; controller only for its own account and billing data |
| Legal team | General Counsel; two commercial counsel; one privacy counsel (also data protection officer); two contracts managers |
| Buy side | Halcyon also buys software and services, mainly cloud, messaging and analytics vendors, some of which handle PHI as subcontractors |

### 2.1 Defined terms to use in clause language

| Context | Terms |
|---|---|
| SaaS MSA (Halcyon sells) | "Halcyon", "Customer", "Services", "Customer Data", "Documentation", "Order Form", "Fees", "Subscription Term" |
| DPA | "Processor" (Halcyon), "Controller", "Personal Data", "Sub-processor", "Data Subject" |
| HIPAA overlay | "Business Associate" (Halcyon), "Covered Entity", "PHI", "Subcontractor", "Breach" |
| Mutual NDA | "Disclosing Party", "Receiving Party", "Confidential Information", "Purpose" |
| Vendor MSA (Halcyon buys) | "Halcyon", "Vendor", "Services", "Halcyon Data", "Fees" |

### 2.2 Context dimensions

| Key | Values |
|---|---|
| `deal_value_band` | `standard` (under $100k a year), `mid` ($100k to $500k), `enterprise` ($500k to $1.5M), `strategic` (over $1.5M) |
| `counterparty_tier` | `tier_1` (large health system or public body), `tier_2` (regional group), `tier_3` (small practice or startup) |
| `data_sensitivity` | `none`, `personal_data`, `phi`, `special_category` |
| `region` | `us`, `eu`, `uk`, `other` |
| `regimes` | multi-value: `hipaa`, `gdpr` |

### 2.3 Approver roles

| Key | Function | Level | Response time |
|---|---|---|---|
| `contracts_manager` | legal | 1 | 8 hours |
| `deal_desk` | finance | 2 | 8 hours |
| `commercial_counsel` | legal | 2 | 24 hours |
| `privacy_counsel` | privacy | 2 | 24 hours |
| `security_lead` | security | 2 | 24 hours |
| `vp_sales` | sales | 3 | 24 hours |
| `vp_customer_success` | delivery | 3 | 24 hours |
| `cfo` | finance | 4 | 48 hours |
| `general_counsel` | legal | 4 | 48 hours |

### 2.4 Risk appetite

These are the anchor positions. Content authors must stay consistent with them and extend the same logic to issues not listed. Vendor side unless marked.

| Issue | Preferred | Still green | Yellow, and who approves | Red |
|---|---|---|---|---|
| Liability cap | 12 months of Fees | Up to 12 months | Up to 18 months: `commercial_counsel`. Up to 24: `general_counsel`. Strategic deals up to 36: `general_counsel` with `cfo` | Above the yellow limit, or uncapped |
| Data breach super-cap | 2× annual Fees | 2× | Up to 3×, never above $5M: `general_counsel` | Above 3× or $5M, or uncapped |
| Cap carve-outs | Fraud, wilful misconduct, payment obligations | Plus IP indemnity | Uncapped confidentiality breach excluding Customer Data: `general_counsel` | Uncapped data breach; uncapped "any breach" |
| Consequential damages | Mutual exclusion | Mutual with listed exceptions matching the carve-outs | One-way exclusion favouring Customer: `commercial_counsel` | Exclusion removed |
| Payment terms | Net 30 | Net 45 | Net 60: `deal_desk` | Beyond 60 days |
| Late fees | 1.5% a month | 1.0% a month | None: `deal_desk` | Customer set-off rights against Fees |
| Renewal price increase | Up to 7% | Capped at 5% | Fixed price for a multi-year term: `deal_desk` | Price lock over 3 years |
| Initial term | 36 months | 12 months or more | Under 12 months: `vp_sales` | Month-to-month |
| Auto-renewal | 12-month renewals, 60 days' notice | 30 days' notice | No auto-renewal: `vp_sales` | Customer may cancel a renewal after it starts, with refund |
| Termination for convenience (Customer) | None | None | After month 12, on 90 days' notice, no refund: `vp_sales` with `deal_desk` | Any time, with refund of prepaid Fees |
| Cure period | 30 days | 30 days | 15 days: `commercial_counsel` | Under 10 days, or none |
| Uptime | 99.9% monthly | 99.9% | 99.95%: `vp_customer_success` | 99.99% or higher |
| Service credits | Capped at 10% of monthly Fees; sole remedy | Up to 15% | Up to 25%: `vp_customer_success` | Above 25%, or not the sole remedy |
| Breach notification | Without undue delay, within 72 hours of confirmation | 48 hours | 24 hours: `security_lead` with `privacy_counsel` | Under 24 hours, or from "suspicion" |
| Sub-processors | General authorisation, 30 days' notice, right to object | 30 days | 60 days' notice: `privacy_counsel` | Prior written consent for each sub-processor |
| Audit by Customer | Annual, 30 days' notice, SOC 2 report first | Same | On-site audit at Customer's cost: `security_lead` | Unannounced or unlimited audits |
| Governing law | Delaware | New York, Massachusetts, California; Ireland or England and Wales for EU and UK deals | Other US states: `commercial_counsel` | Any other jurisdiction, unless `general_counsel` approves |
| Data residency | US data in US regions; EU data in the EU region | Same | Named single region: `security_lead` | Single-tenant or on-premises deployment |
| Insurance evidence | Certificate on request, limits as held | Additional insured on general liability | Cyber limit above $10M: `cfo` | Unlimited or "adequate to cover all losses" |
| IP indemnity | Third-party infringement claims against the Services | Same | Extends to combinations Halcyon specified: `commercial_counsel` | First-party indemnity for any breach of the agreement |
| Publicity | Halcyon may list Customer by name and logo | With prior written consent | No publicity right: `contracts_manager` | Customer may publicise Halcyon performance data |
| NDA term and survival | 2-year term, 3-year survival | Up to 5-year survival | Indefinite survival for trade secrets only: `contracts_manager` | Perpetual survival for all information |
| NDA residuals | No residuals clause | None | Unaided-memory residuals excluding source code and PHI: `commercial_counsel` | Broad residuals clause |
| **Buy side:** vendor liability cap | 24 months of fees, data breach uncapped | 24 months with 5× super-cap | 12 months with 3× super-cap: `commercial_counsel` | Under 12 months, or data breach inside the general cap |
| **Buy side:** vendor breach notice | 48 hours | 72 hours | Over 72 hours: `security_lead` | No commitment |

### 2.5 Global red lines

Twelve red lines apply to every playbook. Task 3.2 writes them in full.

1. Uncapped aggregate liability for Halcyon.
2. Most-favoured-customer or price-parity commitments.
3. Exclusivity or non-compete obligations on Halcyon.
4. Assignment or exclusive licence of Halcyon's pre-existing intellectual property.
5. Commitments to build features or meet roadmap dates not in the Documentation.
6. Liquidated damages or penalties beyond capped service credits.
7. Unilateral right for the counterparty to amend the agreement.
8. Source code escrow with release on anything other than insolvency or abandonment.
9. Unannounced or unlimited audit or system access.
10. Use of Customer Data to train third-party models, or sale of data, by any party.
11. Governing law or venue in a jurisdiction outside the approved and escalated lists.
12. Indemnity for the counterparty's own negligence or breach.

## 3. Seed folder layout

Everything to do with seeding lives in one folder, `backend/seed/`: the code that validates, loads and reports, the content files, and the tests for that code. It has one sub-folder per seed category, so future categories are added beside the existing ones.

```text
backend/seed/
  README.md                     # what each category is and the command to run it   (0.8)
  __init__.py
  common/                       # shared helpers: YAML loading, DB session, CLI      (0.8)
  playbooks/                    # category: playbooks
    models.py                   # seed file models                                   (0.2)
    validate.py                 # python -m seed.playbooks.validate                  (0.2)
    load.py                     # python -m seed.playbooks.load                      (2.1)
    report.py                   # python -m seed.playbooks.report                    (2.2)
    data/halcyon/
      company_profile.md  authoring_guide.md                                         (0.1)
      taxonomy.yaml                                                                  (3.1)
      authority.yaml                                                                 (3.2)
      REVIEW.md                                                                      (3.13)
      playbooks/
        baseline/playbook.yaml  rules.yaml                                           (3.3)
        mutual_nda/playbook.yaml  rules.yaml                                         (3.4)
        saas_msa_vendor/playbook.yaml  commercial.yaml                               (3.5)
        saas_msa_vendor/risk.yaml                                                    (3.6)
        saas_msa_vendor/data.yaml                                                    (3.7)
        dpa_processor/playbook.yaml  rules.yaml                                      (3.8)
        hipaa_overlay/playbook.yaml  rules.yaml                                      (3.9)
        gdpr_overlay/playbook.yaml  rules.yaml                                       (3.10)
        vendor_msa_customer/playbook.yaml  commercial.yaml                           (3.11)
        vendor_msa_customer/risk.yaml                                                (3.12)
      versions/
        saas_msa_vendor_1_1.yaml  dpa_processor_1_1.yaml                             (3.14)
  contracts/                    # category: synthetic contracts
    build.py                    # python -m seed.contracts.build                     (5.2)
    data/halcyon/
      source/  docx/  expected.yaml                                                  (5.2)
  history/                      # category: negotiation history
    models.py  load.py          # python -m seed.history.load                        (5.3)
    data/halcyon/decisions.yaml                                                      (5.3)
  tests/                        # tests for seed code only; run with: pytest seed/tests
```

### 3.0 Isolation rules

The end goal: deleting `backend/seed/` changes nothing about the application. It still starts, migrates, passes its tests and serves every feature.

1. **Dependencies run one way.** Seed code may import from `app` (models, repositories, settings). Nothing under `backend/app/`, `backend/migrations/`, `backend/scripts/` or `backend/tests/` may import from `seed`, read a file under it, or call one of its commands.
2. **Seed code stays in `backend/seed/`.** No seed loader, validator, report, model or seed test anywhere else. `backend/scripts/` holds only operational scripts for the application, such as the monitor job, the partition check and the schema move.
3. **Seed tests stay in `backend/seed/tests/`.** They are not listed in the application's `testpaths` and run with their own command. The application suite must pass with the folder absent.
4. **Seed-only dependencies** go in a separate `seed` dependency group in `pyproject.toml`, not in the application's dependencies. `pyyaml` is the first.
5. **Reference data the application needs is not seed data.** Agreement types and clause families, with their heading synonyms, are inserted by migrations, because the document pipeline depends on them. Seed data is company content: issues, roles, policies, playbooks, rules, contracts and history.
6. **The application works with no seed data loaded.** Every feature handles empty playbook, role and policy tables without error, as resolution does today when no rule matches.
7. **Application features are not seed.** The playbook bootstrap that mines language from executed contracts, the rule test runner and the publish flow are product features and live in `app`. They are not loaders and must not depend on seed files.
8. **A guard enforces rule 1** in the application test suite and in CI, alongside the existing import guards.

**Current state**, checked 2026-11-16:

| Item | Where it is now | Where it goes |
|---|---|---|
| Seed loader with 29 rules as a Python literal | `backend/scripts/seed_playbooks.py`, beside the monitor job | Replaced by `backend/seed/playbooks/load.py`; old file deleted (task 2.1) |
| Seed tests | `backend/tests/unit/test_seed_playbooks.py`, inside the application suite | Replaced by tests in `backend/seed/tests/`; old file deleted (task 2.1) |
| Setup instructions | `backend/README.md` step 4 and the structure listing name `scripts/seed_playbooks.py` | Updated to the new command and marked optional (task 2.1) |
| Planning doc | `development_docs/Backend_Structure.md` lists the seed script under `scripts/` | Updated (task 5.5) |
| Imports of seed code from the application | None. Two comments in `app` mention "the template seed"; no import, no file read | Stays that way; guard added (task 0.8) |
| `backend/seed/` | Does not exist | Created (task 0.8) |

### 3.1 Rule allocation

This table fixes which rules each task writes. `rule_key` is `{family}.{issue}`. The same key in two playbooks is deliberate: the higher-precedence playbook overrides.

| Task | File | Rules | Families and issues |
|---|---|---|---|
| 3.3 | `baseline/rules.yaml` | 12 | `governing_law`: choice_of_law, venue · `dispute_resolution`: escalation_process, forum · `notices`: method · `assignment`: consent_requirement, change_of_control · `amendment`: written_amendment · `entire_agreement`: integration, order_of_precedence · `force_majeure`: scope, termination_right |
| 3.4 | `mutual_nda/rules.yaml` | 14 | `definitions`: confidential_information_scope · `confidentiality`: standard_of_care, permitted_disclosures, exclusions, compelled_disclosure, residuals, equitable_relief · `term`: agreement_term, survival_period · `termination`: return_or_destruction · `intellectual_property`: no_license · `non_solicitation`: employee_non_solicit · `publicity`: name_and_logo_use · `governing_law`: choice_of_law |
| 3.5 | `saas_msa_vendor/commercial.yaml` | 12 | `payment`: payment_terms, late_fees, price_increases, taxes · `term`: initial_term, auto_renewal · `termination`: for_convenience, for_cause_cure_period, effect_of_termination · `suspension`: suspension_rights · `service_levels`: uptime_commitment, service_credits |
| 3.6 | `saas_msa_vendor/risk.yaml` | 14 | `limitation_of_liability`: cap_amount, cap_carve_outs, consequential_damages_exclusion, data_breach_super_cap · `indemnification`: ip_infringement_indemnity, customer_indemnity, indemnity_procedure · `warranties`: performance_warranty, disclaimer · `insurance`: coverage_requirements · `intellectual_property`: ownership, feedback_license, usage_data · `publicity`: name_and_logo_use |
| 3.7 | `saas_msa_vendor/data.yaml` | 10 | `confidentiality`: standard_of_care · `data_protection`: customer_data_use, data_return_and_deletion · `security`: security_program, certifications · `breach_notification`: notification_timeline · `subprocessors`: subprocessor_changes · `audit`: customer_audit_rights · `compliance`: compliance_with_laws, anti_corruption |
| 3.8 | `dpa_processor/rules.yaml` | 18 | `definitions`: roles_of_parties · `data_protection`: processing_instructions, purpose_limitation, data_subject_requests, data_return_and_deletion, personnel_confidentiality, dpia_assistance · `security`: technical_organisational_measures · `breach_notification`: notification_timeline, notification_content · `subprocessors`: authorisation_model, subprocessor_changes, subprocessor_liability · `data_transfers`: transfer_mechanism, data_residency · `audit`: customer_audit_rights, audit_cost · `limitation_of_liability`: dpa_liability_alignment |
| 3.9 | `hipaa_overlay/rules.yaml` | 14 | `data_protection`: permitted_uses_of_phi, minimum_necessary, individual_rights_support, data_return_and_deletion, de_identification · `security`: safeguards, phi_encryption · `breach_notification`: notification_timeline, notification_content · `subprocessors`: subcontractor_baa_flow_down · `audit`: hhs_access · `termination`: termination_for_baa_breach · `indemnification`: regulatory_penalties_indemnity · `compliance`: hipaa_compliance |
| 3.10 | `gdpr_overlay/rules.yaml` | 12 | `data_protection`: processing_instructions, data_subject_requests, dpia_assistance, records_of_processing · `data_transfers`: transfer_mechanism, transfer_impact_assessment, data_residency · `breach_notification`: notification_timeline · `subprocessors`: authorisation_model · `audit`: supervisory_authority_cooperation · `governing_law`: choice_of_law · `compliance`: gdpr_compliance |
| 3.11 | `vendor_msa_customer/commercial.yaml` | 12 | `payment`: payment_terms, late_fees, price_increases, taxes · `term`: initial_term, auto_renewal · `termination`: for_convenience, for_cause_cure_period, transition_assistance · `service_levels`: uptime_commitment, service_credits · `assignment`: change_of_control |
| 3.12 | `vendor_msa_customer/risk.yaml` | 12 | `limitation_of_liability`: cap_amount, cap_carve_outs · `indemnification`: ip_infringement_indemnity, data_breach_indemnity · `warranties`: performance_warranty · `insurance`: coverage_requirements · `intellectual_property`: ownership · `confidentiality`: standard_of_care · `security`: security_program · `breach_notification`: notification_timeline · `subprocessors`: subprocessor_changes · `audit`: customer_audit_rights |
| | **Total** | **130** | 90 distinct issues across 28 families |

### 3.2 Content quotas

The validator enforces the per-rule minimums and the global totals in `playbook_plan.md` section 7. The per-file numbers below are the planning guide that makes the totals add up. A file may trade a few parameters for extra positions if its clauses have no numbers, but must say so in its report. Rules with `negotiable: false` have no fallbacks or objections, so a file containing them reaches its position and objection quotas with extra acceptable variants and with third rungs or extra objections on its negotiable rules. The red-line quota of one per rule is above the per-rule minimum, which requires one only at `risk_weight` 7 or more; low-weight files may fall short and say so.

| Task | Rules | Positions | Parameters | Red lines | Objections | Dependencies | Test cases |
|---|---|---|---|---|---|---|---|
| 3.3 | 12 | 48 | 9 | 12 | 23 | 6 | 60 |
| 3.4 | 14 | 56 | 10 | 14 | 27 | 7 | 70 |
| 3.5 | 12 | 48 | 9 | 12 | 23 | 6 | 60 |
| 3.6 | 14 | 56 | 10 | 14 | 27 | 7 | 70 |
| 3.7 | 10 | 40 | 7 | 10 | 19 | 5 | 50 |
| 3.8 | 18 | 72 | 13 | 18 | 35 | 9 | 90 |
| 3.9 | 14 | 56 | 10 | 14 | 27 | 7 | 70 |
| 3.10 | 12 | 48 | 9 | 12 | 23 | 6 | 60 |
| 3.11 | 12 | 48 | 9 | 12 | 23 | 6 | 60 |
| 3.12 | 12 | 48 | 9 | 12 | 23 | 6 | 60 |
| **Total** | **130** | **520** | **95** | **130** (+12 global) | **250** | **65** | **650** |

## 4. Seed file format

Task 0.2 turns this into validated models. Field names match the table columns in `playbook_plan.md`.

`playbook.yaml`:

```yaml
key: halcyon-saas-msa-vendor
name: Halcyon SaaS Master Subscription Agreement (Vendor)
practice_area: saas_msa
layer: agreement
party_role: vendor
paper_scope: both
jurisdiction: US
precedence: 20
owner_role: commercial_counsel
parent: halcyon-baseline
applies_when: null
review_cadence_days: 90
description: >
  Positions for agreements under which Halcyon sells Halcyon Engage.
version:
  version: "1.0"
  effective_from: 2026-01-15
  change_summary: Initial published version.
  created_by: Senior Commercial Counsel
  approved_by: General Counsel
rule_files: [commercial.yaml, risk.yaml, data.yaml]
```

One rule in a rules file:

```yaml
rules:
  - rule_key: limitation_of_liability.cap_amount
    title: Aggregate liability cap
    required: true
    risk_weight: 10
    negotiable: true
    default_zone: yellow
    needs_human_judgment: false
    position_summary: >
      Each party's total liability is capped at the Fees paid in the 12 months
      before the claim.
    risk_rationale: >
      Halcyon's median contract is $165k a year against $10M of cyber cover.
      An uncapped or high-multiple cap on one contract can exceed the revenue
      from that customer many times over and is not insurable.
    detection_guidance: >
      Look for "aggregate liability", "shall not exceed", "limited to". The cap
      may be stated as a multiple of fees, a period of fees, or a fixed sum.
      A liability clause with no cap is a deviation, not a missing clause.
    source_ref: Halcyon Risk Policy RP-04; cyber policy aggregate limit
    authored_by: Senior Commercial Counsel
    approved_by: General Counsel
    last_reviewed_at: 2026-01-10
    positions:
      - kind: preferred
        rung: 0
        label: 12-month cap
        zone: green
        summary: Mutual cap at 12 months of Fees.
        language: >
          Except for the Excluded Claims, each party's total aggregate liability
          arising out of or related to this Agreement shall not exceed the Fees
          paid and payable by Customer in the twelve (12) months preceding the
          first event giving rise to liability.
      - kind: fallback
        rung: 1
        label: 18-month cap
        zone: yellow
        approver_role: commercial_counsel
        conditions: {deal_value_band: [mid, enterprise, strategic]}
        give_get: Ask for a 36-month initial term or annual prepayment.
        summary: Mutual cap at 18 months of Fees.
        language: >
          ... eighteen (18) months ...
      - kind: fallback
        rung: 2
        label: 24-month cap
        zone: yellow
        approver_role: general_counsel
        conditions: {deal_value_band: [enterprise, strategic]}
        give_get: Require that all indemnities sit inside the cap.
        summary: Mutual cap at 24 months of Fees.
        language: >
          ... twenty-four (24) months ...
      - kind: acceptable_variant
        label: Fixed-sum cap at or below 12 months of Fees
        zone: green
        summary: A dollar cap no higher than 12 months of Fees.
        language: >
          ... shall not exceed the greater of (a) the Fees paid in the prior
          twelve (12) months and (b) US$[amount] ...
    parameters:
      - key: cap_multiple_months
        label: Cap as months of Fees
        value_type: number
        unit: months
        direction: lower_is_better
        preferred_value: 12
        green_limit: 12
        yellow_limit: 24
        extraction_hint: >
          Convert "1x annual fees" to 12, "2x" to 24. A fixed sum is converted
          using the contract's annual Fees when known.
        context_overrides:
          - when: {deal_value_band: [strategic]}
            yellow_limit: 36
    red_lines:
      - key: lol-uncapped
        description: Halcyon's liability is uncapped or the cap is deleted.
        condition_type: semantic
        condition:
          test: >
            The clause leaves Halcyon's aggregate liability without any
            monetary limit, other than for the listed Excluded Claims.
        action: block
        rationale: Uninsurable; see global red line 1.
    objections:
      - objection: Twelve months of fees does not cover our exposure if patient data is lost.
        their_rationale: A breach affecting patients costs far more than the subscription.
        response: >
          We address data incidents separately through a higher dedicated cap,
          so the general cap does not need to carry that risk.
        talking_points:
          - Point to the data breach super-cap at 2x annual Fees.
          - The cap is mutual and also protects Customer.
        recommended_position: {rule_key: limitation_of_liability.data_breach_super_cap, rung: 0}
        frequency: common
        counterparty_profile: Large hospital systems
    dependencies:
      - related_rule_key: limitation_of_liability.data_breach_super_cap
        relation: trade_against
        note: Offer the super-cap before raising the general cap.
    test_cases:
      - name: Standard 12-month cap
        expected_outcome: compliant
        expected_zone: green
        sample_text: >
          Neither party's aggregate liability under this Agreement shall exceed
          the fees paid by Customer in the twelve months before the claim arose.
      - name: 24-month cap on an enterprise deal
        context: {deal_value_band: enterprise}
        expected_outcome: fallback
        expected_position_rung: 2
        expected_zone: yellow
        sample_text: >
          ... shall not exceed two times the annual Fees ...
      - name: Liability unlimited, reworded
        expected_outcome: red_line
        expected_red_line_key: lol-uncapped
        expected_zone: red
        sample_text: Halcyon's liability under this Agreement shall be unlimited.
      - name: Trap - negated wording
        is_trap: true
        expected_outcome: compliant
        expected_zone: green
        sample_text: >
          Nothing in this Agreement shall impose unlimited liability on either
          party; each party's liability is limited to the fees paid in the
          preceding twelve months.
```

## 5. Authoring standards for content tasks

1. **Clause language is complete and contract-ready.** Full sentences, defined terms from section 2.1, no "..." and no descriptions in place of text. The example above abbreviates only to save space.
2. **Fallbacks are real concessions in order.** Each rung gives up more than the one before. Rung order matches the risk appetite table.
3. **Yellow rungs name an approver** from section 2.3 and, where sensible, a give-get.
4. **Acceptable variants are different wording for the same or a better outcome**, as the other side might draft it.
5. **Red lines prefer `parameter` and `semantic` conditions.** Use `phrase` only for wording that is unambiguous, and set `negation_guard: true`.
6. **Objections are in the counterparty's voice;** responses are sendable text of two to four sentences.
7. **Test cases must include, per rule:** one compliant, one acceptable variant, one fallback, one deviation, and one red line or one trap. A rule with `negotiable: false` has no fallback, so it carries a `missing` case or a second deviation in its place. Sample text must be worded differently from the playbook language it tests. Traps use negated or look-alike wording.
8. **Rules with `negotiable: false`** (mandatory regulatory terms) need no fallbacks or objections but still need a variant and five test cases.
9. **Numbers are parameters.** Any period, percentage, amount or count in preferred language has a matching parameter.
10. **Rationales cite the company facts:** insurance limits, certifications, deal sizes, hosting regions.
11. **Dates:** version 1.0 effective 2026-01-15; `last_reviewed_at` between 2025-11-01 and 2026-01-10.
12. **Validate before reporting:** `cd backend && .venv/bin/python -m seed.playbooks.validate`.

## 6. Task map

| Task | Title | Depends on | Can run alongside |
|---|---|---|---|
| 0.8 | Seed folder skeleton and isolation guard | — | 0.3 |
| 0.1 | Company profile and authoring guide files | 0.8 | 0.2 |
| 0.2 | Seed file models and validator | 0.8 | 0.1 |
| 0.3 | Namespace setting, storage prefix, cloud-only storage | — | 0.1, 0.2 |
| 0.4 | Schema-aware models, migrations and SQL | 0.3 | 0.1, 0.2, 3.x |
| 0.5 | Move existing objects into the project schema | 0.4, user go-ahead | 3.x |
| 0.6 | Partition check and write guard | 0.4 | 0.5, 3.x |
| 0.7 | Connect cloud storage and delete local storage | 0.3, 0.6, R2 credentials from the owner | 0.5, 3.x |
| 1.1 | Migration: lookups and authority tables | 0.5, 0.6, 0.7 | 3.x |
| 1.2 | Migration: playbook, versions, rules, children | 1.1 | 3.x |
| 1.3 | Migration: contract, review and outcome tables | 1.2 | 1.4, 3.x |
| 1.4 | Repositories and API schemas | 1.2 | 1.3, 3.x |
| 2.1 | Seed loader | 0.2, 1.4 | 2.2, 3.x |
| 2.2 | Coverage report | 0.2 | 2.1, 3.x |
| 3.1 | Taxonomy content | 0.1, 0.2 | 3.2 |
| 3.2 | Authority content | 0.1, 0.2 | 3.1 |
| 3.3–3.12 | Ten rule files | 3.1, 3.2 | Each other; all of phases 1, 2 and 4 |
| 3.13 | Cross-file consistency review | 3.3–3.12 | — |
| 3.14 | Version 1.1 change sets | 3.13 | 5.2 |
| 4.1 | Contract type and context capture | 1.3 | 4.2, 4.8 |
| 4.2 | Resolution engine | 1.4 | 4.1, 4.8 |
| 4.3 | Structural checks and zone evaluator | 4.2 | 4.4, 4.6, 4.7 |
| 4.4 | Content analysis extraction | 4.2 | 4.3, 4.6, 4.7 |
| 4.5 | Score normalisation and three-zone gate | 4.3, 4.4 | 4.9 |
| 4.6 | Redlines from the ladder | 4.2, 1.3 | 4.3, 4.4, 4.7 |
| 4.7 | Drafting lookup | 4.2 | 4.3, 4.4, 4.6 |
| 4.8 | Playbook API: versions and children | 1.4 | 4.1, 4.2 |
| 4.9 | Frontend alignment | 4.2, 4.8 | 4.5, 4.10 |
| 4.10 | Rule test-case runner | 4.3, 4.4 | 4.9 |
| 4.11 | Bootstrap into draft versions | 4.8 | 4.9, 4.10 |
| 5.1 | Load the seed and run the report | 2.1, 2.2, 3.14, user go-ahead | 5.2 |
| 5.2 | Synthetic contract corpus | 3.13 | 3.14, phase 4 |
| 5.3 | Synthetic negotiation history | 3.13, 1.3, 2.1; its load step waits for 5.1 | 5.2 |
| 5.4 | End-to-end verification | 4.5, 4.6, 4.10, 5.1, 5.2 | — |
| 5.5 | Drop legacy columns and update docs | 5.4 | — |
| 5.6 | Seed removal drill | 5.5 | — |

Three tracks can run at once: **schema** (0.3 → 0.4 → 0.5, with 0.6 and 0.7 alongside, then 1.1 → 1.2 → 1.3; migrations strictly serial), **content** (0.8, then 0.1 and 0.2, then 3.1 and 3.2, then ten parallel files), and **tooling** (2.2). Content never touches the database, so it does not wait for partitioning. Phase 4 starts as soon as 1.4 lands and does not wait for content; it uses small fixtures.

---

## Phase 0: Setup

### 0.1 Company profile and authoring guide files

- **Depends on:** 0.8. **Parallel with:** 0.2.
- **Context:** content agents need the company facts and writing standards as files in the repo, not only in this plan.
- **Do:** create `backend/seed/playbooks/data/halcyon/company_profile.md` from the whole of section 2 of this document (the company facts table and 2.1 to 2.5), and `authoring_guide.md` from sections 3.1, 3.2, 4 and 5. Copy faithfully; do not change any number.
- **Done when:** both files exist; every table in sections 2, 3.1, 3.2, 4 and 5 is present; no value differs from this document.

### 0.2 Seed file models and validator

- **Depends on:** 0.8. **Parallel with:** 0.1.
- **Context:** ten agents will write YAML in parallel. A strict validator is what keeps them consistent.
- **Must know:** the format in section 4; the isolation rules in section 3.0; the per-rule minimums in `playbook_plan.md` section 7.2. All code for this task goes under `backend/seed/`, never under `backend/app/` or `backend/scripts/`.
- **Do:**
  1. Confirm `pyyaml` is in the `seed` dependency group (added by 0.8) and installed in `.venv`.
  2. Create `backend/seed/playbooks/models.py` with Pydantic models for taxonomy, authority, playbook header, rule and every child. Forbid unknown keys. Use literal types for every enumerated field. Define these models here; do not put them in `app`.
  3. Create `backend/seed/playbooks/validate.py`, run as `python -m seed.playbooks.validate [dir]`, defaulting to `seed/playbooks/data/halcyon`. It loads every file, validates the models, then runs cross-checks:
     - every `rule_key` resolves to a family and issue in `taxonomy.yaml` (skip with a warning if that file does not exist yet);
     - every role key exists in `authority.yaml` (same skip rule);
     - exactly one preferred position per rule; fallback rungs are 1..n with no gaps; yellow positions have an approver;
     - `recommended_position` and `expected_red_line_key` references resolve;
     - per-rule minimums are met;
     - no `rule_key` is duplicated within a playbook;
     - no clause language contains "..." or "[TBD]".
  4. Exit non-zero on any error and print file, rule key and message for each.
  5. Add `backend/seed/tests/test_playbook_models.py` with a valid fixture and at least eight failing fixtures, one per cross-check. Fixtures go in `backend/seed/tests/fixtures/`.
- **Files:** `backend/seed/playbooks/__init__.py`, `backend/seed/playbooks/models.py`, `backend/seed/playbooks/validate.py`, `backend/seed/tests/test_playbook_models.py`, `backend/seed/tests/fixtures/`.
- **Done when:** the example in section 4, written out in full, validates; each bad fixture fails with a clear message; `pytest seed/tests` passes; the application suite passes and the isolation guard from 0.8 passes.

### 0.3 Namespace setting, storage prefix, cloud-only storage

- **Depends on:** nothing. **Parallel with:** 0.1, 0.2.
- **Context:** the project shares free-tier accounts with other projects. Today nothing in the code identifies which project a table or file belongs to.
- **Do:**
  1. Add to `app/core/config.py`: `project_namespace` (default `precedent`), `db_schema` (defaults to the namespace) and `object_storage_prefix` (defaults to the namespace). Validate that `db_schema` matches `^[a-z][a-z0-9_]*$` and is not `public`.
  2. Add the three variables to `.env.example` with a comment explaining the shared-account reason. Add `PROJECT_NAMESPACE=precedent` to `.env` without changing any other line.
  3. In `app/core/storage.py`, apply the prefix inside the S3 backend: prepend `{prefix}/` to every key on put, get and presign. Callers keep passing logical keys and the `object_key` columns stay unprefixed.
  4. Reject keys that are absolute or contain `..`.
  5. Remove local storage from the code. Delete `FilesystemStorageBackend` and its export. `get_storage` returns the S3 backend or raises a clear configuration error naming the missing variable; it has no fallback.
  6. Make the four `object_storage_*` settings required, so the application fails at startup when any is missing.
  7. Rewrite `tests/unit/test_storage.py`: test the S3 backend against a mocked boto3 client, and add an `InMemoryStorage` test double under `backend/tests/` for other tests to use. Nothing in the tests writes to disk. Update `tests/conftest.py` and the CI workflow so tests get placeholder storage settings, as they already do for the database URL.
  8. Update the module docstring, `.env.example` and `backend/README.md`: cloud storage is required, and there is no local development mode for storage.
- **Files:** `backend/app/core/config.py`, `backend/app/core/storage.py`, `backend/.env.example`, `backend/.env`, `backend/README.md`, `backend/tests/conftest.py`, `backend/tests/unit/test_storage.py`, the test double, `.github/workflows/`.
- **Done when:** a test shows a put of `contracts/x/y.pdf` reaches the S3 client as `precedent/contracts/x/y.pdf`; a test shows `db_schema=public` is rejected; a test shows missing storage settings raise at startup; a search of `backend/app` and `backend/scripts` for `FilesystemStorageBackend` and `sqlite` returns nothing, and `/tmp` appears only in the partition check script from task 0.6, which names the folder in order to detect it; the suite passes without creating any file.

### 0.4 Schema-aware models, migrations and SQL

- **Depends on:** 0.3. **Parallel with:** 0.1, 0.2, 3.x. Makes no database change.
- **Must know:** the connection uses Neon's pooled endpoint, where a session-level `SET` does not reliably persist between transactions. Do not rely on a session search path at runtime.
- **Do:**
  1. In `app/db/base.py`, give `Base` a `MetaData(schema=<db_schema>)` so all 16 models are schema-qualified in generated SQL.
  2. In `migrations/env.py`: create the schema if it does not exist; configure Alembic with `version_table_schema=<db_schema>` and `include_schemas=True`; and inside the migration transaction run `SET LOCAL search_path TO <db_schema>, public` so migrations `001` to `009` and all later ones create objects in the project schema without naming it. `public` stays on the path so the `vector` type resolves.
  3. Qualify hand-written SQL with the schema from settings: the two statements in `app/db/repositories/nms_repo.py`, the five view queries in `app/services/analytics/service.py`, any table reference in `app/db/repositories/search_repo.py`, and the view definitions in `migrations/versions/009_analytics_views.py` and `004_nms_tables.py`. Update `db/views.sql` to match.
  4. Leave `CREATE EXTENSION IF NOT EXISTS vector` in migration `001` as it is.
  5. Add a test asserting every table in `Base.metadata` has the project schema, and a test that greps `app/` for raw `FROM` or `JOIN` followed by an unqualified project table or view name.
- **Files:** `backend/app/db/base.py`, `backend/migrations/env.py`, the SQL locations listed, `backend/db/views.sql`, new tests.
- **Done when:** both new tests pass; `alembic upgrade head --sql` (offline mode, no connection) shows the schema being created and the version table in the project schema; the suite passes.

### 0.5 Move existing objects into the project schema

- **Depends on:** 0.4 and the user's go-ahead. This is the only clean-up the live database needs.
- **Context:** 23 objects sit in `public`: the tables `alert`, `clause`, `clause_embedding`, `contract`, `contract_metadata`, `contract_version`, `decision_event`, `flag`, `obligation`, `party`, `playbook`, `playbook_rule`, `qa_cache`, `redline`, `review_run`, `risk_score` and `alembic_version`; and the views `counterparty_pattern`, `v_contract_intelligence`, `v_contract_value`, `v_portfolio_risk`, `v_renewal_dashboard` and `v_tabular_review`. All tables are empty.
- **Do:**
  1. Write `backend/scripts/move_to_schema.py` with `--dry-run` as the default and `--apply` to execute.
  2. It works from the fixed list above and touches nothing else. For each name it checks the object exists in `public` and does not already exist in the target schema.
  3. In one transaction: create the schema if needed; `ALTER TABLE ... SET SCHEMA` for each table; `ALTER VIEW ... SET SCHEMA` for each view. Indexes, constraints and owned sequences move with their tables.
  4. Before and after, print object counts per schema and row counts per table, and stop without committing if any row count changes.
  5. Do not move or modify the `vector` extension.
  6. Run the dry run, show the user the output, and apply only after they confirm.
  7. Afterwards run `alembic current` and confirm it reports `i9j0k1l2m3n4` from the project schema.
- **Files:** `backend/scripts/move_to_schema.py`, a unit test of the statement builder.
- **Done when:** `public` contains no tables or views owned by this project; the project schema contains 17 tables and 6 views; `alembic current` reports the same head as before; the application health check passes against the moved schema. If the user prefers to drop and re-run migrations instead, record that choice and its result in the task report.

### 0.6 Partition check and write guard

- **Depends on:** 0.4. **Parallel with:** 0.5, 3.x.
- **Do:**
  1. Create `backend/scripts/check_partition.py`, read-only. It fails if any object in the fixed project list exists in `public`, if the project schema is missing, if `alembic_version` is not in the project schema, if object storage is not configured, if any key written by this project lies outside the prefix, or if a local storage folder for this project exists (`/tmp/precedent-storage` or `/tmp/{namespace}-storage`). It prints a short table per store.
  2. Add `assert_namespace()` in `app/core/config.py` or a small helper module. It raises unless the schema is set, is not `public`, and exists. Every seed loader under `backend/seed/` and every operational script that writes data calls it first. The helper lives in `app`; seed code imports it, never the reverse.
  3. Extend `GET /api/health` to report the schema name and whether it exists.
- **Files:** `backend/scripts/check_partition.py`, the helper, `backend/app/api/routes/health.py`, tests.
- **Done when:** the check fails against the pre-move layout in a unit test with a mocked catalogue and passes against the post-move layout; the guard has a test for each failure case; the suite passes.

### 0.7 Connect cloud storage and delete local storage

- **Depends on:** 0.3, 0.6, and the owner supplying R2 credentials. **Parallel with:** 0.5, 3.x.
- **Owner prerequisite:** create a Cloudflare R2 bucket and an access key pair, and put the endpoint, bucket name, access key and secret key into `backend/.env`. An agent must not create accounts, buckets or keys, and must not ask for the secret values in chat. If the account allows only one bucket and it is shared with other projects, that is fine: the `precedent/` prefix keeps this project's files apart.
- **Context:** the only local data today is `/tmp/precedent-storage`, containing one 2-byte `__health_check__` file. There are no contract files to migrate.
- **Do:**
  1. Confirm the four storage settings are present, without printing them.
  2. Before deleting anything, list `/tmp/precedent-storage`. If it contains only `__health_check__`, delete the folder. If it contains anything else, stop: upload each file to the bucket under the prefix using its relative path as the key, confirm each upload by reading it back and comparing size, then delete the folder. Report what was found either way.
  3. Start the application and call `GET /api/health`. Confirm storage reports healthy and that the health-check object is at `precedent/__health_check__` in the bucket.
  4. List the bucket and confirm this project has written nothing outside `precedent/`. Do not read, move or delete objects belonging to other projects.
  5. Run `check_partition.py`.
- **Done when:** `/tmp/precedent-storage` no longer exists; the health check passes against R2; every object written by this project is under `precedent/`; `check_partition.py` passes for storage.

### 0.8 Seed folder skeleton and isolation guard

- **Depends on:** nothing. Do this first in the content track. **Parallel with:** 0.3.
- **Context:** seed code currently sits in `backend/scripts/` and its tests sit inside the application suite. The end state is one self-contained folder that can be deleted without affecting the application (section 3.0).
- **Do:**
  1. Create `backend/seed/` with `__init__.py`, `README.md`, and the empty packages `common/`, `playbooks/`, `contracts/`, `history/` and `tests/`, each sub-folder with a `data/` folder where section 3 shows one.
  2. In `common/`, add the shared helpers later tasks need: a YAML file loader, a database session helper that reads application settings and calls the namespace guard when it exists, and a small command-line wrapper with `--dry-run`.
  3. Add a `seed` dependency group to `backend/pyproject.toml` containing `pyyaml`, and install it into `.venv`. Do not add it to the application's dependencies.
  4. Keep seed tests out of the application's `testpaths`. Document `pytest seed/tests` in the seed README.
  5. Add the isolation guard to the application suite as `backend/tests/unit/test_seed_isolation.py`. It scans every Python file under `backend/app/`, `backend/migrations/`, `backend/scripts/` and `backend/tests/` and fails on any `import seed` or `from seed`, and on any string path that points into `seed/`. The test excludes its own file from the scan, must not import `seed`, and must pass when the folder does not exist.
  6. Add the same check to the CI workflow next to the existing import guards, and add a CI step that runs `pytest seed/tests` only when the folder exists.
  7. Write `backend/seed/README.md`: the purpose of the folder, the isolation rules, one section per category with its commands, and the statement that the application does not need this folder.
  8. Do not move or delete `scripts/seed_playbooks.py` or its test in this task. Task 2.1 replaces them.
- **Files:** `backend/seed/**` skeleton, `backend/pyproject.toml`, `backend/tests/unit/test_seed_isolation.py`, `.github/workflows/`.
- **Done when:** the folder matches section 3; the guard passes now and fails when a deliberate `import seed` is added to a file under `app` (try it, then remove it); the application suite passes; `pytest seed/tests` runs with no tests collected and exits cleanly.

---

## Phase 1: Schema

Serial. One agent at a time. Phase 1 starts only after tasks 0.5, 0.6 and 0.7 are done and `check_partition.py` passes. Each task writes its migration and the matching SQLAlchemy models, and adds model-level unit tests in the style of `tests/unit/test_playbook_repo.py`.

### 1.1 Migration: lookups and authority tables

- **Depends on:** 0.5, 0.6 and 0.7.
- **Do:** create `agreement_type`, `clause_family`, `clause_issue`, `context_dimension`, `approver_role` and `escalation_policy` exactly as in `playbook_plan.md` sections 3.1, 3.2, 3.11 and 3.12. In the same migration, insert the reference data the application itself depends on, so it never has to come from the seed folder:
  - the seven `agreement_type` rows;
  - all 29 `clause_family` rows: the 20 existing canonical types and `other`, with names and synonyms taken from `_SYNONYMS` in `app/services/document_processing/clause_types.py`, plus eight new families: `service_levels`, `security`, `subprocessors`, `breach_notification`, `data_transfers`, `publicity`, `non_solicitation`, `suspension`. Every family has a name, a category, a two-sentence description and at least four heading synonyms. No synonym maps to two families.

  Write the reference rows as literals in the migration; a migration must not read files from `seed/`. Do not change the normaliser yet.
- **Files:** `backend/migrations/versions/010_playbook_lookups.py`, `backend/app/db/models/taxonomy.py`, `backend/app/db/models/authority.py`, `backend/app/db/models/__init__.py`.
- **Done when:** upgrade and downgrade are both written; 29 family rows and 7 agreement types are inserted by the migration; models import cleanly; the suite passes.

### 1.2 Migration: playbook, versions, rules and children

- **Depends on:** 1.1.
- **Must know:** the live database has 0 rows in `playbook` and `playbook_rule` (checked 2026-11-16), so the backfill will have nothing to do there. Still write it to handle existing legacy rows, for other environments and for the unit test.
- **Do:**
  1. Extend `playbook` per section 3.2. Drop `ck_playbook_practice_area`; add the FK to `agreement_type`. Backfill `key` from a slug of `name`, `layer = 'agreement'`, `party_role = 'vendor'`, `paper_scope = 'both'`, `jurisdiction = 'global'`, `status = 'active'`. Add the unique constraint on `key` after the backfill.
  2. Create `playbook_version` and `playbook_change_log`.
  3. For each existing playbook, insert a `1.0` version with status `published` and set `current_version_id`.
  4. Extend `playbook_rule` per section 3.4. New columns are nullable in this migration. Backfill `playbook_version_id`, and `rule_key = clause_type || '.general'`. Change the FK to `playbook` to cascade on delete.
  5. Create `rule_position`, `rule_parameter`, `red_line`, `rule_objection`, `rule_dependency` and `rule_test_case`, all cascading from the rule.
  6. Backfill children from legacy columns: `preferred_language` → a `preferred` position; each entry of `acceptable_variations` → an `acceptable_variant`; `fallback_language`, when present → a rung 1 fallback, zone yellow, approver null; each entry of `prohibited_terms` → a rule-scoped `phrase` red line with `negation_guard: true` and action `block`.
  7. Add unique `(playbook_version_id, rule_key)` and unique `(playbook_id, version)`.
  8. Add an `onupdate` for `updated_at` on the `playbook` model.
- **Files:** `backend/migrations/versions/011_playbook_structure.py`, `backend/app/db/models/playbook.py`.
- **Done when:** the migration handles zero legacy rows without error; a unit test of the backfill helper functions, using a copy of the 29 legacy rules saved as plain test data in `backend/tests/fixtures/legacy_playbook_rows.py`, shows they would produce 29 preferred positions, 46 variants and 65 red lines (the test must not import from `scripts` or `seed`); legacy columns are still present; the suite passes.

### 1.3 Migration: contract, review and outcome tables

- **Depends on:** 1.2. **Parallel with:** 1.4.
- **Do:** apply every row of `playbook_plan.md` section 4 for `clause`, `contract`, `flag`, `risk_score`, `redline`, `decision_event` and `review_run`, and create `playbook_exception` per section 3.13. All new columns are nullable. Widen the `redline.position` check to `preferred` or a `fallback_` prefix followed by digits. Add `needs_approval` to the `review_run.gate_decision` check. Add the `clause.clause_type` FK only after inserting any distinct existing `clause_type` values that are missing from `clause_family`.
- **Files:** `backend/migrations/versions/012_playbook_outcomes.py`; models under `backend/app/db/models/` for the tables touched; new `exception.py`.
- **Done when:** upgrade and downgrade are written; existing tests for analysis, redline, gate and NMS still pass unchanged.

### 1.4 Repositories and API schemas

- **Depends on:** 1.2. **Parallel with:** 1.3.
- **Do:**
  1. Extend `app/db/repositories/playbook_repo.py` with: version create, copy, publish and get-current; child CRUD for all six child tables; `get_rules_with_children(version_id)` loading children in a fixed number of queries; upsert-by-key helpers for playbook, family, issue, role and policy.
  2. Add `taxonomy_repo.py` and `authority_repo.py`.
  3. Extend `app/schemas/playbook.py` with response models for every new entity and a `ResolvedRule` model carrying children plus `source_playbook_id`, `source_playbook_name` and `source_version`. Keep the legacy fields on `RuleResponse` for now.
  4. Fix PATCH semantics: use `model_dump(exclude_unset=True)` so a field can be set to null.
- **Files:** `backend/app/db/repositories/playbook_repo.py`, `taxonomy_repo.py`, `authority_repo.py`, `backend/app/schemas/playbook.py`, `backend/app/services/playbook/service.py`, matching unit tests.
- **Done when:** new repository functions have unit tests; a test proves a nullable field can be cleared through PATCH; the suite passes.

---

## Phase 2: Seed tooling

### 2.1 Seed loader

- **Depends on:** 0.2, 1.4. **Parallel with:** 2.2.
- **Context:** the current `scripts/seed_playbooks.py` holds 29 rules as a Python literal and skips any playbook whose name exists. It and its test sit outside the seed folder, which section 3.0 does not allow.
- **Do:**
  1. Create `backend/seed/playbooks/load.py`, run as `python -m seed.playbooks.load [dir]`, defaulting to `seed/playbooks/data/halcyon`. It loads the directory through the 0.2 models and writes in this order: issues, context dimensions, roles, escalation policies, global red lines, playbooks, versions, rules and children, change logs. It does not create agreement types or clause families: those come from migration `010`. If a family or agreement type named in the files is missing from the database, stop with an error saying which migration provides it.
  2. Upsert by stable key. A published version is never modified: if the file content for a published version differs from the database, stop with an error telling the author to add a new version file.
  3. One transaction per playbook; roll back that playbook on any error.
  4. Flags: `--dry-run` (validate and print the counts that would be written), `--only <playbook-key>`.
  5. Set `status = 'archived'` on any playbook already in the database whose key is not in the seed directory. Do not delete it. The live database has no playbooks today, so this affects nothing there; it protects environments where the old five-template seed was run.
  6. Write the loader's tests in `backend/seed/tests/test_playbook_load.py`.
  7. Retire the old seed code: delete `backend/scripts/seed_playbooks.py` and `backend/tests/unit/test_seed_playbooks.py`. First confirm task 1.2 has saved its copy of the legacy rules as test data.
  8. Update `backend/README.md`: replace step 4 with the new command, mark seeding as optional demonstration data that the application does not need, fix the structure listing, and point to `backend/seed/README.md`.
- **Files:** `backend/seed/playbooks/load.py`, `backend/seed/tests/test_playbook_load.py`, `backend/README.md`; deletes the two old files.
- **Done when:** `--dry-run` on the 0.2 fixture prints correct counts with no database; seed tests cover upsert, the published-version guard, rollback, archiving and the missing-reference-data error; nothing named `seed` remains under `backend/scripts/` or `backend/tests/` except the isolation guard; the application suite and the isolation guard pass.

### 2.2 Coverage report

- **Depends on:** 0.2. **Parallel with:** 2.1.
- **Do:** create `backend/seed/playbooks/report.py`, run as `python -m seed.playbooks.report [dir]`. It reads the seed files only and prints: counts per table against the seed-sourced targets in `playbook_plan.md` section 7.3 (for the two migration-sourced rows it checks only that `expected_families` lists 29 keys and that every `practice_area` used is one of the seven agreement types); per-playbook rule counts against section 7.1; per-rule minimum violations; family and issue coverage; fill rate for every optional field; zone distribution of positions; approver distribution; test-case mix by expected outcome. Exit non-zero if any target is missed. Add `--json`.
- **Files:** `backend/seed/playbooks/report.py`, `backend/seed/tests/test_playbook_report.py`.
- **Done when:** the report runs on the fixture and flags its shortfalls correctly; `pytest seed/tests` and the application suite pass.

---

## Phase 3: Content

Content tasks need only phase 0. They write YAML and do not touch application code.

### 3.1 Taxonomy content

- **Depends on:** 0.1, 0.2. **Parallel with:** 3.2.
- **Must know:** clause families are application reference data and are created by migration `010` (task 1.1), not by seed. This file lists family keys only so the validator can check references.
- **Do:** write `taxonomy.yaml` with:
  - `expected_families`: the 29 family keys, with no other fields: the 20 existing types, `other`, and `service_levels`, `security`, `subprocessors`, `breach_notification`, `data_transfers`, `publicity`, `non_solicitation`, `suspension`.
  - The 90 issues in the allocation table (section 3.1 of this document), each with name, description and detection hints.
  - At least 5 further issues not yet used by any rule, to reach 95, for example `payment.invoice_disputes`, `warranties.warranty_remedy`, `insurance.evidence_of_coverage`, `definitions.affiliates`, `limitation_of_liability.cap_basis`.
- **Files:** `backend/seed/playbooks/data/halcyon/taxonomy.yaml` only.
- **Done when:** the validator passes; 29 expected family keys; at least 95 issues; every `rule_key` in the allocation table resolves.

### 3.2 Authority content

- **Depends on:** 0.1, 0.2. **Parallel with:** 3.1.
- **Do:** write `authority.yaml` with:
  - the 5 context dimensions and their value definitions from section 2.2;
  - the 9 roles from section 2.3;
  - the 12 global red lines from section 2.5, each with a condition (prefer `semantic`), action and rationale;
  - at least 36 escalation policies. Cover yellow and red for each of these groups: liability and indemnity, payment and pricing, term and termination, service levels, security and breach notification, privacy and sub-processors, audit, intellectual property, governing law, and a catch-all. Add context-specific rows for `strategic` deals, `tier_1` counterparties and `phi` data. Each row has an owner, consulted roles, a time limit and the information the approver needs.
- **Files:** `backend/seed/playbooks/data/halcyon/authority.yaml` only.
- **Done when:** the validator passes; counts are met; every approver in the risk appetite table appears in at least one policy; a catch-all policy exists for both zones.

### 3.3 to 3.12 Rule files

Ten tasks with one shared brief. Each agent takes one row of the allocation table.

- **Depends on:** 3.1 and 3.2. **Parallel with:** each other.
- **Must know:** sections 2, 4 and 5 of this document in full. The agent writes from Halcyon's side as given by the playbook's `party_role`.
- **Do:**
  1. Write exactly the rules listed for the task, using the listed `rule_key` values.
  2. Meet the per-rule minimums and the quota row for the task.
  3. For the first rules file of a playbook (3.3, 3.4, 3.5, 3.8, 3.9, 3.10, 3.11), also write `playbook.yaml` using the values in the table below.
  4. Run the validator and fix every error in the task's own files.
- **Files:** only the file or files named for the task.
- **Done when:** the validator passes for the task's files; the quota row is met or the shortfall is explained; every yellow position has an approver consistent with section 2.4; every rule has five or more test cases, including at least one trap per three rules.

Playbook headers:

| Key | practice_area | layer | party_role | jurisdiction | precedence | owner | parent | applies_when | Review days |
|---|---|---|---|---|---|---|---|---|---|
| `halcyon-baseline` | baseline | base | mutual | global | 10 | general_counsel | — | — | 90 |
| `halcyon-mutual-nda` | nda | agreement | mutual | global | 20 | contracts_manager | halcyon-baseline | — | 90 |
| `halcyon-saas-msa-vendor` | saas_msa | agreement | vendor | US | 20 | commercial_counsel | halcyon-baseline | — | 90 |
| `halcyon-dpa-processor` | dpa | agreement | vendor | global | 20 | privacy_counsel | halcyon-baseline | — | 90 |
| `halcyon-vendor-msa-customer` | vendor_msa | agreement | customer | US | 20 | commercial_counsel | halcyon-baseline | — | 90 |
| `halcyon-hipaa-overlay` | hipaa | overlay | vendor | US | 30 | privacy_counsel | — | `{regimes: [hipaa]}` | 180 |
| `halcyon-gdpr-overlay` | gdpr | overlay | vendor | EU | 30 | privacy_counsel | — | `{regimes: [gdpr]}` | 180 |

Task-specific notes:

| Task | Notes |
|---|---|
| 3.3 Baseline | Mutual boilerplate. Low risk weights (2 to 5) except `governing_law` (6). Fewer objections are natural; make up the quota with variants |
| 3.4 Mutual NDA | Mutual positions. `governing_law.choice_of_law` overrides the baseline with a wider green list. Residuals and survival follow section 2.4 |
| 3.5 SaaS commercial | Heaviest use of parameters. Approvers are mostly `deal_desk`, `vp_sales` and `vp_customer_success` |
| 3.6 SaaS risk | Highest risk weights (8 to 10). The example in section 4 is the model for `cap_amount`; write it out in full |
| 3.7 SaaS data | General security and data terms that apply even without HIPAA or GDPR. Keep regime-specific detail out; the overlays add it |
| 3.8 DPA | Processor side. Regime-neutral where possible so it works for US state privacy law as well |
| 3.9 HIPAA overlay | Several rules are `negotiable: false` because the regulation mandates them. Cite the relevant part of 45 C.F.R. Parts 160 and 164 in `source_ref`. Overrides `data_protection.data_return_and_deletion` and both `breach_notification` rules |
| 3.10 GDPR overlay | Cite GDPR articles in `source_ref`. Overrides the DPA's `processing_instructions`, `data_subject_requests`, `transfer_mechanism`, `data_residency`, `authorisation_model` and the breach timeline. `governing_law.choice_of_law` prefers Ireland |
| 3.11 Vendor MSA commercial | Halcyon is the buyer. Positions invert: longer payment terms, termination for convenience, price caps, strong service credits |
| 3.12 Vendor MSA risk | Buyer side. High vendor caps, data breach outside the cap, 48-hour breach notice, flow-down of Halcyon's HIPAA obligations |

### 3.13 Cross-file consistency review

- **Depends on:** 3.3 to 3.12. **Serial.**
- **Do:**
  1. Run the validator and the coverage report over the whole directory; resolve every error and every missed target.
  2. Check every `related_rule_key` and cross-file `recommended_position` resolves in at least one realistic merged set: baseline + SaaS; baseline + SaaS + HIPAA; baseline + SaaS + GDPR; baseline + DPA + GDPR; baseline + NDA; baseline + vendor MSA.
  3. Check overlapping rule keys do not contradict each other. Where an overlay overrides, its limits must be the same or stricter.
  4. Check numbers against section 2.4 and check defined terms against section 2.1.
  5. Read ten randomly chosen rules end to end for legal plausibility and fix weak ones.
  6. Write `backend/seed/playbooks/data/halcyon/REVIEW.md` listing what was checked and what was changed.
- **Files:** any file under `backend/seed/playbooks/data/halcyon/playbooks/`; `REVIEW.md`.
- **Done when:** validator and report both exit zero; all six merged sets resolve with no dangling reference; `REVIEW.md` exists.

### 3.14 Version 1.1 change sets

- **Depends on:** 3.13. **Parallel with:** 5.2.
- **Context:** shows versioning working. Version 1.0 stays untouched.
- **Do:** write `versions/saas_msa_vendor_1_1.yaml` and `versions/dpa_processor_1_1.yaml`. Each is a full rule set for version 1.1 (effective 2026-07-01) plus a `changes` list. Together they contain at least 20 change-log entries: at least 14 `modified`, 3 `added` and 3 `removed` or replaced. Every entry has a field path, old and new values, and a reason tied to fictional negotiation data, for example "Fallback 1 was accepted in 61% of enterprise deals in the first half of 2026; promoted to preferred for the enterprise band." Extend the 0.2 models if the format needs it, and add a test.
- **Done when:** validator passes; 9 versions in total; at least 20 change-log entries; version 1.0 files are byte-identical to before.

---

## Phase 4: Wiring

Code tasks. Use small hand-built fixtures; do not wait for phase 3. Follow the existing patterns: deterministic logic in services, model calls only through `app/core/llm/gateway`, and mocked sessions in unit tests.

### 4.1 Contract type and context capture

- **Depends on:** 1.3. **Parallel with:** 4.2, 4.8.
- **Context:** `contract.contract_type` is never written today, so resolution always returns nothing.
- **Do:**
  1. Add optional form fields to `POST /api/documents`: `contract_type`, `party_role`, and `context` as a JSON string. Validate against `agreement_type` and `context_dimension`.
  2. When `contract_type` is not supplied, classify it in document processing from the title and the first 3,000 characters with one structured model call (new task key, fast tier, new prompt file). Store the result; leave it null if confidence is low.
  3. Derive `regimes` when not supplied: `hipaa` if the text mentions PHI or business associate terms, `gdpr` if it mentions GDPR, controller and processor. Deterministic keyword rules.
  4. Derive `deal_value_band` from a supplied deal value, using the band boundaries in `context_dimension`.
  5. Add `PATCH /api/repository/contracts/{id}` for `contract_type`, `party_role` and `context`.
  6. Context dimensions are seed or user data, so handle their absence: with no dimensions defined, accept the context as given, skip validation and skip band derivation.
- **Done when:** an uploaded contract has a non-null `contract_type` in tests with the fake gateway; invalid values return 400; PATCH works; the suite passes.
- **Note (2026-11-18): step 2 is superseded by `document_processing_plan.md`.** This task's own-gateway model call for classifying `contract_type` from the title and first 3,000 characters was replaced before it shipped: `document_processing_implementation.md` task 3.4 deletes `classify_contract_type`, its prompt (`contract_type_classify.md`) and its schema (`core/llm/schemas/classification.py`) outright. Contract type is now one enum field inside the Extend Extract schema generated by `document_processing/fields.py` — it comes back in the same run that produces every other field, with no separate call through `core/llm`. A user-supplied `contract_type` still wins, recorded as `contract_type_source = "user"`; the extracted value is recorded as `"extracted"`. Steps 1, 3, 4, 5 and 6 of this task are unaffected and were built as written; only step 2's mechanism changed.

### 4.2 Resolution engine

- **Depends on:** 1.4. **Parallel with:** 4.1, 4.8.
- **Do:** rewrite `app/services/playbook/routing.py` to implement `playbook_plan.md` section 5.1. Signature: `resolve(session, contract_type, party_role, paper_origin, context) -> ResolveResponse`. Return a list of `ResolvedRule` with children and source fields, the pinned version ids, and the applied playbook keys. Evaluate `applies_when` with a small pure function `matches(condition, context)`. Sort ties deterministically by playbook key. Change `GET /api/playbooks/resolve` to accept the new query parameters and return the list. Update every caller: `contract_analysis/service.py`, `workflows/review_pipeline.py`, `api/routes/redlines.py`. Provide a `rules_by_clause_type` helper so callers that still key by clause type keep working until 4.3 to 4.6 land.
- **Done when:** tests cover base plus agreement plus overlay merge, override by precedence, `applies_when` filtering, party-role selection, unknown type returning the baseline only, and deterministic ordering; the suite passes.

### 4.3 Structural checks and zone evaluator

- **Depends on:** 4.2. **Parallel with:** 4.4, 4.6, 4.7.
- **Do:**
  1. In `layer1_structural.py`, replace the `prohibited_terms` loop with evaluation of `phrase` and `regex` red lines at rule, playbook and global scope. Implement `negation_guard`: skip a match when a negation word ("not", "no", "nothing", "neither", "never", "without") appears earlier in the same sentence within 60 characters.
  2. Missing-clause check runs per required rule; report it once per clause family.
  3. Create `app/services/contract_analysis/evaluator.py` with pure functions implementing `playbook_plan.md` section 5.2: `zone_for_parameter(parameter, value, context)`, applying `context_overrides`; and `evaluate_finding(rule, extracted, context)`, returning zone, matched position or red line, and reason.
  4. Populate the new flag fields `rule_key`, `zone`, `position_id`, `red_line_id` and `parameter_values`.
- **Done when:** the four benign probe sentences listed in `playbook_status.md` section 5 no longer flag; parameter boundary values are tested at, just inside and just outside each limit; the suite passes.

### 4.4 Content analysis extraction

- **Depends on:** 4.2. **Parallel with:** 4.3, 4.6, 4.7.
- **Do:** change the Layer 2 prompt and output schema so that for each clause the model receives the resolved rules for that clause family (title, summary, positions with labels, parameters with hints, semantic red-line tests, detection guidance) and returns, per rule: which position the text matches (`preferred`, a variant, a fallback rung, or none); extracted parameter values with a verbatim quote; a yes or no with a quote for each semantic red line; and the existing risk and vagueness flags. Keep one call per contract; if the prompt exceeds the configured size, split by clause batches. Pass the result to the 4.3 evaluator; the model never assigns the zone. Store the issue keys of the rules matched in each clause in `clause.issue_keys`. Update both prompt files and `core/llm/schemas/analysis.py`.
- **Done when:** fake-gateway tests show a fallback match, a parameter breach and a semantic red line each producing the right zone through the evaluator; ungoverned clauses are still assessed; the suite passes.

### 4.5 Score normalisation and three-zone gate

- **Depends on:** 4.3, 4.4.
- **Do:** implement `playbook_plan.md` section 5.3. Set `WEIGHTS_VERSION = "v2"`. Store `max_zone`. In `workflows/gate.py`, decide from the worst zone, add `needs_approval`, resolve the approver from the position or else the escalation matrix (most specific match, then priority), and put approver role, time limit and required information into `gate_reason`. When no position approver and no escalation policy applies, which is the case with no seed data loaded, still return the decision and record that no approver is configured. Record `playbook_version_ids` on the review run. Rewrite the gate tests to use scores the scorer can actually produce.
- **Done when:** score is always between 0 and 1; a test proves a green-only contract auto-applies, a yellow one routes to the right role, and a red one escalates; a block red line cannot route below `general_counsel`; the suite passes.

### 4.6 Redlines from the ladder

- **Depends on:** 4.2, 1.3. **Parallel with:** 4.3, 4.4, 4.7.
- **Do:**
  1. Pass the rule's positions to redline generation. The preferred redline adapts rung 0 language to the contract's defined terms; alternatives are the fallback rungs allowed by `conditions`, in order. The model may adapt wording but not invent a position; each alternative carries its `position_id`.
  2. Build the counterparty comment from the best-matching objection's response when one exists; record `objection_id`.
  3. Toggle steps one rung at a time and sets `position` to `fallback_n`.
  4. Decision events record `rule_id`, `rule_key`, `position_id` and `playbook_version_id`.
  5. Accepting a yellow rung creates a `playbook_exception` with status `requested` and the right approver.
  6. Fix the counterparty placeholder: do not write a zero UUID when the counterparty is unknown.
- **Done when:** tests show alternatives come from the playbook in rung order; conditions filter rungs; toggling twice reaches `fallback_2`; an exception row is created for a yellow rung; the suite passes.

### 4.7 Drafting lookup

- **Depends on:** 4.2. **Parallel with:** 4.3, 4.4, 4.6.
- **Do:** in `services/drafting/service.py`, resolve the playbook from `contract_type`, `party_role` and context in the request and return rung 0 language for the requested clause type, or issue when given, with source `playbook`. Keep the caller-supplied `preferred_language` override. Align the request schema with what the frontend sends (`context` as text, optional `mode`).
- **Done when:** a request with a known contract type and clause type returns playbook language without a model call; a miss falls through to frequency and then the model; the suite passes.

### 4.8 Playbook API: versions and children

- **Depends on:** 1.4. **Parallel with:** 4.1, 4.2.
- **Do:** add routes for: list versions; create a draft from the current version; publish a draft, which runs test cases when 4.10 exists and otherwise only validates minimums; diff two versions; CRUD for positions, parameters, red lines, objections, dependencies and test cases on draft versions only (409 on published); list taxonomy, roles, context dimensions and escalation policies. Writing to a published version returns 409. Deleting a playbook cascades. Every edit on a draft appends to `playbook_change_log`. Update `development_docs/API_Spec.md`.
- **Done when:** route tests cover the draft-publish cycle, the 409 cases, cascade delete and change-log creation; the suite passes.

### 4.9 Frontend alignment

- **Depends on:** 4.2, 4.8. **Parallel with:** 4.5, 4.10.
- **Scope:** `frontend/` only, not `frontend_v2/`.
- **Do:** update `lib/api/types.ts` and `hooks.ts` to the new shapes. Fix resolve preview to send the new parameters and read the list. Fix bootstrap to send `playbook_id` and `contract_ids` and read `created_rule_count`. In the rule editor, change risk weight to 1–10, remove the escalation threshold field, and add tabs for positions, parameters, red lines, objections and test cases. Show version and status on the playbook header with draft and publish actions. Add contract type, party role and context fields to the upload form.
- **Done when:** type-check and lint pass; with the backend running locally the page lists playbooks, opens a rule with its ladder, and the resolve preview renders. Say so plainly if the browser check could not be done.

### 4.10 Rule test-case runner

- **Depends on:** 4.3, 4.4. **Parallel with:** 4.9.
- **Do:** create `app/services/playbook/testing.py` and `scripts/run_rule_tests.py`. For each test case, build a one-clause input, run structural checks, extraction and the evaluator, and compare outcome, zone, rung and red-line key with the expected values. Two modes: `--deterministic` runs only cases decidable without the model (phrase, regex and missing cases); the default mode calls the model and is cost-bearing, so it prints the number of calls and asks for `--yes` to proceed. Output pass rate per playbook, per rule and per expected outcome, plus failing cases. Add `POST /api/playbooks/versions/{id}/test`, and make publish require a pass rate threshold, default 95%.
- **Done when:** deterministic mode runs in unit tests against fixtures; default mode is tested with the fake gateway; the suite passes.

### 4.11 Bootstrap into draft versions

- **Depends on:** 4.8. **Parallel with:** 4.9, 4.10.
- **Do:** change `services/playbook/bootstrap.py` so mined language is written as a `preferred` position and `acceptable_variant` positions on rules in a draft version, with `authored_by = "bootstrap"`. It never writes to a published version and never creates fallbacks, red lines or parameters. Sample across contracts instead of taking the first five clauses.
- **Done when:** existing bootstrap tests are updated and pass; a test proves a published version is rejected.

---

## Phase 5: Load, verify and clean up

### 5.1 Load the seed and run the report

- **Depends on:** 2.1, 2.2, 3.14, and the user's go-ahead to touch the database.
- **Do:** run `check_partition.py` first and stop if it fails. Then run `alembic upgrade head`, then the loader with `--dry-run`, then for real. Run `check_partition.py` again at the end. Run the coverage report and a set of count queries against the database. Run the loader a second time to prove it is idempotent.
- **Done when:** database counts equal the seed file counts and meet every target in `playbook_plan.md` section 7.3; the second run writes nothing; no playbook outside the seed directory was deleted.

### 5.2 Synthetic contract corpus

- **Depends on:** 3.13. **Parallel with:** 3.14 and phase 4.
- **Storage note:** the DOCX files and their source text are source content kept in git. When the corpus is used in task 5.4, each file is uploaded through the API and stored in the cloud bucket; no working copies are kept on disk.
- **Do:** write the source text for 12 contracts under `backend/seed/contracts/data/halcyon/source/`, and a generator `backend/seed/contracts/build.py` (run as `python -m seed.contracts.build`) that turns them into DOCX under `docx/` using `python-docx`. The parse test goes in `backend/seed/tests/`. Use fictional counterparties. Each is 6 to 15 pages with numbered headings the segmenter can detect. Mix:

  | # | Type | Paper | Profile |
  |---|---|---|---|
  | 1 | SaaS MSA | own | Clean; should pass green |
  | 2 | SaaS MSA | own | Edited by a mid-market customer; four yellow deviations |
  | 3 | SaaS MSA + HIPAA | counterparty | Hospital system paper; red on liability and audit |
  | 4 | SaaS MSA + GDPR | counterparty | EU clinic group; yellow on residency and sub-processors |
  | 5 | SaaS MSA | counterparty | Strategic deal; fallbacks valid only because of the band |
  | 6 | DPA + GDPR | own | Clean |
  | 7 | DPA | counterparty | Per-sub-processor consent and 24-hour breach notice |
  | 8 | BAA (HIPAA) | counterparty | Missing required clauses |
  | 9 | Mutual NDA | own | Clean |
  | 10 | Mutual NDA | counterparty | Residuals clause and perpetual survival |
  | 11 | Vendor MSA | counterparty | Vendor paper with a low cap and no breach notice |
  | 12 | Vendor MSA | counterparty | Reasonable vendor paper; mostly green |

  Write `backend/seed/contracts/data/halcyon/expected.yaml` listing, per contract, the contract type, context, and every expected finding with rule key, zone and position or red line.
- **Done when:** 12 DOCX files parse with the existing parser in a unit test; `expected.yaml` lists at least 60 expected findings in total; at least 15 are red and at least 20 yellow.

### 5.3 Synthetic negotiation history

- **Depends on:** 3.13, 1.3, 2.1. **Parallel with:** 5.2.
- **Do:** write `backend/seed/history/data/halcyon/decisions.yaml` with 15 fictional counterparties across the three tiers, 150 decision events and 40 exceptions keyed by `rule_key` and rung, dated across the first half of 2026. Shape the data so it supports the reasons in the 3.14 change logs, for example a high acceptance rate for the fallback that 1.1 promotes. Add `backend/seed/history/models.py` and `backend/seed/history/load.py` (run as `python -m seed.history.load`) to validate the file and insert parties, events and exceptions. Tests go in `backend/seed/tests/`. Authoring and tests need no database. The real load runs after task 5.1, because events reference loaded rules, and needs the user's go-ahead like any other write.
- **Done when:** the history models validate the file; counts are met in the file and, after the load, in the database; every change-log reason in 3.14 that cites a figure is reproducible from this data, shown by a small script or test.

### 5.4 End-to-end verification

- **Depends on:** 4.5, 4.6, 4.10, 5.1, 5.2. Cost-bearing: uses the model. Confirm with the user first.
- **Do:** run the rule test suite in default mode over all 650 cases. Upload the 12 corpus contracts through the API and compare findings with `expected.yaml`. Record pass rate by playbook and by expected outcome, precision and recall of findings against the corpus, gate decisions per contract, and model call counts. Write the results to `playbook_verification.md` at the repository root, including failures as they are.
- **Done when:** the report exists with real numbers; rule-test pass rate and corpus recall are stated; every failure is listed with a probable cause. Do not tune the playbook to hide failures; list proposed fixes separately.

### 5.5 Drop legacy columns and update docs

- **Depends on:** 5.4. Needs the user's go-ahead because it is destructive.
- **Do:** confirm no code reads the five legacy columns (search the backend and frontend). Write migration `013` dropping them, with a downgrade that recreates them empty. Remove the legacy fields from schemas and types. Delete `_SYNONYMS` from `clause_types.py` and load synonyms from `clause_family`, cached at startup; those rows come from migration `010`, so this does not make the application depend on seed data. Update `development_docs/Backend_Structure.md` (seed code now lives in `backend/seed/`, not `scripts/`), `development_docs/Data_Model.md`, `Architecture.md` (diagram 7 and the note that versioning is out of scope), `API_Spec.md`, `PRD.md` section 3.2 and `backend/README.md`.
- **Done when:** the search for legacy field names returns nothing outside migrations and the legacy fixture; the suite passes; the docs describe the new model.
- **Note (2026-11-18): the `clause_types.py`/`_SYNONYMS` part of this task is superseded by `document_processing_plan.md`.** `document_processing_implementation.md` phase 5 (task 5.1) deletes `clause_types.py` outright, not just its in-code `_SYNONYMS` dict — it is replaced by a new module, `document_processing/clause_typing.py` (task 2.4), which already reads `clause_family` (key, name, synonyms) through `load_family_index(session)`, cached per process with `clear_family_index_cache()`, built from the same migration `010` rows this task's `load_synonym_cache` would have read. So by the time this task runs, there is no `_SYNONYMS` dict left to delete and no synonym cache left to add — that half of the "Do" list is already done, by a different module, for a different reason (Extend's section family is tried first; the dictionary is the fallback). This task's other work is unaffected: the migration-`013` legacy-column drop, the schema/type updates, and the `Backend_Structure.md`/`Data_Model.md`/`Architecture.md`/`API_Spec.md`/`PRD.md`/`backend/README.md` doc updates listed here still need doing on their own terms (and overlap with, but are not replaced by, the S1 doc rewrite done for `document_processing_implementation.md` task 5.4).

### 5.6 Seed removal drill

- **Depends on:** 5.5. Last task.
- **Context:** the requirement is that deleting `backend/seed/` affects nothing in the application. This task proves it instead of assuming it.
- **Do:**
  1. Confirm the working tree is clean for `backend/seed/`, so nothing can be lost.
  2. Move `backend/seed/` to a location outside the repository, such as the session scratch folder. Do not delete it.
  3. With the folder absent: run the application suite; run `alembic upgrade head --sql` in offline mode; start the application and call `GET /api/health`; call `GET /api/playbooks` and `GET /api/playbooks/resolve` for one contract type; run the isolation guard.
  4. Search the repository outside `backend/seed/` for `seed.` imports, `seed/` paths and the old script name, including the frontend, CI workflow, README files and `development_docs/`. Documentation may mention the folder; code and configuration may not depend on it.
  5. Move the folder back and confirm `git status` shows no change under it.
  6. Record the result of each check in the task report. Fix any failure in the application side, not by adding a dependency on seed.
- **Done when:** every check in step 3 passes with the folder absent; step 4 finds no code or configuration dependency; the folder is restored unchanged.

---

## 7. Definition of done for the whole programme

0. `check_partition.py` passes: nothing belonging to this project exists outside the `precedent` schema or storage prefix, and no local database or local storage folder exists.
1. Every target in `playbook_plan.md` section 7 is met in the database.
2. An uploaded contract resolves a non-empty, version-pinned rule set.
3. Every finding carries a rule key, a zone and, where relevant, a position or red line.
4. The gate returns one of three decisions and, with the seed loaded, names an approver for yellow and red.
5. Redline alternatives come from the playbook ladder.
6. A playbook change goes through draft, test and publish, and appears in the change log.
7. `playbook_verification.md` reports measured results from the rule tests and the corpus.
8. All seed code, content and seed tests are under `backend/seed/`, and the seed removal drill (task 5.6) passes: with the folder absent, the application suite passes and the application starts.
