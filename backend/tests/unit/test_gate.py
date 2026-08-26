"""Tests for T-061 Threshold Gate (app/workflows/gate.py)."""

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


def _make_flag(flag_type: str = "content", severity: str = "medium") -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=uuid.uuid4(),
        flag_type=flag_type,
        severity=severity,
        source="deterministic",
        char_start=0,
        char_end=10,
        detail={},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
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
    risk: RiskDTO | None = None,
    redlines: list[RedlineDTO] | None = None,
) -> PipelineResult:
    contract_id = uuid.uuid4()
    return PipelineResult(
        contract_id=contract_id,
        analysis=AnalysisResult(flags=flags or [], risk=risk),
        redlines=redlines or [],
        stance_mode="balanced",
    )


def _make_run() -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    return run


def _patch_repo(create_return: MagicMock, complete_return: MagicMock | None = None):
    """Return context-manager patches for review_run_repo."""
    mock_repo = MagicMock()
    mock_repo.create_review_run = AsyncMock(return_value=create_return)
    mock_repo.complete_review_run = AsyncMock(return_value=complete_return or create_return)
    return patch(f"{_MODULE}.review_run_repo", mock_repo), mock_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_stop_prohibited_flag_escalates():
    """A prohibited flag forces escalation regardless of score."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[_make_flag(flag_type="prohibited")],
        risk=RiskDTO(score=0.1, max_clause_severity="low", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert isinstance(result, GateResult)
    assert result.gate_decision == "escalated"
    assert "prohibited" in result.gate_reason["hard_stop"]
    mock_repo.complete_review_run.assert_called_once()


@pytest.mark.asyncio
async def test_hard_stop_missing_flag_escalates():
    """A missing flag forces escalation."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[_make_flag(flag_type="missing")],
        risk=RiskDTO(score=0.1, max_clause_severity="low", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "escalated"
    assert "missing" in result.gate_reason["hard_stop"]


@pytest.mark.asyncio
async def test_hard_stop_max_clause_severity_high_escalates():
    """max_clause_severity=high forces escalation even with low aggregate score."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[_make_flag(flag_type="content")],
        risk=RiskDTO(score=0.2, max_clause_severity="high", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "escalated"
    assert "max_clause_severity=high" in result.gate_reason["hard_stop"]


@pytest.mark.asyncio
async def test_hard_stop_interference_detected_escalates():
    """interference_detected=True in any redline rationale forces escalation."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[],
        risk=RiskDTO(score=0.1, max_clause_severity="low", weights_version="v1"),
        redlines=[_make_redline_dto(rationale={"interference_detected": True})],
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "escalated"
    assert "non_interference_failure" in result.gate_reason["hard_stop"]


@pytest.mark.asyncio
async def test_hard_stop_aggregate_score_at_threshold_escalates():
    """Aggregate score >= escalation_score_threshold forces escalation."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[],
        risk=RiskDTO(score=0.7, max_clause_severity="medium", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "escalated"
    assert "aggregate_score" in result.gate_reason["hard_stop"]


@pytest.mark.asyncio
async def test_auto_apply_no_hard_stops_low_score():
    """No hard-stops and score < 0.4 yields auto_applied."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[_make_flag(flag_type="content")],
        risk=RiskDTO(score=0.2, max_clause_severity="low", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "auto_applied"
    assert result.gate_reason["hard_stop"] is None
    assert result.gate_reason["aggregate_score"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_ambiguous_range_score_escalates():
    """Score in [0.4, 0.7) with no hard-stops escalates with score_in_ambiguous_range."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(
        flags=[],
        risk=RiskDTO(score=0.55, max_clause_severity="medium", weights_version="v1"),
    )
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    assert result.gate_decision == "escalated"
    assert result.gate_reason["hard_stop"] is None
    assert result.gate_reason.get("reason") == "score_in_ambiguous_range"


@pytest.mark.asyncio
async def test_no_risk_data_no_flags_auto_applied():
    """With risk=None and no flags and no redlines, ambiguous branch fires (risk is None)."""
    session = AsyncMock()
    run = _make_run()
    pipeline = _make_pipeline(flags=[], risk=None, redlines=[])
    patch_ctx, mock_repo = _patch_repo(run)
    with patch_ctx:
        result = await evaluate_gate(session, pipeline)

    # risk=None: no score hard-stops, no flag hard-stops; auto_apply condition also requires risk != None
    # → falls to else branch → escalated with score_in_ambiguous_range and score=None
    assert result.gate_decision == "escalated"
    assert result.gate_reason["aggregate_score"] is None
    assert result.gate_reason.get("reason") == "score_in_ambiguous_range"
