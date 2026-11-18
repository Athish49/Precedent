"""End-to-end review pipeline integration test (fake LLM, no real DB)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.workflows.review_pipeline import PipelineResult

_PIPE_MODULE = "app.workflows.review_pipeline"
_GATE_MODULE = "app.workflows.gate"


def _make_contract(contract_type: str = "nda") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contract_type = contract_type
    c.counterparty_id = uuid.uuid4()
    return c


def _make_flag(
    contract_id: uuid.UUID, severity: str = "medium", zone: str | None = None
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_type="non_standard",
        severity=severity,
        source="llm",
        char_start=0,
        char_end=50,
        detail={"description": "Non-standard clause", "clause_type": "indemnification"},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
        zone=zone,
    )


def _make_risk(
    score: float = 0.3, max_severity: str = "medium", max_zone: str | None = None
) -> RiskDTO:
    return RiskDTO(
        score=score,
        max_clause_severity=max_severity,
        weights_version="v2",
        max_zone=max_zone,
    )


def _make_pipeline(
    score: float = 0.25,
    max_severity: str = "medium",
    flag_type: str = "non_standard",
    zone: str | None = None,
) -> PipelineResult:
    contract_id = uuid.uuid4()
    flag = FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_type=flag_type,
        severity=max_severity,
        source="llm",
        char_start=0,
        char_end=50,
        detail={"description": "Clause", "clause_type": "indemnification"},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
        zone=zone,
    )
    risk = _make_risk(score=score, max_severity=max_severity, max_zone=zone)
    analysis = AnalysisResult(flags=[flag], risk=risk)
    return PipelineResult(
        contract_id=contract_id,
        analysis=analysis,
        redlines=[],
        stance_mode="balanced",
    )


def _gate_patches(run: MagicMock, contract: MagicMock | None = None):
    """Return context managers that patch gate.py's repo calls.

    ``evaluate_gate`` (task 4.5 rewrite) resolves an approver for any
    yellow/red worst zone, which means it also reaches ``contract_repo`` (for
    escalation-matrix context) and ``authority_repo`` (no escalation
    policies loaded — there is no seed data in these tests, which is exactly
    the "no approver configured" case the gate must still handle without
    crashing or blocking).
    """
    contract = contract or MagicMock(context={})
    return (
        patch(
            f"{_GATE_MODULE}.review_run_repo.create_review_run",
            new_callable=AsyncMock,
            return_value=run,
        ),
        patch(
            f"{_GATE_MODULE}.review_run_repo.complete_review_run",
            new_callable=AsyncMock,
            return_value=run,
        ),
        patch(
            f"{_GATE_MODULE}.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=contract,
        ),
        patch(
            f"{_GATE_MODULE}.authority_repo.list_escalation_policies",
            new_callable=AsyncMock,
            return_value=[],
        ),
    )


@pytest.mark.asyncio
async def test_review_pipeline_e2e():
    """Full pipeline: run_pipeline → evaluate_gate produces auto_applied decision."""
    contract = _make_contract()
    contract_id = contract.id
    analysis = AnalysisResult(
        flags=[_make_flag(contract_id, severity="medium")],
        risk=_make_risk(score=0.25, max_severity="medium"),
    )

    run = MagicMock()
    run.id = uuid.uuid4()

    with (
        patch(
            f"{_PIPE_MODULE}.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=contract,
        ),
        patch(
            f"{_PIPE_MODULE}.routing.resolve",
            new_callable=AsyncMock,
        ) as mock_resolve,
        patch(
            f"{_PIPE_MODULE}.clause_repo.get_clauses_for_contract",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            f"{_PIPE_MODULE}.contract_analysis_service.analyze",
            new_callable=AsyncMock,
            return_value=analysis,
        ),
        patch(
            f"{_GATE_MODULE}.review_run_repo.create_review_run",
            new_callable=AsyncMock,
            return_value=run,
        ),
        patch(
            f"{_GATE_MODULE}.review_run_repo.complete_review_run",
            new_callable=AsyncMock,
            return_value=run,
        ),
    ):
        resolved = MagicMock()
        resolved.rules = {}
        mock_resolve.return_value = resolved

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from app.workflows.review_pipeline import run_pipeline
        pipeline = await run_pipeline(session, contract_id)

        assert pipeline.contract_id == contract_id
        assert pipeline.stance_mode == "balanced"
        assert pipeline.analysis.risk is not None
        assert pipeline.analysis.risk.score == 0.25

        from app.workflows.gate import evaluate_gate
        gate = await evaluate_gate(session, pipeline)

        assert gate.gate_decision == "auto_applied"
        assert gate.contract_id == contract_id


@pytest.mark.asyncio
async def test_gate_escalates_on_red_zone():
    """A flag in the red zone escalates, with no approver configured (no seed data)."""
    pipeline = _make_pipeline(score=0.8, max_severity="high", zone="red")

    run = MagicMock()
    run.id = uuid.uuid4()

    p1, p2, p3, p4 = _gate_patches(run)
    with p1, p2, p3, p4:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from app.workflows.gate import evaluate_gate
        gate = await evaluate_gate(session, pipeline)

    assert gate.gate_decision == "escalated"
    assert gate.contract_id == pipeline.contract_id
    assert gate.gate_reason["worst_zone"] == "red"
    assert gate.gate_reason["approver_role"] is None
    assert gate.gate_reason["approver_source"] == "none_configured"


@pytest.mark.asyncio
async def test_gate_auto_applies_low_risk():
    """No flag carries a zone (none breach the playbook) → auto_applied."""
    pipeline = _make_pipeline(score=0.2, max_severity="medium", zone=None)

    run = MagicMock()
    run.id = uuid.uuid4()

    p1, p2, p3, p4 = _gate_patches(run)
    with p1, p2, p3, p4:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from app.workflows.gate import evaluate_gate
        gate = await evaluate_gate(session, pipeline)

    assert gate.gate_decision == "auto_applied"
    assert gate.gate_reason["worst_zone"] is None
    assert gate.gate_reason["quality_failure"] is False
