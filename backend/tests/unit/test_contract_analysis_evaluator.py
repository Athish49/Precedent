"""Tests for the zone evaluator (task 4.3; ``playbook_plan.md`` section 5.2).

Covers ``zone_for_parameter`` (direction handling, context_overrides, and
boundary values at the green/yellow/red edges) and ``evaluate_finding``
(the five-step ladder, in priority order).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.contract_analysis.evaluator import (
    ExtractedClause,
    evaluate_finding,
    zone_for_parameter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parameter(
    key: str = "cap_multiple_months",
    direction: str = "lower_is_better",
    preferred_value=12,
    green_limit=12,
    yellow_limit=24,
    allowed_values=None,
    context_overrides=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_id=uuid.uuid4(),
        key=key,
        label=key.replace("_", " "),
        value_type="number",
        unit=None,
        direction=direction,
        preferred_value=preferred_value,
        green_limit=green_limit,
        yellow_limit=yellow_limit,
        allowed_values=allowed_values,
        extraction_hint=None,
        context_overrides=context_overrides,
    )


def _position(
    kind: str, zone: str = "green", rung: int | None = None, label: str = "Position"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_id=uuid.uuid4(),
        kind=kind,
        rung=rung,
        label=label,
        language="...",
        summary=None,
        zone=zone,
        approver_role_id=None,
        conditions=None,
        give_get=None,
        internal_note=None,
    )


def _red_line(
    key: str = "rl-1",
    description: str = "A red line",
    condition_type: str = "phrase",
    condition: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        scope="rule",
        rule_id=uuid.uuid4(),
        playbook_id=None,
        key=key,
        description=description,
        condition_type=condition_type,
        condition=condition if condition is not None else {},
        action="block",
        approver_role_id=None,
        rationale=None,
    )


def _rule(parameters=None, default_zone="red") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        playbook_version_id=uuid.uuid4(),
        clause_type="limitation_of_liability",
        issue_id=None,
        rule_key="limitation_of_liability.cap_amount",
        title="Liability cap",
        position_summary=None,
        risk_rationale=None,
        required=True,
        negotiable=True,
        risk_weight=8.0,
        default_zone=default_zone,
        needs_human_judgment=False,
        judgment_note=None,
        applies_when=None,
        detection_guidance=None,
        source_ref=None,
        authored_by=None,
        approved_by=None,
        last_reviewed_at=None,
        positions=[],
        parameters=parameters or [],
        red_lines=[],
        objections=[],
        dependencies=[],
        test_cases=[],
        source_playbook_id=uuid.uuid4(),
        source_playbook_name="Halcyon Baseline",
        source_version="1.0",
    )


# ---------------------------------------------------------------------------
# zone_for_parameter — lower_is_better boundaries
# (preferred_value=12, green_limit=12, yellow_limit=24; smaller is safer)
# ---------------------------------------------------------------------------


def test_lower_is_better_at_green_limit_is_green() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 12) == "green"


def test_lower_is_better_just_inside_green_limit_is_green() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 11) == "green"


def test_lower_is_better_just_outside_green_limit_is_yellow() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 13) == "yellow"


def test_lower_is_better_at_yellow_limit_is_yellow() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 24) == "yellow"


def test_lower_is_better_just_inside_yellow_limit_is_yellow() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 23) == "yellow"


def test_lower_is_better_just_outside_yellow_limit_is_red() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 25) == "red"


def test_lower_is_better_far_beyond_yellow_limit_is_red() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    assert zone_for_parameter(param, 999) == "red"


# ---------------------------------------------------------------------------
# zone_for_parameter — higher_is_better boundaries
# (e.g. uptime: green_limit=99.9, yellow_limit=99.5; bigger is safer)
# ---------------------------------------------------------------------------


def test_higher_is_better_at_green_limit_is_green() -> None:
    param = _parameter(direction="higher_is_better", green_limit=99.9, yellow_limit=99.5)
    assert zone_for_parameter(param, 99.9) == "green"


def test_higher_is_better_just_inside_green_limit_is_green() -> None:
    param = _parameter(direction="higher_is_better", green_limit=99.9, yellow_limit=99.5)
    assert zone_for_parameter(param, 99.95) == "green"


def test_higher_is_better_just_outside_green_limit_is_yellow() -> None:
    param = _parameter(direction="higher_is_better", green_limit=99.9, yellow_limit=99.5)
    assert zone_for_parameter(param, 99.89) == "yellow"


def test_higher_is_better_at_yellow_limit_is_yellow() -> None:
    param = _parameter(direction="higher_is_better", green_limit=99.9, yellow_limit=99.5)
    assert zone_for_parameter(param, 99.5) == "yellow"


def test_higher_is_better_just_outside_yellow_limit_is_red() -> None:
    param = _parameter(direction="higher_is_better", green_limit=99.9, yellow_limit=99.5)
    assert zone_for_parameter(param, 99.49) == "red"


# ---------------------------------------------------------------------------
# zone_for_parameter — set_membership and exact
# ---------------------------------------------------------------------------


def test_set_membership_in_green_list_is_green() -> None:
    param = _parameter(
        direction="set_membership",
        green_limit=["delaware", "new_york"],
        yellow_limit=["other_us_state"],
    )
    assert zone_for_parameter(param, "delaware") == "green"


def test_set_membership_in_yellow_list_is_yellow() -> None:
    param = _parameter(
        direction="set_membership",
        green_limit=["delaware", "new_york"],
        yellow_limit=["other_us_state"],
    )
    assert zone_for_parameter(param, "other_us_state") == "yellow"


def test_set_membership_outside_both_lists_is_red() -> None:
    param = _parameter(
        direction="set_membership",
        green_limit=["delaware", "new_york"],
        yellow_limit=["other_us_state"],
    )
    assert zone_for_parameter(param, "cayman_islands") == "red"


def _exact_parameter() -> SimpleNamespace:
    return _parameter(
        direction="exact", preferred_value="net_30", green_limit="net_30", yellow_limit="net_45"
    )


def test_exact_matching_green_target_is_green() -> None:
    param = _exact_parameter()
    assert zone_for_parameter(param, "net_30") == "green"


def test_exact_matching_yellow_target_is_yellow() -> None:
    param = _exact_parameter()
    assert zone_for_parameter(param, "net_45") == "yellow"


def test_exact_mismatch_is_red() -> None:
    param = _exact_parameter()
    assert zone_for_parameter(param, "net_90") == "red"


# ---------------------------------------------------------------------------
# zone_for_parameter — missing / unknown input fails safe
# ---------------------------------------------------------------------------


def test_none_value_is_red() -> None:
    param = _parameter()
    assert zone_for_parameter(param, None) == "red"


def test_unknown_direction_fails_safe_to_red() -> None:
    param = _parameter(direction="not_a_real_direction")
    assert zone_for_parameter(param, 1) == "red"


def test_no_green_limit_set_has_no_green_zone() -> None:
    """A parameter with only a yellow_limit has no reachable green rung."""
    param = _parameter(direction="lower_is_better", green_limit=None, yellow_limit=24)
    assert zone_for_parameter(param, 1) == "yellow"
    assert zone_for_parameter(param, 25) == "red"


# ---------------------------------------------------------------------------
# zone_for_parameter — context_overrides
# ---------------------------------------------------------------------------


def test_context_override_raises_yellow_limit_for_strategic_deals() -> None:
    """playbook_plan.md 2.4: strategic deals may go up to 36 months of Fees."""
    param = _parameter(
        direction="lower_is_better",
        green_limit=12,
        yellow_limit=24,
        context_overrides=[{"when": {"deal_value_band": ["strategic"]}, "yellow_limit": 36}],
    )
    # Without the override, 30 would be red.
    assert zone_for_parameter(param, 30, context={"deal_value_band": "standard"}) == "red"
    # With the override matching, the same value is yellow.
    assert zone_for_parameter(param, 30, context={"deal_value_band": "strategic"}) == "yellow"


def test_context_override_not_applied_when_condition_does_not_match() -> None:
    param = _parameter(
        direction="lower_is_better",
        green_limit=12,
        yellow_limit=24,
        context_overrides=[{"when": {"deal_value_band": ["strategic"]}, "yellow_limit": 36}],
    )
    assert zone_for_parameter(param, 30, context={"deal_value_band": "mid"}) == "red"


def test_later_matching_override_wins_on_conflicting_field() -> None:
    param = _parameter(
        direction="lower_is_better",
        green_limit=12,
        yellow_limit=24,
        context_overrides=[
            {"when": {"deal_value_band": ["strategic"]}, "yellow_limit": 30},
            {"when": {"deal_value_band": ["strategic"]}, "yellow_limit": 36},
        ],
    )
    assert zone_for_parameter(param, 32, context={"deal_value_band": "strategic"}) == "yellow"


# ---------------------------------------------------------------------------
# evaluate_finding — the five-step ladder
# ---------------------------------------------------------------------------


def test_red_line_match_wins_regardless_of_everything_else() -> None:
    """Step 1 short-circuits even when a position would otherwise be green."""
    red_line = _red_line("lol-uncapped")
    position = _position("preferred", zone="green")
    rule = _rule()
    extracted = ExtractedClause(matched_red_lines=[red_line], matched_position=position)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.red_line is red_line


def test_parameter_beyond_yellow_limit_is_red() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(parameter_values={"cap_multiple_months": 30})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.parameter_key == "cap_multiple_months"
    assert result.parameter_value == 30


def test_parameter_beyond_green_limit_is_yellow() -> None:
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(parameter_values={"cap_multiple_months": 18})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.parameter_key == "cap_multiple_months"


def test_preferred_position_match_is_no_finding() -> None:
    """Section 5.2 step 3: a preferred-position match is "no finding", not
    a green finding — layer2_content.py treats zone == "none" as nothing to
    flag."""
    position = _position("preferred", zone="green", label="Preferred cap")
    rule = _rule()
    extracted = ExtractedClause(matched_position=position)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "none"
    assert result.position is position
    assert result.position_id == position.id


def test_acceptable_variant_match_is_no_finding() -> None:
    position = _position("acceptable_variant", zone="green", label="Variant cap")
    rule = _rule()
    extracted = ExtractedClause(matched_position=position)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "none"


def test_fallback_rung_match_uses_the_rungs_own_zone() -> None:
    position = _position("fallback", zone="yellow", rung=1, label="Fallback 1")
    rule = _rule()
    extracted = ExtractedClause(matched_position=position)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.position is position


def test_no_match_at_all_falls_back_to_rule_default_zone() -> None:
    rule = _rule(default_zone="yellow")
    extracted = ExtractedClause()
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.position is None
    assert result.red_line is None


def test_no_match_and_no_default_zone_fails_safe_to_red() -> None:
    rule = _rule(default_zone=None)
    extracted = ExtractedClause()
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"


def test_evaluate_finding_accepts_layer2_dict_shape() -> None:
    """``evaluate_finding`` also accepts the plain-dict extraction shape
    ``layer2_content.py`` builds from ``RuleExtractionOut`` — a position
    identified by its label and red lines identified by their key, not by
    id — resolving both against the rule's own children."""
    position = _position("fallback", zone="yellow", rung=1, label="Fallback 1")
    rule = _rule()
    rule.positions = [position]
    payload = {
        "position": {"match_kind": "fallback", "position_label": "Fallback 1", "quote": "..."},
        "parameters": {},
        "red_lines": {},
    }
    result = evaluate_finding(rule, payload)
    assert result.zone == "yellow"
    assert result.position_id == position.id


def test_evaluate_finding_dict_shape_resolves_triggered_red_line() -> None:
    red_line = _red_line("lol-uncapped", "Liability is uncapped.")
    rule = _rule()
    rule.red_lines = [red_line]
    payload = {
        "position": {"match_kind": "none"},
        "parameters": {},
        "red_lines": {"lol-uncapped": {"triggered": True, "quote": "uncapped"}},
    }
    result = evaluate_finding(rule, payload)
    assert result.zone == "red"
    assert result.red_line_id == red_line.id


def test_parameter_step_beats_position_step() -> None:
    """A red parameter wins over a green-looking matched *preferred* position
    (step 2 before step 3) -- and, per the module docstring's "Combining
    step 2 and steps 3/4" section, a preferred/acceptable-variant match is
    deliberately dropped from the result entirely rather than merged, so it
    can never make a real parameter breach vanish downstream (see
    ``layer2_content._extraction_to_flag``'s preferred/acceptable_variant
    suppression)."""
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    position = _position("preferred", zone="green")
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(
        parameter_values={"cap_multiple_months": 40}, matched_position=position
    )
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.parameter_key == "cap_multiple_months"
    assert result.position is None
    assert result.position_id is None


# ---------------------------------------------------------------------------
# evaluate_finding -- reconciling a parameter breach with a matched
# *fallback* position on the same clause (the pilot-found bug: step 2 used
# to win outright and silently drop the position/rung information).
# ---------------------------------------------------------------------------


def test_parameter_and_fallback_position_agree_cleanly() -> None:
    """Parameter independently lands on yellow, and the matched fallback
    rung is also labelled yellow -- the position/rung must survive in the
    result (this is exactly what the rule-test runner needs to report
    ``expected_outcome: "fallback"`` / ``expected_position_rung`` instead of
    a generic ``deviation``), and the zone is the (agreeing) yellow."""
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    position = _position("fallback", zone="yellow", rung=1, label="Fallback 1")
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(
        parameter_values={"cap_multiple_months": 18}, matched_position=position
    )
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.position is position
    assert result.position_id == position.id
    assert result.parameter_key == "cap_multiple_months"
    assert result.parameter_value == 18


def test_parameter_worse_than_fallback_position_surfaces_the_worse_zone() -> None:
    """The matched fallback rung is labelled green, but the raw parameter
    value is actually beyond the yellow limit (red) -- the position/rung
    must still be reported (it was correctly identified), but the zone must
    be the worse of the two (red), not silently improved on by the
    fallback's own green label."""
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    position = _position("fallback", zone="green", rung=2, label="Fallback 2")
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(
        parameter_values={"cap_multiple_months": 999}, matched_position=position
    )
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.position is position
    assert result.position_id == position.id
    assert result.parameter_key == "cap_multiple_months"
    assert result.parameter_value == 999


def test_parameter_only_unaffected_when_no_position_matches_at_all() -> None:
    """No position matched on this clause at all -- the parameter result is
    returned exactly as before, nothing to reconcile."""
    param = _parameter(direction="lower_is_better", green_limit=12, yellow_limit=24)
    rule = _rule(parameters=[param])
    extracted = ExtractedClause(parameter_values={"cap_multiple_months": 18})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.parameter_key == "cap_multiple_months"
    assert result.position is None
    assert result.position_id is None


def test_fallback_position_only_unaffected_when_rule_has_no_parameters() -> None:
    """No parameter on this rule matched (or exists) at all -- the fallback
    position's own zone decides exactly as before, nothing to reconcile."""
    position = _position("fallback", zone="yellow", rung=1, label="Fallback 1")
    rule = _rule(parameters=[])
    extracted = ExtractedClause(matched_position=position)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.position is position
    assert result.parameter_key is None


# ---------------------------------------------------------------------------
# evaluate_finding -- parameter-type red lines (condition_type: "parameter").
#
# Neither Layer 1 (phrase/regex only) nor Layer 2 (semantic only) ever
# evaluates these upstream, so evaluate_finding derives matches for them
# itself, right before step 1, from rule.red_lines + extracted.parameter_
# values -- see seed/playbooks/data/halcyon/playbooks/mutual_nda/rules.yaml's
# "ci-named-schedule-only" (op: eq) and vendor_msa_customer/risk.yaml's
# "breach-notice-over-120-hours" (op: gt).
# ---------------------------------------------------------------------------


def test_parameter_red_line_matches_via_eq() -> None:
    red_line = _red_line(
        "ci-named-schedule-only",
        "Confidential Information is limited to a named schedule.",
        condition_type="parameter",
        condition={"parameter_key": "ci_scope_standard", "op": "eq", "value": "named_schedule_only"},
    )
    rule = _rule()
    rule.red_lines = [red_line]
    extracted = ExtractedClause(parameter_values={"ci_scope_standard": "named_schedule_only"})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.red_line_id == red_line.id
    assert result.red_line is red_line


def test_parameter_red_line_matches_via_gt() -> None:
    red_line = _red_line(
        "breach-notice-over-120-hours",
        "Vendor's notice period is longer than 120 hours from discovery.",
        condition_type="parameter",
        condition={"parameter_key": "breach_notice_hours", "op": "gt", "value": 120},
    )
    rule = _rule()
    rule.red_lines = [red_line]
    extracted = ExtractedClause(parameter_values={"breach_notice_hours": 168})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.red_line_id == red_line.id
    assert result.red_line is red_line


def test_parameter_red_line_does_not_match_under_threshold() -> None:
    """A present value that simply doesn't satisfy the condition falls
    through to the rest of the ladder normally (here: no parameter
    declared with limits, no position -> step 5's default deviation)."""
    red_line = _red_line(
        "breach-notice-over-120-hours",
        "Vendor's notice period is longer than 120 hours from discovery.",
        condition_type="parameter",
        condition={"parameter_key": "breach_notice_hours", "op": "gt", "value": 120},
    )
    rule = _rule(default_zone="yellow")
    rule.red_lines = [red_line]
    extracted = ExtractedClause(parameter_values={"breach_notice_hours": 72})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.red_line_id is None
    assert result.red_line is None


def test_parameter_red_line_does_not_match_when_key_absent() -> None:
    """The parameter key is simply absent from extracted.parameter_values
    (e.g. this clause/finding belongs to a different rule in the same
    family) -- this must not be treated as a fail-safe match, unlike
    zone_for_parameter's "missing value fails safe to red" behaviour."""
    red_line = _red_line(
        "ci-named-schedule-only",
        "Confidential Information is limited to a named schedule.",
        condition_type="parameter",
        condition={"parameter_key": "ci_scope_standard", "op": "eq", "value": "named_schedule_only"},
    )
    rule = _rule(default_zone="yellow")
    rule.red_lines = [red_line]
    extracted = ExtractedClause(parameter_values={})
    result = evaluate_finding(rule, extracted)
    assert result.zone == "yellow"
    assert result.red_line_id is None
    assert result.red_line is None


def test_parameter_red_line_merges_with_existing_matched_red_lines() -> None:
    """A derived parameter-type match is appended to, not a replacement
    for, red lines Layer 1/Layer 2 already populated."""
    phrase_red_line = _red_line("rl-phrase", "Phrase-matched red line.")
    parameter_red_line = _red_line(
        "ci-named-schedule-only",
        "Confidential Information is limited to a named schedule.",
        condition_type="parameter",
        condition={"parameter_key": "ci_scope_standard", "op": "eq", "value": "named_schedule_only"},
    )
    rule = _rule()
    rule.red_lines = [parameter_red_line]
    extracted = ExtractedClause(
        matched_red_lines=[phrase_red_line],
        parameter_values={"ci_scope_standard": "named_schedule_only"},
    )
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    # Step 1 picks the first entry; the derived match is appended after it.
    assert result.red_line_id == phrase_red_line.id


# ---------------------------------------------------------------------------
# Presence ops: is_absent / is_present (playbook_plan.md section 3.7's
# canonical example), plus not_in. Seed: dpa_processor's
# "toms-no-description" / "changes-no-notice-or-objection" /
# "pers-no-confidentiality-duty" and hipaa_overlay's
# "regulatory-penalty-indemnity-uncapped" all use op: is_absent.
# ---------------------------------------------------------------------------


def _presence_rule(op: str, key: str = "subprocessor_change_notice_days"):
    red_line = _red_line(
        "changes-no-notice-or-objection",
        "No notice of sub-processor changes.",
        condition_type="parameter",
        condition={"parameter_key": key, "op": op},
    )
    rule = _rule(
        parameters=[_parameter(key="subprocessor_change_notice_days")], default_zone="yellow"
    )
    rule.red_lines = [red_line]
    return rule, red_line


def test_is_absent_fires_when_declared_parameter_not_extracted() -> None:
    rule, red_line = _presence_rule("is_absent")
    fallback = _position("fallback", zone="yellow", rung=1)
    extracted = ExtractedClause(parameter_values={}, matched_position=fallback)
    result = evaluate_finding(rule, extracted)
    assert result.zone == "red"
    assert result.red_line_id == red_line.id
    assert result.red_line is red_line


def test_is_absent_does_not_fire_when_parameter_was_extracted() -> None:
    rule, _red = _presence_rule("is_absent")
    extracted = ExtractedClause(parameter_values={"subprocessor_change_notice_days": 10})
    result = evaluate_finding(rule, extracted)
    assert result.red_line_id is None
    assert result.zone != "red"


def test_is_absent_does_not_fire_on_completely_empty_extraction() -> None:
    """Nothing extracted at all (no position, parameter or red line) means the
    clause does not engage with this rule (or, in playbook/testing.py's
    missing-clause simulation, the family is absent): the missing check owns
    that, so the red line must not fire. The seed's `missing` test cases for
    rules with is_absent red lines expect a yellow deviation."""
    rule, _red = _presence_rule("is_absent")
    result = evaluate_finding(rule, ExtractedClause())
    assert result.red_line_id is None
    assert result.zone == "yellow"


def test_is_absent_does_not_fire_for_parameter_the_rule_does_not_declare() -> None:
    rule, _red = _presence_rule("is_absent", key="not_a_rule_parameter")
    extracted = ExtractedClause(matched_position=_position("fallback", zone="yellow", rung=1))
    result = evaluate_finding(rule, extracted)
    assert result.red_line_id is None


def test_is_absent_via_layer2_dict_shape() -> None:
    rule, red_line = _presence_rule("is_absent")
    fallback = _position("fallback", zone="yellow", rung=1, label="Fallback 1")
    rule.positions = [fallback]
    payload = {
        "position": {"match_kind": "fallback", "position_label": "Fallback 1", "quote": "x"},
        "parameters": {},
        "red_lines": {},
    }
    result = evaluate_finding(rule, payload)
    assert result.red_line_id == red_line.id


def test_is_present_fires_only_when_parameter_extracted() -> None:
    rule, red_line = _presence_rule("is_present")
    hit = evaluate_finding(
        rule, ExtractedClause(parameter_values={"subprocessor_change_notice_days": 10})
    )
    assert hit.red_line_id == red_line.id
    miss = evaluate_finding(
        rule, ExtractedClause(matched_position=_position("fallback", zone="yellow", rung=1))
    )
    assert miss.red_line_id is None


def test_not_in_parameter_red_line() -> None:
    red_line = _red_line(
        "law-not-approved",
        "Governing law outside the approved list.",
        condition_type="parameter",
        condition={"parameter_key": "law", "op": "not_in", "value": ["delaware", "ireland"]},
    )
    rule = _rule(default_zone="yellow")
    rule.red_lines = [red_line]
    assert evaluate_finding(
        rule, ExtractedClause(parameter_values={"law": "ontario"})
    ).red_line_id == red_line.id
    assert evaluate_finding(
        rule, ExtractedClause(parameter_values={"law": "ireland"})
    ).red_line_id is None
