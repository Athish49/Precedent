"""Tests for S2 Layer 2 LLM content analysis (T-042; rewritten by task 4.4)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.core.llm.schemas.analysis import (
    ClauseAnalysisItem,
    ClauseFlagOut,
    ContractAnalysisOut,
    ExtractedParameterOut,
    ExtractedPositionOut,
    RuleExtractionOut,
    SemanticRedLineOut,
)
from app.services.contract_analysis.layer2_content import (
    _find_inconsistency_candidates,
    _rule_block,
    run_layer2,
)
from app.services.contract_analysis.models import ClauseRuleMatch
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clause(
    clause_type: str,
    text: str = "Standard clause text.",
    char_start: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        clause_type=clause_type,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def _position(
    kind: str = "preferred",
    label: str = "Preferred",
    rung: int | None = None,
    summary: str | None = "Standard position.",
    language: str = "Preferred language.",
    zone: str = "green",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), kind=kind, rung=rung, label=label, summary=summary,
        language=language, zone=zone,
    )


def _parameter(
    key: str = "cap_multiple_months",
    label: str = "Cap (months of Fees)",
    unit: str | None = "months",
    extraction_hint: str | None = "Number of months of Fees the cap is set to.",
    value_type: str = "number",
    direction: str = "lower_is_better",
    green_limit: object = 12,
    yellow_limit: object = 24,
    allowed_values: list | None = None,
    preferred_value: object = 12,
    context_overrides: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key, label=label, unit=unit, extraction_hint=extraction_hint,
        value_type=value_type, direction=direction, green_limit=green_limit,
        yellow_limit=yellow_limit, allowed_values=allowed_values,
        preferred_value=preferred_value, context_overrides=context_overrides,
    )


def _red_line(
    key: str = "uncapped_liability",
    description: str = "Liability is uncapped for any category other than the carve-outs.",
    condition_type: str = "semantic",
    test: str | None = None,
) -> SimpleNamespace:
    condition = {"test": test} if test else {}
    return SimpleNamespace(
        id=uuid.uuid4(), key=key, description=description,
        condition_type=condition_type, condition=condition,
    )


def _rule(
    clause_type: str,
    rule_key: str | None = None,
    title: str | None = "Liability cap",
    positions: list | None = None,
    parameters: list | None = None,
    red_lines: list | None = None,
    default_zone: str = "red",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        clause_type=clause_type,
        rule_key=rule_key or f"{clause_type}.issue",
        title=title,
        position_summary="Cap Halcyon's liability at 12 months of Fees.",
        detection_guidance="Look for a dollar or multiple-of-fees cap.",
        positions=positions if positions is not None else [_position()],
        parameters=parameters if parameters is not None else [],
        red_lines=red_lines if red_lines is not None else [],
        default_zone=default_zone,
    )


def _match(clause, rules: list | None = None) -> ClauseRuleMatch:
    return ClauseRuleMatch(clause=clause, rules=rules or [])


def _fake_result(*items: ClauseAnalysisItem) -> ContractAnalysisOut:
    return ContractAnalysisOut(items=list(items))


def _item(
    clause_id: uuid.UUID,
    *flags: ClauseFlagOut,
    rule_extractions: list[RuleExtractionOut] | None = None,
) -> ClauseAnalysisItem:
    return ClauseAnalysisItem(
        clause_id=str(clause_id), flags=list(flags), rule_extractions=rule_extractions or []
    )


def _flag(
    flag_type: str,
    severity: str = "medium",
    detail: str = "test detail",
    quote: str | None = None,
) -> ClauseFlagOut:
    return ClauseFlagOut(
        flag_type=flag_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        detail=detail,
        offending_quote=quote,
    )


def _extraction(
    rule_key: str,
    match_kind: str = "preferred",
    position_label: str | None = "Preferred",
    position_quote: str | None = None,
    parameters: list[ExtractedParameterOut] | None = None,
    red_lines: list[SemanticRedLineOut] | None = None,
) -> RuleExtractionOut:
    return RuleExtractionOut(
        rule_key=rule_key,
        position=ExtractedPositionOut(
            match_kind=match_kind,  # type: ignore[arg-type]
            position_label=position_label,
            quote=position_quote,
        ),
        parameters=parameters or [],
        red_lines=red_lines or [],
    )


# ---------------------------------------------------------------------------
# run_layer2 — basic routing
# ---------------------------------------------------------------------------


def test_empty_matches_returns_no_flags() -> None:
    contract_id = uuid.uuid4()
    flags = run_layer2(contract_id, "own", [])
    assert flags == []


def test_empty_matches_counterparty_returns_no_flags() -> None:
    contract_id = uuid.uuid4()
    flags = run_layer2(contract_id, "counterparty", [])
    assert flags == []


# ---------------------------------------------------------------------------
# Free-standing flags (high_risk / vague / inconsistent) — unchanged by 4.4
# ---------------------------------------------------------------------------


def test_own_paper_high_risk_and_vague_flags() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("limitation_of_liability", "Party A has unlimited liability for all losses.")
    m = _match(clause, [_rule("limitation_of_liability")])

    fake_item = _item(
        clause.id,
        _flag("high_risk", "high", "Unlimited liability."),
        _flag("vague", "low", "All losses is undefined."),
    )
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 2
    types = {f.flag_type for f in flags}
    assert types == {"high_risk", "vague"}
    assert all(f.source == "llm" and f.zone is None for f in flags)


def test_own_paper_no_flags_returns_empty() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("governing_law", "This agreement is governed by Delaware law.")
    m = _match(clause, [_rule("governing_law")])

    fake_item = _item(clause.id)  # no flags, no extractions
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags == []


def test_own_paper_calls_gateway_once() -> None:
    contract_id = uuid.uuid4()
    clauses = [
        _match(_clause("indemnification"), [_rule("indemnification")]),
        _match(_clause("termination"), [_rule("termination")]),
        _match(_clause("governing_law"), [_rule("governing_law")]),
    ]
    fake_items = [_item(m.clause.id) for m in clauses]
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(*fake_items)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "own", clauses)

    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "call_structured"
    assert fake.calls[0]["task"] == "clause_analysis"


def test_own_paper_inconsistent_flag_included() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("confidentiality", "All Confidential Information must be protected.")
    m = _match(clause, [_rule("confidentiality")])

    fake_item = _item(clause.id, _flag("inconsistent", "medium", "Term used inconsistently."))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert any(f.flag_type == "inconsistent" for f in flags)


def test_counterparty_ungoverned_clause_can_have_flags() -> None:
    """Clauses with rules=[] must still produce flags on the counterparty path."""
    contract_id = uuid.uuid4()
    clause = _clause("payment", "Client waives all rights to dispute invoices.")
    m = _match(clause, rules=[])  # ungoverned

    fake_item = _item(clause.id, _flag("high_risk", "high", "Waiver of invoice dispute rights."))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])

    assert len(flags) == 1
    assert flags[0].flag_type == "high_risk"
    assert flags[0].matched_rule_id is None


def test_counterparty_ungoverned_clause_included_in_prompt() -> None:
    """Ungoverned clauses appear in the counterparty prompt (not silently dropped)."""
    contract_id = uuid.uuid4()
    governed = _match(_clause("indemnification"), [_rule("indemnification")])
    ungoverned = _match(_clause("payment", "Client waives all rights."), rules=[])

    captured_messages: list[list[dict]] = []

    class CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_messages.append(messages)
            items = [_item(governed.clause.id), _item(ungoverned.clause.id)]
            return _fake_result(*items)

    fake = CapturingFake()

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "counterparty", [governed, ungoverned])

    assert captured_messages
    msgs = captured_messages[0]
    user_msg = next(m["content"] for m in msgs if m.get("role") == "user")
    assert str(ungoverned.clause.id) in user_msg
    assert "payment" in user_msg
    assert "ungoverned" in user_msg


def test_governed_clause_prompt_includes_rule_family_detail() -> None:
    """The prompt for a governed clause carries every rule in its family, with
    title, positions (labels), parameters (hints) and semantic red lines."""
    contract_id = uuid.uuid4()
    cap_rule = _rule(
        "limitation_of_liability",
        "limitation_of_liability.cap_amount",
        title="Liability cap amount",
        positions=[
            _position("preferred", "Preferred: 12-month cap"),
            _position("fallback", "Fallback 1: 18-month cap", rung=1),
        ],
        parameters=[_parameter("cap_multiple_months")],
    )
    carveouts_rule = _rule(
        "limitation_of_liability",
        "limitation_of_liability.cap_carve_outs",
        title="Liability cap carve-outs",
        red_lines=[
            _red_line(
                "uncapped_data_breach",
                test="The clause leaves data breach liability uncapped.",
            )
        ],
    )
    clause = _clause(
        "limitation_of_liability", "Halcyon's liability is capped at 18 months of Fees."
    )
    m = _match(clause, [cap_rule, carveouts_rule])

    captured_messages: list[list[dict]] = []

    class CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_messages.append(messages)
            return _fake_result(_item(clause.id))

    fake = CapturingFake()
    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "own", [m])

    user_msg = next(m["content"] for m in captured_messages[0] if m.get("role") == "user")
    assert "limitation_of_liability.cap_amount" in user_msg
    assert "limitation_of_liability.cap_carve_outs" in user_msg
    assert "Liability cap amount" in user_msg
    assert "Fallback 1: 18-month cap" in user_msg
    assert "cap_multiple_months" in user_msg
    assert "The clause leaves data breach liability uncapped." in user_msg


# ---------------------------------------------------------------------------
# Counterparty path — deviation via rule_extractions (not model-assigned)
# ---------------------------------------------------------------------------


def test_unrecognized_rule_key_in_extraction_is_ignored() -> None:
    """A rule_key the model echoes that wasn't offered for this clause (or any
    clause) must not be mistaken for a real rule."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification")
    m = _match(clause, [_rule("indemnification", "indemnification.customer_indemnity")])

    extraction = _extraction("indemnification.made_up_issue")
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags == []


# ---------------------------------------------------------------------------
# Zone-evaluator integration (task 4.3's real evaluate_finding — it landed
# mid-task, so these drive the real evaluator end to end rather than a
# mocked stand-in). Each covers one of the three required "Done when"
# scenarios: a fallback match, a parameter breach, and a semantic red line,
# each producing the right zone through the evaluator.
# ---------------------------------------------------------------------------


def test_fallback_match_produces_yellow_flag_through_evaluator() -> None:
    """A clause matching a yellow-zone fallback rung is a real finding (not
    "no finding" — only preferred/acceptable_variant is that), with the
    fallback's own zone and position_id populated from the real evaluator."""
    contract_id = uuid.uuid4()
    fallback = _position(
        "fallback", "Fallback 1: after month 12, 90 days notice", rung=1, zone="yellow"
    )
    rule = _rule(
        "termination",
        "termination.for_convenience",
        positions=[_position("preferred", "Preferred: none"), fallback],
    )
    clause = _clause(
        "termination", "Customer may terminate for convenience after month 12 on 90 days notice."
    )
    m = _match(clause, [rule])

    extraction = _extraction(
        "termination.for_convenience",
        match_kind="fallback",
        position_label="Fallback 1: after month 12, 90 days notice",
        position_quote="terminate for convenience after month 12",
    )
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 1
    f = flags[0]
    assert f.zone == "yellow"
    assert f.severity == "medium"
    assert f.flag_type == "non_standard"
    assert f.rule_key == "termination.for_convenience"
    assert f.position_id == fallback.id
    assert f.red_line_id is None
    assert f.matched_rule_id == rule.id
    assert f.char_start is not None and f.char_end is not None


def test_parameter_breach_produces_red_flag_through_evaluator() -> None:
    """A parameter value beyond yellow_limit is red (section 5.2 step 2),
    via the real zone_for_parameter/evaluate_finding — not anything this
    module computes."""
    contract_id = uuid.uuid4()
    # lower_is_better, green<=12, yellow<=24 -> 36 is beyond yellow -> red.
    parameter = _parameter("cap_multiple_months", green_limit=12, yellow_limit=24)
    rule = _rule(
        "limitation_of_liability",
        "limitation_of_liability.cap_amount",
        parameters=[parameter],
    )
    text = "Halcyon's aggregate liability is capped at 36 months of Fees."
    clause = _clause("limitation_of_liability", text)
    m = _match(clause, [rule])

    extraction = _extraction(
        "limitation_of_liability.cap_amount",
        match_kind="none",
        position_label=None,
        parameters=[
            ExtractedParameterOut(
                parameter_key="cap_multiple_months",
                value="36 months",
                quote="36 months of Fees",
            )
        ],
    )
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])

    assert len(flags) == 1
    f = flags[0]
    assert f.zone == "red"
    assert f.severity == "high"
    assert f.flag_type == "deviation"
    # EvaluationResult.parameter_values convention: {parameter_key: value} —
    # the parsed numeric value (36), not the model's raw quote/text.
    assert f.parameter_values == {"cap_multiple_months": 36}
    expected_start = text.index("36 months of Fees")
    assert f.char_start == expected_start
    assert f.char_end == expected_start + len("36 months of Fees")


def test_semantic_red_line_triggered_produces_prohibited_flag_through_evaluator() -> None:
    """A triggered semantic red line is always red (section 5.2 step 1),
    regardless of anything else extracted for the rule."""
    contract_id = uuid.uuid4()
    red_line = _red_line("uncapped_data_breach")
    rule = _rule(
        "limitation_of_liability",
        "limitation_of_liability.cap_carve_outs",
        red_lines=[red_line],
    )
    text = "Vendor's liability for a data breach shall be unlimited."
    clause = _clause("limitation_of_liability", text)
    m = _match(clause, [rule])

    extraction = _extraction(
        "limitation_of_liability.cap_carve_outs",
        match_kind="none",
        position_label=None,
        red_lines=[
            SemanticRedLineOut(
                red_line_key="uncapped_data_breach",
                triggered=True,
                quote="liability for a data breach shall be unlimited",
            )
        ],
    )
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])

    assert len(flags) == 1
    f = flags[0]
    assert f.zone == "red"
    assert f.severity == "high"
    assert f.flag_type == "prohibited"
    assert f.red_line_id == red_line.id
    assert f.position_id is None
    expected_start = text.index("liability for a data breach shall be unlimited")
    assert f.char_start == expected_start


def test_preferred_match_through_evaluator_produces_no_flag() -> None:
    """playbook_plan.md section 5.2 point 3: a preferred/acceptable match is
    "no finding" — evaluate_finding returns zone="green" for this (not a
    sentinel), but layer2_content must still not turn it into a flag."""
    contract_id = uuid.uuid4()
    preferred = _position("preferred", "Preferred")
    rule = _rule("governing_law", "governing_law.choice_of_law", positions=[preferred])
    clause = _clause("governing_law", "This Agreement is governed by Delaware law.")
    m = _match(clause, [rule])

    extraction = _extraction(
        "governing_law.choice_of_law", match_kind="preferred", position_label="Preferred"
    )
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags == []


def test_no_match_falls_back_to_rule_default_zone() -> None:
    """playbook_plan.md section 5.2 step 5: no red line, no parameter
    breach, and no position match at all -> a deviation in the rule's
    default_zone (not a crash, not silently dropped)."""
    contract_id = uuid.uuid4()
    rule = _rule(
        "assignment", "assignment.consent_requirement", positions=[_position()],
        default_zone="yellow",
    )
    clause = _clause("assignment", "Either party may assign this Agreement freely.")
    m = _match(clause, [rule])

    # match_kind="none" with no position_label -> matched_position=None in
    # ExtractedClause, and no parameters/red_lines extracted either.
    extraction = _extraction(
        "assignment.consent_requirement", match_kind="none", position_label=None
    )
    fake_item = _item(clause.id, rule_extractions=[extraction])
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 1
    f = flags[0]
    assert f.zone == "yellow"
    assert f.flag_type == "non_standard"
    assert f.position_id is None
    assert f.red_line_id is None


# ---------------------------------------------------------------------------
# Char-offset resolution (free-standing flags) — unchanged by 4.4
# ---------------------------------------------------------------------------


def test_offending_quote_resolved_to_contract_level_offsets() -> None:
    """char_start/char_end are clause.char_start + in-clause position of quote."""
    contract_id = uuid.uuid4()
    text = "This agreement grants unlimited liability to the vendor."
    clause = _clause("limitation_of_liability", text=text, char_start=300)
    m = _match(clause, [_rule("limitation_of_liability")])

    quote = "unlimited liability"
    fake_item = _item(clause.id, _flag("high_risk", "high", "Too broad.", quote=quote))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 1
    f = flags[0]
    expected_start = 300 + text.lower().index("unlimited liability")
    assert f.char_start == expected_start
    assert f.char_end == expected_start + len("unlimited liability")


def test_missing_quote_produces_none_offsets() -> None:
    """A flag with no offending_quote gets char_start=None, char_end=None."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification")
    m = _match(clause, [_rule("indemnification")])

    fake_item = _item(clause.id, _flag("high_risk", quote=None))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags[0].char_start is None
    assert flags[0].char_end is None


def test_quote_not_found_in_clause_produces_none_offsets() -> None:
    """If the quote isn't found in clause text, offsets gracefully return None."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", "Short text.")
    m = _match(clause, [_rule("indemnification")])

    fake_item = _item(clause.id, _flag("high_risk", quote="text that is not there"))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags[0].char_start is None
    assert flags[0].char_end is None


# ---------------------------------------------------------------------------
# Batching (task 4.4 item 2)
# ---------------------------------------------------------------------------


def test_small_contract_uses_single_call_structured() -> None:
    contract_id = uuid.uuid4()
    m = _match(_clause("indemnification"), [_rule("indemnification")])
    fake_item = _item(m.clause.id)
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "own", [m])

    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "call_structured"


def test_oversized_contract_splits_into_batches() -> None:
    """When the prompt would exceed the configured size limit, clauses are
    split across multiple batched calls (gateway.call_batch) instead of one
    call_structured call."""
    contract_id = uuid.uuid4()
    matches = [
        _match(_clause("indemnification", "Indemnification text. " * 50)),
        _match(_clause("termination", "Termination text. " * 50)),
        _match(_clause("payment", "Payment text. " * 50)),
    ]

    captured_items: list[list[dict]] = []

    class BatchingFake(FakeLLMGateway):
        def call_batch(self, task, items, response_model, cache_prefix=None):
            captured_items.append(items)
            return {
                item["id"]: _fake_result(_item(matches[idx].clause.id))
                for idx, item in enumerate(items)
            }

    fake = BatchingFake()

    with (
        patch("app.services.contract_analysis.layer2_content.gateway", fake),
        patch("app.services.contract_analysis.layer2_content.get_settings") as mock_settings,
    ):
        mock_settings.return_value = SimpleNamespace(layer2_max_prompt_chars=200)
        flags = run_layer2(contract_id, "own", matches)

    assert captured_items
    assert len(captured_items[0]) >= 2  # split into more than one batch item
    # Every clause's (empty) result is still accounted for, merged across batches.
    assert flags == []


def test_batched_results_merge_flags_from_every_batch() -> None:
    contract_id = uuid.uuid4()
    matches = [
        _match(_clause("indemnification", "Indemnification text. " * 50)),
        _match(_clause("payment", "Payment text with unlimited exposure. " * 50)),
    ]

    class BatchingFake(FakeLLMGateway):
        def call_batch(self, task, items, response_model, cache_prefix=None):
            results = {}
            for idx, item in enumerate(items):
                clause = matches[idx].clause
                if idx == 1:
                    flag = _flag("high_risk", "high", "Unlimited exposure.")
                    results[item["id"]] = _fake_result(_item(clause.id, flag))
                else:
                    results[item["id"]] = _fake_result(_item(clause.id))
            return results

    fake = BatchingFake()

    with (
        patch("app.services.contract_analysis.layer2_content.gateway", fake),
        patch("app.services.contract_analysis.layer2_content.get_settings") as mock_settings,
    ):
        mock_settings.return_value = SimpleNamespace(layer2_max_prompt_chars=200)
        flags = run_layer2(contract_id, "own", matches)

    assert len(flags) == 1
    assert flags[0].flag_type == "high_risk"
    assert flags[0].clause_id == matches[1].clause.id


# ---------------------------------------------------------------------------
# Inconsistency candidate extraction — unchanged by 4.4
# ---------------------------------------------------------------------------


def test_find_inconsistency_candidates_returns_terms_in_minority_of_clauses() -> None:
    """Terms present in fewer than half the clauses are surfaced as candidates."""
    clauses = [
        _match(_clause("indemnification", "Confidential Information must be protected.")),
        _match(_clause("termination", "Either party may terminate the Agreement.")),
        _match(_clause("governing_law", "This Agreement is governed by Delaware law.")),
    ]
    # "Confidential Information" appears in 1/3 clauses → candidate
    candidates = _find_inconsistency_candidates(clauses)
    assert any("Confidential" in c for c in candidates)


def test_find_inconsistency_candidates_empty_input() -> None:
    assert _find_inconsistency_candidates([]) == []


def test_find_inconsistency_candidates_respects_limit() -> None:
    """Returns at most 20 candidates regardless of input size."""
    texts = [
        f"Term{i} is a defined term used in clause {i}." for i in range(50)
    ]
    clauses = [_match(_clause("indemnification", t)) for t in texts]
    candidates = _find_inconsistency_candidates(clauses)
    assert len(candidates) <= 20


# ---------------------------------------------------------------------------
# Bug 1: enum/set_membership parameters must carry their allowed_values so
# the model is not left guessing the exact backend token string.
# ---------------------------------------------------------------------------


def test_rule_block_renders_allowed_values_for_enum_parameter() -> None:
    param = _parameter(
        key="breach_notice_trigger",
        label="Breach notice trigger",
        unit=None,
        extraction_hint="When notice must be given.",
        value_type="enum",
        direction="set_membership",
        allowed_values=["suspected_or_discovered", "confirmed_only", "no_trigger_stated"],
    )
    rule = _rule("data_breach", parameters=[param])

    block = _rule_block(rule)

    assert (
        "breach_notice_trigger: When notice must be given. "
        "(use exactly one of: suspected_or_discovered, confirmed_only, no_trigger_stated)"
        in block
    )


def test_rule_block_unchanged_for_parameter_without_allowed_values() -> None:
    """No allowed_values set -> no stray "(use exactly one of...)" text, and
    the rendered line is identical to before the bug 1 fix."""
    param = _parameter(key="cap_multiple_months", allowed_values=None)
    rule = _rule("limitation_of_liability", parameters=[param])

    block = _rule_block(rule)

    assert "use exactly one of" not in block
    assert (
        "cap_multiple_months (months): Number of months of Fees the cap is set to."
        in block
    )


# ---------------------------------------------------------------------------
# Bug 2a: a fallback position's own `conditions` must be checked against the
# contract's context — a rung that doesn't apply to this deal should not even
# be offered to the model.
# ---------------------------------------------------------------------------


def test_rule_block_omits_fallback_position_whose_conditions_dont_match_context() -> None:
    matching_fallback = _position("fallback", "Fallback 1: personal data only", rung=1)
    matching_fallback.conditions = {"data_sensitivity": ["personal_data", "phi"]}
    nonmatching_fallback = _position("fallback", "Fallback 2: special category only", rung=2)
    nonmatching_fallback.conditions = {"data_sensitivity": ["special_category"]}
    unconditioned_fallback = _position("fallback", "Fallback 3: always offered", rung=3)
    rule = _rule(
        "dpa",
        positions=[matching_fallback, nonmatching_fallback, unconditioned_fallback],
    )
    context = {"data_sensitivity": "personal_data"}

    block = _rule_block(rule, context)

    assert "Fallback 1: personal data only" in block
    assert "Fallback 2: special category only" not in block
    assert "Fallback 3: always offered" in block


def test_rule_block_renders_all_fallbacks_when_context_is_none() -> None:
    """context=None (the default) -> behavior completely unchanged, even for
    a position that does carry conditions."""
    conditioned = _position("fallback", "Fallback 1: conditioned", rung=1)
    conditioned.conditions = {"data_sensitivity": ["special_category"]}
    rule = _rule("dpa", positions=[conditioned])

    block = _rule_block(rule)

    assert "Fallback 1: conditioned" in block


def test_rule_block_renders_all_fallbacks_when_context_is_empty() -> None:
    """An empty (but non-None) context dict is also treated as "unknown" —
    unchanged rendering, same as context=None."""
    conditioned = _position("fallback", "Fallback 1: conditioned", rung=1)
    conditioned.conditions = {"data_sensitivity": ["special_category"]}
    rule = _rule("dpa", positions=[conditioned])

    block = _rule_block(rule, {})

    assert "Fallback 1: conditioned" in block


def test_run_layer2_context_threads_into_rule_block_for_conditioned_fallback() -> None:
    """Integration: run_layer2's own `context` param (already passed for a
    real contract) must reach _rule_block so a conditioned fallback position
    is only shown to the model when the contract's own context matches it."""
    contract_id = uuid.uuid4()
    matching = _position("fallback", "Fallback A: for personal data", rung=1)
    matching.conditions = {"data_sensitivity": ["personal_data"]}
    nonmatching = _position("fallback", "Fallback B: for special category", rung=2)
    nonmatching.conditions = {"data_sensitivity": ["special_category"]}
    rule = _rule("dpa", positions=[matching, nonmatching])
    clause = _clause("dpa", "Processor shall implement technical measures.")
    m = _match(clause, [rule])

    captured_messages: list[list[dict]] = []

    class CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_messages.append(messages)
            return _fake_result(_item(clause.id))

    fake = CapturingFake()
    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "own", [m], context={"data_sensitivity": "personal_data"})

    user_msg = next(msg["content"] for msg in captured_messages[0] if msg.get("role") == "user")
    assert "Fallback A: for personal data" in user_msg
    assert "Fallback B: for special category" not in user_msg


# ---------------------------------------------------------------------------
# Bug 2b: playbook/global-scope SEMANTIC red lines (document-level, not tied
# to any one rule's clause family) must be evaluated and turned into
# correctly-scoped AnalysisFlag rows.
# ---------------------------------------------------------------------------


def _global_red_line(
    key: str = "global-governing-law-outside-lists",
    scope: str = "global",
    description: str = "Governing law/venue falls outside the approved jurisdiction list.",
    action: str = "escalate",
    test: str | None = "Is the governing law/venue outside the approved jurisdiction list?",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        scope=scope,
        key=key,
        description=description,
        condition_type="semantic",
        condition={"test": test} if test else {},
        action=action,
    )


def test_global_red_line_triggered_produces_scoped_flag() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("governing_law", "This Agreement is governed by the laws of Ruritania.")
    m = _match(clause, [_rule("governing_law")])
    global_red_line = _global_red_line()

    fake_result = _fake_result(_item(clause.id))
    fake_result.global_red_lines = [
        SemanticRedLineOut(
            red_line_key=global_red_line.key,
            triggered=True,
            quote="laws of Ruritania",
        )
    ]
    fake = FakeLLMGateway(structured_responses={"clause_analysis": fake_result})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m], global_red_lines=[global_red_line])

    global_flags = [f for f in flags if f.red_line_id == global_red_line.id]
    assert len(global_flags) == 1
    f = global_flags[0]
    assert f.zone == "red"
    assert f.severity == "high"
    assert f.flag_type == "prohibited"
    assert f.source == "llm"
    assert f.rule_key is None
    assert f.matched_rule_id is None
    assert f.detail["red_line_scope"] == "global"
    assert f.detail["red_line_key"] == global_red_line.key
    assert f.clause_id == clause.id
    assert f.char_start is not None and f.char_end is not None

    # Must survive scoring.py's path unchanged (reuses evaluate_finding's
    # "any red line -> red" severity/zone convention).
    from app.services.contract_analysis.scoring import score_flags

    score = score_flags(contract_id, flags, [])
    assert score.max_zone == "red"
    assert score.score == 1.0


def test_global_red_line_not_triggered_produces_no_flag() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("governing_law", "This Agreement is governed by Delaware law.")
    m = _match(clause, [_rule("governing_law")])
    global_red_line = _global_red_line()

    fake_result = _fake_result(_item(clause.id))
    fake_result.global_red_lines = [
        SemanticRedLineOut(red_line_key=global_red_line.key, triggered=False, quote=None)
    ]
    fake = FakeLLMGateway(structured_responses={"clause_analysis": fake_result})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m], global_red_lines=[global_red_line])

    assert flags == []


def test_unrecognized_global_red_line_key_is_ignored() -> None:
    """A red_line_key the model echoes that was not offered must not be
    mistaken for a real playbook/global red line."""
    contract_id = uuid.uuid4()
    clause = _clause("governing_law")
    m = _match(clause, [_rule("governing_law")])
    global_red_line = _global_red_line()

    fake_result = _fake_result(_item(clause.id))
    fake_result.global_red_lines = [
        SemanticRedLineOut(red_line_key="made-up-key", triggered=True, quote="x")
    ]
    fake = FakeLLMGateway(structured_responses={"clause_analysis": fake_result})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m], global_red_lines=[global_red_line])

    assert flags == []


def test_no_global_red_lines_means_no_extra_flags_or_prompt_section() -> None:
    """Passing no global_red_lines at all (the default) must leave behavior
    identical to before the bug 2b fix."""
    contract_id = uuid.uuid4()
    clause = _clause("governing_law", "This agreement is governed by Delaware law.")
    m = _match(clause, [_rule("governing_law")])

    captured_messages: list[list[dict]] = []

    class CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_messages.append(messages)
            return _fake_result(_item(clause.id))

    fake = CapturingFake()
    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags == []
    user_msg = next(msg["content"] for msg in captured_messages[0] if msg.get("role") == "user")
    assert "Contract-wide red lines" not in user_msg


def test_global_red_lines_merged_across_batches() -> None:
    """Each batch (task 4.4's splitting) is asked the same document-level
    red-line question independently — a batch that reports triggered=True
    must not be overridden by another batch that found no evidence."""
    contract_id = uuid.uuid4()
    matches = [
        _match(_clause("governing_law", "Governed by Ruritania. " * 30)),
        _match(_clause("indemnification", "Indemnification text. " * 30)),
    ]
    global_red_line = _global_red_line()

    class BatchingFake(FakeLLMGateway):
        def call_batch(self, task, items, response_model, cache_prefix=None):
            results = {}
            for idx, item in enumerate(items):
                clause = matches[idx].clause
                triggered = idx == 0
                batch_result = _fake_result(_item(clause.id))
                batch_result.global_red_lines = [
                    SemanticRedLineOut(
                        red_line_key=global_red_line.key,
                        triggered=triggered,
                        quote="Ruritania" if triggered else None,
                    )
                ]
                results[item["id"]] = batch_result
            return results

    fake = BatchingFake()
    with (
        patch("app.services.contract_analysis.layer2_content.gateway", fake),
        patch("app.services.contract_analysis.layer2_content.get_settings") as mock_settings,
    ):
        mock_settings.return_value = SimpleNamespace(layer2_max_prompt_chars=50)
        flags = run_layer2(
            contract_id, "own", matches, global_red_lines=[global_red_line]
        )

    triggered_flags = [f for f in flags if f.red_line_id == global_red_line.id]
    assert len(triggered_flags) == 1


# ---------------------------------------------------------------------------
# Layer 1 -> Layer 2 join: a rule-scope phrase/regex red line Layer 1 already
# matched on a clause+rule decides that pair; Layer 2 emits no second flag.
# ---------------------------------------------------------------------------


def _join_setup():
    fallback = _position("fallback", "Fallback 1", rung=1, zone="yellow")
    phrase_rl = _red_line(
        "audit-unannounced", condition_type="phrase", description="Unannounced audits."
    )
    rule_a = _rule(
        "audit",
        "audit.customer_audit_rights",
        positions=[_position("preferred", "Preferred"), fallback],
        red_lines=[phrase_rl],
        default_zone="yellow",
    )
    rule_b = _rule(
        "audit",
        "audit.audit_costs",
        positions=[_position("preferred", "Preferred"), fallback],
        default_zone="yellow",
    )
    clause = _clause("audit", "Customer may audit Vendor at any time without prior notice.")
    m = _match(clause, [rule_a, rule_b])
    item = _item(
        clause.id,
        rule_extractions=[
            _extraction("audit.customer_audit_rights", "fallback", "Fallback 1", "audit Vendor"),
            _extraction("audit.audit_costs", "fallback", "Fallback 1", "audit Vendor"),
        ],
    )
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(item)})
    return clause, rule_a, rule_b, phrase_rl, m, fake


def test_layer1_red_line_hit_suppresses_layer2_flag_for_same_clause_and_rule() -> None:
    contract_id = uuid.uuid4()
    clause, rule_a, rule_b, phrase_rl, m, fake = _join_setup()
    hits = {(clause.id, rule_a.id): {phrase_rl.id}}

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m], layer1_red_line_hits=hits)

    # rule_a: Layer 1 already decided red -> no contradictory yellow
    # "fallback" flag from Layer 2. rule_b (same clause, no Layer 1 hit)
    # is still evaluated normally.
    assert [f.rule_key for f in flags] == ["audit.audit_costs"]
    assert flags[0].zone == "yellow"


def test_without_layer1_hits_layer2_flags_every_rule() -> None:
    """Control: the same input with no Layer 1 hit produces both flags."""
    contract_id = uuid.uuid4()
    _clause_, _a, _b, _rl, m, fake = _join_setup()
    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])
    assert sorted(f.rule_key for f in flags) == ["audit.audit_costs", "audit.customer_audit_rights"]


def test_layer1_hit_on_another_clause_does_not_suppress() -> None:
    contract_id = uuid.uuid4()
    _clause_, rule_a, _b, phrase_rl, m, fake = _join_setup()
    hits = {(uuid.uuid4(), rule_a.id): {phrase_rl.id}}
    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m], layer1_red_line_hits=hits)
    assert len(flags) == 2


def test_layer1_hit_feeds_evaluate_finding_as_matched_red_line() -> None:
    """The Layer 1 red line is passed into evaluate_finding (the evaluator's
    docstring promise), and decides step 1 ahead of any semantic red line
    the model also triggered."""
    from app.services.contract_analysis import layer2_content

    contract_id = uuid.uuid4()
    clause, rule_a, _b, phrase_rl, m, fake = _join_setup()
    hits = {(clause.id, rule_a.id): {phrase_rl.id}}
    seen = []
    real = layer2_content.evaluate_finding

    def spy(rule, extracted, context=None):
        result = real(rule, extracted, context)
        seen.append((rule, extracted, result))
        return result

    with (
        patch("app.services.contract_analysis.layer2_content.gateway", fake),
        patch("app.services.contract_analysis.layer2_content.evaluate_finding", spy),
    ):
        run_layer2(contract_id, "counterparty", [m], layer1_red_line_hits=hits)

    rule_a_calls = [(e, r) for rule, e, r in seen if rule is rule_a]
    assert len(rule_a_calls) == 1
    extracted, result = rule_a_calls[0]
    assert extracted.matched_red_lines[0] is phrase_rl
    assert result.zone == "red"
    assert result.red_line is phrase_rl
