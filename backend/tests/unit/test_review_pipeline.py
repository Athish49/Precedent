"""Tests for T-060 Review Pipeline orchestration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.schemas.redline import RedlineDTO
from app.workflows.review_pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "app.workflows.review_pipeline"


def _make_contract(
    contract_type: str = "nda",
    counterparty_id: uuid.UUID | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contract_type = contract_type
    c.counterparty_id = counterparty_id or uuid.uuid4()
    return c


def _make_flag(
    contract_id: uuid.UUID | None = None,
    clause_id: uuid.UUID | None = None,
    severity: str = "high",
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id or uuid.uuid4(),
        clause_id=clause_id,
        flag_type="missing_clause",
        severity=severity,
        source="deterministic",
        char_start=0,
        char_end=10,
        detail={},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _make_clause(contract_id: uuid.UUID, clause_id: uuid.UUID | None = None) -> MagicMock:
    c = MagicMock()
    c.id = clause_id or uuid.uuid4()
    c.contract_id = contract_id
    c.clause_type = "indemnification"
    c.text = "Indemnification clause text."
    return c


def _make_redline_row(contract_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_id=uuid.uuid4(),
        stance_mode="balanced",
        position="preferred",
        replacement_text="Revised text.",
        tracked_changes=[],
        alternatives=[],
        explanation="Explanation.",
        counterparty_comment="Comment.",
        rationale={},
        status="proposed",
        created_at=datetime.now(UTC),
    )


def _make_resolved(rules: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.rules = rules or {}
    return r


def _make_redline_out(replacement: str = "Revised text.") -> MagicMock:
    out = MagicMock()
    out.replacement_text = replacement
    out.explanation = "Explanation."
    out.counterparty_comment = "Comment."
    out.alternatives = []
    return out


def _make_render_result() -> MagicMock:
    rr = MagicMock()
    rr.tracked_changes = []
    rr.interference_detected = False
    return rr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_pipeline_result():
    """run_pipeline returns PipelineResult with correct contract_id and stance_mode."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="high")
    analysis = AnalysisResult(
        flags=[flag],
        risk=RiskDTO(score=7.5, max_clause_severity="high", weights_version="v1"),
    )
    clause = _make_clause(contract_id, clause_id)
    redline_row = _make_redline_row(contract_id)
    redline_out = _make_redline_out()
    render_result = _make_render_result()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[clause]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(
            f"{_MODULE}.nms_repo.get_counterparty_pattern",
            new=AsyncMock(return_value=None),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", return_value=redline_out),
        patch(f"{_MODULE}.render.render", return_value=render_result),
        patch(
            f"{_MODULE}.persist.persist_redline",
            new=AsyncMock(return_value=(redline_row, MagicMock())),
        ),
    ):
        result = await run_pipeline(session, contract_id, stance_mode="balanced")

    assert isinstance(result, PipelineResult)
    assert result.contract_id == contract_id
    assert result.stance_mode == "balanced"
    assert isinstance(result.analysis, AnalysisResult)
    assert len(result.redlines) == 1
    assert isinstance(result.redlines[0], RedlineDTO)


@pytest.mark.asyncio
async def test_contract_not_found_raises_app_error():
    """run_pipeline raises AppError(404) when contract is missing."""
    session = AsyncMock()
    contract_id = uuid.uuid4()

    with patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=None)):
        with pytest.raises(AppError) as exc_info:
            await run_pipeline(session, contract_id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


@pytest.mark.asyncio
async def test_concurrent_fetch_calls_both_gather_dependencies():
    """Both routing.resolve and clause_repo.get_clauses_for_contract are called."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    resolve_mock = AsyncMock(return_value=_make_resolved())
    clauses_mock = AsyncMock(return_value=[])
    analysis = AnalysisResult(flags=[], risk=None)

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=resolve_mock),
        patch(f"{_MODULE}.clause_repo.get_clauses_for_contract", new=clauses_mock),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
    ):
        result = await run_pipeline(session, contract_id)

    resolve_mock.assert_called_once_with(session, contract.contract_type)
    clauses_mock.assert_called_once_with(session, contract_id)
    assert result.redlines == []


@pytest.mark.asyncio
async def test_empty_flags_produces_no_redlines_and_no_llm_call():
    """When analysis returns no flags, redlines is empty and LLM is never called."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    analysis = AnalysisResult(flags=[], risk=None)
    llm_mock = MagicMock()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", new=llm_mock),
    ):
        result = await run_pipeline(session, contract_id)

    assert result.redlines == []
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_stance_filter_light_skips_low_severity_flags():
    """With stance_mode='light', only high-severity flags pass; low flags produce no redlines."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    # Only low-severity flag — should be filtered by stance "light"
    low_flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="low")
    analysis = AnalysisResult(flags=[low_flag], risk=None)
    clause = _make_clause(contract_id, clause_id)
    llm_mock = MagicMock()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[clause]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", new=llm_mock),
    ):
        result = await run_pipeline(session, contract_id, stance_mode="light")

    assert result.redlines == []
    llm_mock.assert_not_called()
