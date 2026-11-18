# Authoring guide

> Source: copied verbatim from `playbook_implementation.md` sections 3.1, 3.2, 4 and 5 (repository root). Section numbers are those of the source document; sections 2.1 to 2.5 are in `company_profile.md`.

## 3.1 Rule allocation

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

## 3.2 Content quotas

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
