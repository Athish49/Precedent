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


def _make_flag(contract_id: uuid.UUID, severity: str = "medium") -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_type="non_standard",
        severity=severity,
        source="llm",
        char_start=0,
        char_end=50,
        detail={"description": "Non-standard clause"},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _make_risk(score: float = 0.3, max_severity: str = "medium") -> RiskDTO:
    return RiskDTO(
        score=score,
        max_clause_severity=max_severity,
        weights_version="v1",
    )


def _make_pipeline(
    score: float = 0.25,
    max_severity: str = "medium",
    flag_type: str = "non_standard",
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
        detail={"description": "Clause"},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )
    risk = _make_risk(score=score, max_severity=max_severity)
    analysis = AnalysisResult(flags=[flag], risk=risk)
    return PipelineResult(
        contract_id=contract_id,
        analysis=analysis,
        redlines=[],
        stance_mode="balanced",
    )


def _gate_patches(run: MagicMock):
    """Return context managers that patch both gate repo calls."""
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
async def test_gate_escalates_on_high_severity():
    """Risk score=0.8, max_severity='high' → escalated via hard-stop."""
    pipeline = _make_pipeline(score=0.8, max_severity="high")

    run = MagicMock()
    run.id = uuid.uuid4()

    p1, p2 = _gate_patches(run)
    with p1, p2:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from app.workflows.gate import evaluate_gate
        gate = await evaluate_gate(session, pipeline)

    assert gate.gate_decision == "escalated"
    assert gate.contract_id == pipeline.contract_id
    assert "hard_stop" in gate.gate_reason


@pytest.mark.asyncio
async def test_gate_auto_applies_low_risk():
    """Risk score=0.2, no hard stops → auto_applied."""
    pipeline = _make_pipeline(score=0.2, max_severity="medium")

    run = MagicMock()
    run.id = uuid.uuid4()

    p1, p2 = _gate_patches(run)
    with p1, p2:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from app.workflows.gate import evaluate_gate
        gate = await evaluate_gate(session, pipeline)

    assert gate.gate_decision == "auto_applied"
    assert gate.gate_reason["hard_stop"] is None
    assert gate.gate_reason["aggregate_score"] == pytest.approx(0.2)
