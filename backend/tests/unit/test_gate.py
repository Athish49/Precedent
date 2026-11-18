"""Tests for the three-zone gate (task 4.5; app/workflows/gate.py).

Rewritten per playbook_implementation.md task 4.5 item 7: the old suite fed
``evaluate_gate`` risk scores between 0.1 and 0.7 against raw-score
thresholds (0.4 / 0.7) that ``app/services/contract_analysis/scoring.py``
never actually produces (``playbook_status.md`` defect #2: "tests pass on a
scale the scorer never produces"). The gate now decides from the worst zone
among the contract's flags (``playbook_plan.md`` section 5.3), so these
tests drive it with ``FlagDTO.zone`` values ("green"/"yellow"/"red"/None)
instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.schemas.redline import RedlineDTO
from app.workflows.gate import GateResult, evaluate_gate
from app.workflows.review_pipeline import PipelineResult

_MODULE = "app.workflows.gate"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flag(
    severity: str = "medium",
    zone: str | None = None,
    position_id: uuid.UUID | None = None,
    red_line_id: uuid.UUID | None = None,
    matched_rule_id: uuid.UUID | None = None,
    clause_type: str = "indemnification",
    rule_key: str | None = None,
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=uuid.uuid4(),
        flag_type="deviation",
        severity=severity,
        source="llm",
        char_start=0,
        char_end=10,
        detail={"clause_type": clause_type},
        matched_rule_id=matched_rule_id,
        created_at=datetime.now(UTC),
        rule_key=rule_key,
        zone=zone,
        position_id=position_id,
        red_line_id=red_line_id,
    )


def _make_redline_dto(rationale: dict | None = None) -> RedlineDTO:
    return RedlineDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=uuid.uuid4(),
        flag_id=uuid.uuid4(),
        stance_mode="balanced",
        position="preferred",
        replacement_text="text",
        tracked_changes=[],
        alternatives=[],
        explanation="expl",
        counterparty_comment="comment",
        rationale=rationale or {},
        status="proposed",
        created_at=datetime.now(UTC),
    )


def _make_pipeline(
    flags: list[FlagDTO] | None = None,
    redlines: list[RedlineDTO] | None = None,
    pinned_version_ids: list[uuid.UUID] | None = None,
) -> PipelineResult:
    contract_id = uuid.uuid4()
    risk = RiskDTO(score=0.0, max_clause_severity=None, weights_version="v2", max_zone=None)
    return PipelineResult(
        contract_id=contract_id,
        analysis=AnalysisResult(flags=flags or [], risk=risk),
        redlines=redlines or [],
        stance_mode="balanced",
        pinned_version_ids=pinned_version_ids or [],
    )


def _make_run() -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    return run


def _none(*_args, **_kwargs):
    return None


async def _run_gate(
    pipeline: PipelineResult,
    *,
    run: MagicMock | None = None,
    contract: MagicMock | None = None,
    escalation_policies: list | None = None,
    get_rule=None,
    get_rule_position=None,
    get_red_line=None,
    get_approver_role=None,
    get_approver_role_by_key=None,
) -> tuple[GateResult, MagicMock]:
    """Run evaluate_gate with every repo it touches mocked.

    Returns ``(result, mock_review_run_repo)`` — the latter so tests can
    inspect what ``create_review_run`` was actually called with (e.g. the
    ``ReviewRun.playbook_version_ids`` it set before persisting).
    """
    session = AsyncMock()
    run = run or _make_run()

    mock_review_run_repo = MagicMock()
    mock_review_run_repo.create_review_run = AsyncMock(return_value=run)
    mock_review_run_repo.complete_review_run = AsyncMock(return_value=run)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_contract = AsyncMock(return_value=contract)

    mock_authority_repo = MagicMock()
    mock_authority_repo.list_escalation_policies = AsyncMock(
        return_value=escalation_policies or []
    )
    mock_authority_repo.get_approver_role = AsyncMock(side_effect=get_approver_role or _none)
    mock_authority_repo.get_approver_role_by_key = AsyncMock(
        side_effect=get_approver_role_by_key or _none
    )

    mock_playbook_repo = MagicMock()
    mock_playbook_repo.get_rule = AsyncMock(side_effect=get_rule or _none)
    mock_playbook_repo.get_rule_position = AsyncMock(side_effect=get_rule_position or _none)
    mock_playbook_repo.get_red_line = AsyncMock(side_effect=get_red_line or _none)

    with (
        patch(f"{_MODULE}.review_run_repo", mock_review_run_repo),
        patch(f"{_MODULE}.contract_repo", mock_contract_repo),
        patch(f"{_MODULE}.authority_repo", mock_authority_repo),
        patch(f"{_MODULE}.playbook_repo", mock_playbook_repo),
    ):
        result = await evaluate_gate(session, pipeline)

    return result, mock_review_run_repo


# ---------------------------------------------------------------------------
# None / green zone -> auto_applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_applied_when_no_flags():
    pipeline = _make_pipeline(flags=[])
    result, mock_repo = await _run_gate(pipeline)

    assert isinstance(result, GateResult)
    assert result.gate_decision == "auto_applied"
    assert result.gate_reason["worst_zone"] is None
    assert result.gate_reason["quality_failure"] is False
    mock_repo.complete_review_run.assert_called_once()


@pytest.mark.asyncio
async def test_auto_applied_when_flags_have_no_zone():
    """Flags that never went through the evaluator (e.g. a vagueness flag
    with no rule binding) must not force routing."""
    pipeline = _make_pipeline(flags=[_make_flag(zone=None), _make_flag(zone=None)])
    result, _ = await _run_gate(pipeline)
    assert result.gate_decision == "auto_applied"


@pytest.mark.asyncio
async def test_green_only_contract_auto_applies():
    """A contract whose worst finding is a green-zone fallback still
    auto-applies — green never needs an approver (playbook_plan.md section
    5.3's gate table: 'None or green -> auto_applied')."""
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="low", zone="green"), _make_flag(severity="low", zone="green")]
    )
    result, mock_repo = await _run_gate(pipeline)

    assert result.gate_decision == "auto_applied"
    assert result.gate_reason["worst_zone"] == "green"
    # Green never needs an approver, so the gate must not have reached any
    # approver-resolution repo call.
    mock_repo.create_review_run.assert_called_once()


# ---------------------------------------------------------------------------
# Yellow zone -> needs_approval, routed to the right approver role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yellow_zone_routes_to_position_approver():
    """A yellow finding tied to a position with its own approver_role_id
    routes there directly, without consulting the escalation matrix."""
    position_id = uuid.uuid4()
    role_id = uuid.uuid4()
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="medium", zone="yellow", position_id=position_id)]
    )

    position = MagicMock(approver_role_id=role_id)
    role = MagicMock(key="commercial_counsel", default_sla_hours=24)

    result, _ = await _run_gate(
        pipeline,
        contract=MagicMock(context={}),
        get_rule_position=lambda _s, pid: position if pid == position_id else None,
        get_approver_role=lambda _s, rid: role if rid == role_id else None,
    )

    assert result.gate_decision == "needs_approval"
    assert result.gate_reason["worst_zone"] == "yellow"
    assert result.gate_reason["approver_role"] == "commercial_counsel"
    assert result.gate_reason["sla_hours"] == 24
    assert result.gate_reason["approver_source"] == "position"


@pytest.mark.asyncio
async def test_yellow_zone_falls_back_to_escalation_matrix():
    """No position approver, but a matching escalation policy exists."""
    rule_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    policy_role_id = uuid.uuid4()
    pipeline = _make_pipeline(
        flags=[
            _make_flag(
                severity="medium",
                zone="yellow",
                matched_rule_id=rule_id,
                clause_type="payment",
            )
        ]
    )

    rule = MagicMock(playbook_id=playbook_id, clause_type="payment")
    policy = MagicMock(
        playbook_id=playbook_id,
        clause_type="payment",
        conditions=None,
        approver_role_id=policy_role_id,
        sla_hours=8,
        required_info={"deal_value": "required"},
        priority=5,
    )
    role = MagicMock(key="deal_desk", default_sla_hours=8)

    result, _ = await _run_gate(
        pipeline,
        contract=MagicMock(context={}),
        get_rule=lambda _s, rid: rule if rid == rule_id else None,
        escalation_policies=[policy],
        get_approver_role=lambda _s, rid: role if rid == policy_role_id else None,
    )

    assert result.gate_decision == "needs_approval"
    assert result.gate_reason["approver_role"] == "deal_desk"
    assert result.gate_reason["sla_hours"] == 8
    assert result.gate_reason["required_info"] == {"deal_value": "required"}
    assert result.gate_reason["approver_source"] == "escalation_matrix"


# ---------------------------------------------------------------------------
# Red zone -> escalated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_red_zone_escalates():
    pipeline = _make_pipeline(flags=[_make_flag(severity="high", zone="red")])
    result, _ = await _run_gate(pipeline, contract=MagicMock(context={}))

    assert result.gate_decision == "escalated"
    assert result.gate_reason["worst_zone"] == "red"


@pytest.mark.asyncio
async def test_red_zone_with_no_approver_configured_still_returns_a_decision():
    """The common case today: no seed data loaded, so no position approver
    and no escalation policy matches. The gate must not crash or block —
    it still returns a decision and records that nothing is configured."""
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="high", zone="red", clause_type="limitation_of_liability")]
    )

    result, _ = await _run_gate(
        pipeline, contract=MagicMock(context={}), escalation_policies=[]
    )

    assert result.gate_decision == "escalated"
    assert result.gate_reason["approver_role"] is None
    assert result.gate_reason["approver_source"] == "none_configured"
    assert "note" in result.gate_reason


# ---------------------------------------------------------------------------
# A `block` red line can never route below general_counsel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_red_line_forces_general_counsel():
    """A block-action red line must win over both a matched position's own
    (lower) approver and whatever the escalation matrix would otherwise
    pick (playbook_plan.md section 5.3: 'block red lines cannot be
    approved below the top legal role')."""
    red_line_id = uuid.uuid4()
    position_id = uuid.uuid4()
    low_role_id = uuid.uuid4()

    pipeline = _make_pipeline(
        flags=[
            _make_flag(
                severity="high",
                zone="red",
                red_line_id=red_line_id,
                position_id=position_id,
            )
        ]
    )

    red_line = MagicMock(action="block", key="no_unlimited_liability", approver_role_id=low_role_id)
    # A position with its own (lower) approver — must be ignored once a
    # block red line is present.
    low_position = MagicMock(approver_role_id=low_role_id)
    low_role = MagicMock(key="contracts_manager", default_sla_hours=8)
    gc_role = MagicMock(key="general_counsel", default_sla_hours=48)
    # An escalation policy that would otherwise route somewhere lower —
    # must also be ignored.
    low_policy = MagicMock(
        playbook_id=None,
        clause_type=None,
        conditions=None,
        approver_role_id=low_role_id,
        sla_hours=8,
        required_info={},
        priority=1,
    )

    result, _ = await _run_gate(
        pipeline,
        contract=MagicMock(context={}),
        get_red_line=lambda _s, rid: red_line if rid == red_line_id else None,
        get_rule_position=lambda _s, pid: low_position if pid == position_id else None,
        escalation_policies=[low_policy],
        get_approver_role=lambda _s, rid: {low_role_id: low_role}.get(rid),
        get_approver_role_by_key=lambda _s, key: gc_role if key == "general_counsel" else None,
    )

    assert result.gate_decision == "escalated"
    assert result.gate_reason["approver_role"] == "general_counsel"
    assert result.gate_reason["approver_source"] == "block_red_line"
    assert result.gate_reason["sla_hours"] == 48


@pytest.mark.asyncio
async def test_block_red_line_forces_general_counsel_even_without_a_role_row():
    """Even if `general_counsel` has no approver_role row loaded (no seed
    data), the gate still names it rather than falling through to a lower
    role or to 'none configured'."""
    red_line_id = uuid.uuid4()
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="high", zone="red", red_line_id=red_line_id)]
    )
    red_line = MagicMock(action="block", key="no_unlimited_liability", approver_role_id=None)

    result, _ = await _run_gate(
        pipeline,
        contract=MagicMock(context={}),
        get_red_line=lambda _s, rid: red_line if rid == red_line_id else None,
    )

    assert result.gate_reason["approver_role"] == "general_counsel"
    assert result.gate_reason["sla_hours"] is None


# ---------------------------------------------------------------------------
# Escalation matrix: most specific match first, then priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_matrix_prefers_most_specific_over_priority():
    """playbook_plan.md section 3.12: 'Most specific match wins; ties broken
    by priority.' A playbook+clause_type-specific policy must win over a
    global one even when the global policy has a higher priority number."""
    rule_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    specific_role_id = uuid.uuid4()
    global_role_id = uuid.uuid4()

    pipeline = _make_pipeline(
        flags=[
            _make_flag(
                severity="high", zone="red", matched_rule_id=rule_id, clause_type="data_protection"
            )
        ]
    )
    rule = MagicMock(playbook_id=playbook_id, clause_type="data_protection")
    specific_policy = MagicMock(
        playbook_id=playbook_id,
        clause_type="data_protection",
        conditions=None,
        approver_role_id=specific_role_id,
        sla_hours=24,
        required_info={},
        priority=1,
    )
    global_policy = MagicMock(
        playbook_id=None,
        clause_type=None,
        conditions=None,
        approver_role_id=global_role_id,
        sla_hours=48,
        required_info={},
        priority=99,
    )
    roles = {
        specific_role_id: MagicMock(key="privacy_counsel", default_sla_hours=24),
        global_role_id: MagicMock(key="general_counsel", default_sla_hours=48),
    }

    result, _ = await _run_gate(
        pipeline,
        contract=MagicMock(context={}),
        get_rule=lambda _s, rid: rule if rid == rule_id else None,
        escalation_policies=[global_policy, specific_policy],
        get_approver_role=lambda _s, rid: roles.get(rid),
    )

    assert result.gate_reason["approver_role"] == "privacy_counsel"


# ---------------------------------------------------------------------------
# Quality failure in redline generation still forces escalated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_failure_forces_escalated_even_on_green_zone():
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="low", zone="green")],
        redlines=[_make_redline_dto(rationale={"interference_detected": True})],
    )
    result, _ = await _run_gate(pipeline)

    assert result.gate_decision == "escalated"
    assert result.gate_reason["quality_failure"] is True
    assert result.gate_reason["approver_source"] == "none_configured"


@pytest.mark.asyncio
async def test_quality_failure_forces_escalated_with_no_flags_at_all():
    pipeline = _make_pipeline(
        flags=[], redlines=[_make_redline_dto(rationale={"interference_detected": True})]
    )
    result, _ = await _run_gate(pipeline)

    assert result.gate_decision == "escalated"
    assert result.gate_reason["worst_zone"] is None
    assert result.gate_reason["quality_failure"] is True


@pytest.mark.asyncio
async def test_no_quality_failure_does_not_escalate_green_zone():
    pipeline = _make_pipeline(
        flags=[_make_flag(severity="low", zone="green")],
        redlines=[_make_redline_dto(rationale={"interference_detected": False})],
    )
    result, _ = await _run_gate(pipeline)
    assert result.gate_decision == "auto_applied"


# ---------------------------------------------------------------------------
# playbook_version_ids recorded on the review run (task 4.5 item 6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_playbook_version_ids_recorded_on_review_run():
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    pipeline = _make_pipeline(flags=[], pinned_version_ids=[v1, v2])

    _, mock_repo = await _run_gate(pipeline)

    created_run = mock_repo.create_review_run.call_args.args[1]
    assert created_run.playbook_version_ids == [str(v1), str(v2)]


@pytest.mark.asyncio
async def test_no_pinned_versions_records_none():
    pipeline = _make_pipeline(flags=[], pinned_version_ids=[])

    _, mock_repo = await _run_gate(pipeline)

    created_run = mock_repo.create_review_run.call_args.args[1]
    assert created_run.playbook_version_ids is None
