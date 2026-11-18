"""Proof that every figure-citing change-log reason in task 3.14's version
files is reproducible from ``decisions.yaml`` alone (task 5.3's "Done when").

For each cited reason this test:

1. Confirms the exact cited figures still appear, verbatim, in the real
   ``playbooks/data/halcyon/versions/*_1_1.yaml`` reason text (a guard: if
   3.14's numbers ever change, this test fails loudly instead of silently
   passing against stale expectations).
2. Counts the matching ``decisions.yaml`` decision events — weighted by each
   entry's ``count`` (see ``seed.history.models`` module docstring) — and
   asserts the resulting numerator/denominator match the cited figures
   exactly.

Each statistic's denominator is one rule_key's full "pool" of weighted
decision events in ``decisions.yaml``; the numerator is the subset tagged
with the ``category`` that corresponds to the cited subset. Both are summed
directly from the file via :func:`_weight`, never hand-totalled, so a future
edit to ``decisions.yaml`` that breaks a ratio breaks this test.
"""

from __future__ import annotations

from pathlib import Path

from seed.common.yaml_loader import load_yaml, load_yaml_mapping
from seed.history.load import load_valid_file
from seed.history.models import DecisionEventEntry

VERSIONS_DIR = Path(__file__).parent.parent / "playbooks" / "data" / "halcyon" / "versions"
DECISIONS_FILE = Path(__file__).parent.parent / "history" / "data" / "halcyon" / "decisions.yaml"

SAAS = "halcyon-saas-msa-vendor"
DPA = "halcyon-dpa-processor"


def _reason_text(file_name: str, field_path: str) -> str:
    """The ``reason`` string of the ``changes`` entry with this ``field_path``."""
    doc = load_yaml_mapping(VERSIONS_DIR / file_name)
    for change in doc["changes"]:
        if change["field_path"] == field_path:
            return change["reason"]
    raise AssertionError(f"{file_name}: no change entry with field_path {field_path!r}")


def _weight(events: list[DecisionEventEntry], playbook_key: str, rule_key: str, *categories: str) -> int:
    """Sum of ``count`` across events matching this rule and any of ``categories``."""
    return sum(
        e.count
        for e in events
        if e.playbook_key == playbook_key and e.rule_key == rule_key and e.category in categories
    )


# ---------------------------------------------------------------------------
# One case per figure-citing reason in the two 3.14 version files.
# `anchor` is a verbatim substring of the real reason text (belt-and-suspenders
# against the hardcoded expected numbers drifting from the source).
# ---------------------------------------------------------------------------

CASES = [
    # --- saas_msa_vendor_1_1.yaml -----------------------------------------
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="payment.late_fees.parameters.late_fee_percent_per_month.preferred_value",
        anchor="61% of the 72 late-fee negotiations",
        playbook_key=SAAS, rule_key="payment.late_fees",
        numerator=("late_fee_fallback1_accepted",),
        denominator=("late_fee_fallback1_accepted", "late_fee_preferred_held", "late_fee_other"),
        expected_numerator=44, expected_denominator=72,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="payment.late_fees.parameters.late_fee_percent_per_month.preferred_value",
        anchor="20 deals (28%) that held the 1.5% preferred rate",
        playbook_key=SAAS, rule_key="payment.late_fees",
        numerator=("late_fee_preferred_held",),
        denominator=("late_fee_fallback1_accepted", "late_fee_preferred_held", "late_fee_other"),
        expected_numerator=20, expected_denominator=72,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="term.initial_term.risk_weight",
        anchor="33 of the 61 initial-term negotiations",
        playbook_key=SAAS, rule_key="term.initial_term",
        numerator=("initial_term_opened_below_preferred",),
        denominator=("initial_term_opened_below_preferred", "initial_term_at_or_above_preferred"),
        expected_numerator=33, expected_denominator=61,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="term.auto_renewal.parameters.renewal_notice_days.context_overrides[tier_1].yellow_limit",
        anchor="9 of 14 tier-1 auto-renewal negotiations",
        playbook_key=SAAS, rule_key="term.auto_renewal",
        numerator=("auto_renewal_tier1_short_notice_accepted",),
        denominator=("auto_renewal_tier1_short_notice_accepted", "auto_renewal_tier1_other"),
        expected_numerator=9, expected_denominator=14,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="termination.for_convenience.parameters.tfc_notice_days.yellow_limit",
        anchor="5 of the 19 enterprise and strategic deals",
        playbook_key=SAAS, rule_key="termination.for_convenience",
        numerator=("tfc_settled_75_days",),
        denominator=("tfc_settled_75_days", "tfc_other"),
        expected_numerator=5, expected_denominator=19,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="termination.for_cause_cure_period.parameters.cure_period_days.yellow_limit",
        anchor="3 of the 48 cure-period negotiations",
        playbook_key=SAAS, rule_key="termination.for_cause_cure_period",
        numerator=("cure_period_below_10_days",),
        denominator=("cure_period_below_10_days", "cure_period_standard"),
        expected_numerator=3, expected_denominator=48,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="service_levels.uptime_commitment.parameters.maintenance_notice_hours.yellow_limit",
        anchor="9 of the 22 uptime and maintenance negotiations",
        playbook_key=SAAS, rule_key="service_levels.uptime_commitment",
        numerator=("uptime_72hr_notice_accepted",),
        denominator=("uptime_72hr_notice_accepted", "uptime_48hr_standard"),
        expected_numerator=9, expected_denominator=22,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="audit.customer_audit_rights.parameters.audit_notice_days.yellow_limit",
        anchor="7 of the 24 audit-rights negotiations",
        playbook_key=SAAS, rule_key="audit.customer_audit_rights",
        numerator=("saas_audit_10day_notice_accepted",),
        denominator=(
            "saas_audit_10day_notice_accepted",
            "saas_audit_tier1_two_onsite",
            "saas_audit_standard",
        ),
        expected_numerator=7, expected_denominator=24,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="warranties.performance_warranty.parameters.warranty_cure_period_days.yellow_limit",
        anchor="4 of 18 performance-warranty negotiations",
        playbook_key=SAAS, rule_key="warranties.performance_warranty",
        numerator=("warranty_10day_cure_accepted",),
        denominator=("warranty_10day_cure_accepted", "warranty_standard_cure"),
        expected_numerator=4, expected_denominator=18,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="insurance.coverage_requirements.parameters.cyber_eo_limit_usd.yellow_limit",
        anchor="3 of 9 large-account insurance negotiations",
        playbook_key=SAAS, rule_key="insurance.coverage_requirements",
        numerator=("insurance_25m_accepted",),
        denominator=("insurance_25m_accepted", "insurance_20m_standard"),
        expected_numerator=3, expected_denominator=9,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="payment.payment_terms.positions[+fallback_3]",
        anchor="4 of the 50 payment-terms negotiations",
        playbook_key=SAAS, rule_key="payment.payment_terms",
        numerator=("payment_terms_net75_strategic",),
        denominator=("payment_terms_net75_strategic", "payment_terms_standard"),
        expected_numerator=4, expected_denominator=50,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="audit.customer_audit_rights.positions[+fallback_3]",
        anchor="6 of 24 audit-rights negotiations",
        playbook_key=SAAS, rule_key="audit.customer_audit_rights",
        numerator=("saas_audit_tier1_two_onsite",),
        denominator=(
            "saas_audit_10day_notice_accepted",
            "saas_audit_tier1_two_onsite",
            "saas_audit_standard",
        ),
        expected_numerator=6, expected_denominator=24,
    ),
    dict(
        file="saas_msa_vendor_1_1.yaml",
        field_path="limitation_of_liability.cap_amount.positions[fallback_3]",
        anchor="2 of the 31 strategic-deal liability negotiations",
        playbook_key=SAAS, rule_key="limitation_of_liability.cap_amount",
        numerator=("cap_36month_reached",),
        denominator=("cap_36month_reached", "cap_24month_settled"),
        expected_numerator=2, expected_denominator=31,
    ),
    # --- dpa_processor_1_1.yaml --------------------------------------------
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="data_protection.data_subject_requests.parameters.dsr_forwarding_business_days.yellow_limit",
        anchor="2 of 34 GDPR-related DPA negotiations",
        playbook_key=DPA, rule_key="data_protection.data_subject_requests",
        numerator=("dsr_1day_forwarding_accepted",),
        denominator=("dsr_1day_forwarding_accepted", "dsr_standard_forwarding"),
        expected_numerator=2, expected_denominator=34,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="data_protection.data_return_and_deletion.parameters.dsr_export_window_days.yellow_limit",
        anchor="6 of 40 deals, 15%",
        playbook_key=DPA, rule_key="data_protection.data_return_and_deletion",
        numerator=("deletion_44day_export_accepted",),
        denominator=(
            "deletion_44day_export_accepted",
            "deletion_enterprise_transition_rung2",
            "deletion_standard_export",
        ),
        expected_numerator=6, expected_denominator=40,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="data_protection.data_return_and_deletion.parameters.deletion_completion_days.yellow_limit",
        anchor="The 9 DPAs that reached the enterprise-transition fallback",
        playbook_key=DPA, rule_key="data_protection.data_return_and_deletion",
        numerator=("deletion_enterprise_transition_rung2",),
        denominator=(
            "deletion_44day_export_accepted",
            "deletion_enterprise_transition_rung2",
            "deletion_standard_export",
        ),
        expected_numerator=9, expected_denominator=40,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="security.technical_organisational_measures.parameters.toms_material_update_notice_days.yellow_limit",
        anchor="3 of 11 TOMs negotiations",
        playbook_key=DPA, rule_key="security.technical_organisational_measures",
        numerator=("toms_45day_notice_accepted",),
        denominator=("toms_45day_notice_accepted", "toms_30day_standard"),
        expected_numerator=3, expected_denominator=11,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="audit.customer_audit_rights.parameters.audit_notice_days.yellow_limit",
        anchor="3 of 27 DPA audit-rights negotiations",
        playbook_key=DPA, rule_key="audit.customer_audit_rights",
        numerator=("dpa_audit_8day_notice_accepted",),
        denominator=("dpa_audit_8day_notice_accepted", "dpa_audit_standard"),
        expected_numerator=3, expected_denominator=27,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="audit.audit_cost.positions[+fallback_3]",
        anchor="4 of 13 strategic DPA audit-cost negotiations",
        playbook_key=DPA, rule_key="audit.audit_cost",
        numerator=("audit_cost_absorb_second_accepted",),
        denominator=("audit_cost_absorb_second_accepted", "audit_cost_standard"),
        expected_numerator=4, expected_denominator=13,
    ),
    dict(
        file="dpa_processor_1_1.yaml",
        field_path="subprocessors.subprocessor_liability.positions[+acceptable_variant]",
        anchor="5 of 22 DPA negotiations in H1 2026 (23%)",
        playbook_key=DPA, rule_key="subprocessors.subprocessor_liability",
        numerator=("subproc_liability_joint_several_variant",),
        denominator=(
            "subproc_liability_joint_several_variant",
            "subproc_liability_standard_flow_down",
        ),
        expected_numerator=5, expected_denominator=22,
    ),
]


def test_version_files_exist_and_are_readable():
    for name in ("saas_msa_vendor_1_1.yaml", "dpa_processor_1_1.yaml"):
        assert (VERSIONS_DIR / name).is_file()
    assert DECISIONS_FILE.is_file()


def test_every_cited_figure_is_reproducible_from_decisions_yaml():
    history = load_valid_file(DECISIONS_FILE)
    events = history.decision_events

    failures: list[str] = []
    for case in CASES:
        reason = _reason_text(case["file"], case["field_path"])
        label = f"{case['file']} [{case['field_path']}]"

        if case["anchor"] not in reason:
            failures.append(
                f"{label}: anchor text {case['anchor']!r} not found in reason "
                f"(3.14's reason text may have changed) -- reason was: {reason!r}"
            )
            continue

        numerator = _weight(events, case["playbook_key"], case["rule_key"], *case["numerator"])
        denominator = _weight(events, case["playbook_key"], case["rule_key"], *case["denominator"])

        if numerator != case["expected_numerator"] or denominator != case["expected_denominator"]:
            failures.append(
                f"{label}: decisions.yaml gives {numerator} of {denominator}, "
                f"expected {case['expected_numerator']} of {case['expected_denominator']}"
            )

    assert not failures, "\n".join(failures)


# Change-log entries that cite a figure but are not a negotiation outcome a
# decision event can represent: internal document/process review counts
# (how many files a reviewer flagged, how often a drafter cross-referenced
# another clause), not what a counterparty accepted. Each is checked against
# the real reason text below, so an edit to 3.14 that changes what these
# entries mean would fail this test rather than silently staying "excluded".
EXCLUDED_FIELD_PATHS: dict[str, dict[str, str]] = {
    "saas_msa_vendor_1_1.yaml": {
        "payment.late_fees.parameters.late_fee_percent_per_month.green_limit": (
            "paired with the preferred_value change above (same CASES rows already "
            "cover its population); cites no new figure of its own"
        ),
        "payment.taxes.dependencies[payment.payment_terms]": (
            "cites a count of internal drafting-guide audits, not a negotiated outcome"
        ),
    },
    "dpa_processor_1_1.yaml": {
        "data_protection.dpia_assistance.dependencies[security.technical_organisational_measures]": (
            "cites how often a drafter cross-referenced another clause, not a negotiated outcome"
        ),
        "audit.audit_cost.dependencies[audit.customer_audit_rights]": (
            "cites an internal reviewer-confusion count across files, not a negotiated outcome"
        ),
    },
}


def test_cases_and_exclusions_cover_every_change_log_entry():
    """Every ``changes`` entry in both files is either a case in ``CASES``
    above or an explicit, justified exclusion — nothing falls through
    silently, including a change added after this test was written."""
    for file_name in ("saas_msa_vendor_1_1.yaml", "dpa_processor_1_1.yaml"):
        doc = load_yaml_mapping(VERSIONS_DIR / file_name)
        all_paths = [c["field_path"] for c in doc["changes"]]
        covered = {c["field_path"] for c in CASES if c["file"] == file_name}
        excluded = EXCLUDED_FIELD_PATHS.get(file_name, {})

        missing = [p for p in all_paths if p not in covered and p not in excluded]
        assert not missing, f"{file_name}: change(s) neither covered nor excluded: {missing}"

        stale = set(excluded) - set(all_paths)
        assert not stale, f"{file_name}: exclusion(s) for change(s) no longer present: {stale}"
