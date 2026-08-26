"""Unit tests for T-074 — S5 Summaries (summarize_contract + summarize_redlines)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.services.intelligence.summarize import (
    RedlineSummaryResult,
    SummaryResult,
    summarize_contract,
    summarize_redlines,
)

PATCH_GET_CONTRACT = "app.services.intelligence.summarize.contract_repo.get_contract"
PATCH_GET_FLAGS = "app.services.intelligence.summarize.analysis_repo.get_flags_for_contract"
PATCH_GET_RISK = "app.services.intelligence.summarize.analysis_repo.get_risk_score_for_contract"
PATCH_GET_REDLINES = "app.services.intelligence.summarize.redline_repo.get_redlines_for_contract"
PATCH_CALL_TEXT = "app.services.intelligence.summarize.gateway.call_text"


def _make_contract(title: str = "Master Services Agreement") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.title = title
    c.contract_type = "services"
    c.paper_origin = "own"
    return c


def _make_flag(flag_type: str = "high_risk", severity: str = "high", detail: str = "Uncapped indemnity") -> MagicMock:
    f = MagicMock()
    f.flag_type = flag_type
    f.severity = severity
    f.detail = detail
    return f


def _make_risk(score: float = 0.75, max_clause_severity: str = "high") -> MagicMock:
    r = MagicMock()
    r.score = score
    r.max_clause_severity = max_clause_severity
    return r


def _make_redline(
    clause_type: str = "indemnification",
    status: str = "pending",
    position: str = "own_paper",
    replacement_text: str = "Liability capped at contract value.",
    explanation: str = "Added cap to limit exposure.",
    counterparty_comment: str = "Acceptable.",
) -> MagicMock:
    r = MagicMock()
    r.clause_type = clause_type
    r.status = status
    r.position = position
    r.replacement_text = replacement_text
    r.explanation = explanation
    r.counterparty_comment = counterparty_comment
    return r


# ---------------------------------------------------------------------------
# summarize_contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_contract_happy_path():
    """Contract found, flags + risk present → call_text called once, returns SummaryResult."""
    session = MagicMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    flags = [_make_flag()]
    risk = _make_risk()

    with (
        patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=contract)),
        patch(PATCH_GET_FLAGS, new=AsyncMock(return_value=flags)),
        patch(PATCH_GET_RISK, new=AsyncMock(return_value=risk)),
        patch(PATCH_CALL_TEXT, return_value="Executive summary text.") as mock_call,
    ):
        result = await summarize_contract(session, contract_id)

    assert isinstance(result, SummaryResult)
    assert result.summary == "Executive summary text."
    mock_call.assert_called_once()
    call_args = mock_call.call_args
    assert call_args[0][0] == "summarize_contract"


@pytest.mark.asyncio
async def test_summarize_contract_not_found():
    """Contract not found → AppError raised."""
    session = MagicMock()
    contract_id = uuid.uuid4()

    with patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=None)):
        with pytest.raises(AppError) as exc_info:
            await summarize_contract(session, contract_id)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_summarize_contract_no_risk():
    """Risk is None → still calls LLM (no crash), returns SummaryResult."""
    session = MagicMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    flags = [_make_flag(severity="medium")]

    with (
        patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=contract)),
        patch(PATCH_GET_FLAGS, new=AsyncMock(return_value=flags)),
        patch(PATCH_GET_RISK, new=AsyncMock(return_value=None)),
        patch(PATCH_CALL_TEXT, return_value="Summary without risk score.") as mock_call,
    ):
        result = await summarize_contract(session, contract_id)

    assert isinstance(result, SummaryResult)
    assert result.summary == "Summary without risk score."
    mock_call.assert_called_once()
    # Verify no-risk message appears in the user message
    user_msg = mock_call.call_args[0][1][1]["content"]
    assert "No risk score computed yet" in user_msg


# ---------------------------------------------------------------------------
# summarize_redlines tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_redlines_happy_path():
    """Redlines present → call_text called once with task 'summarize_redlines', returns RedlineSummaryResult."""
    session = MagicMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    redlines = [_make_redline(), _make_redline(clause_type="limitation_of_liability", status="accepted")]

    with (
        patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=contract)),
        patch(PATCH_GET_REDLINES, new=AsyncMock(return_value=redlines)),
        patch(PATCH_CALL_TEXT, return_value="Redline thread summary.") as mock_call,
    ):
        result = await summarize_redlines(session, contract_id)

    assert isinstance(result, RedlineSummaryResult)
    assert result.summary == "Redline thread summary."
    assert result.clause_type == "indemnification"
    mock_call.assert_called_once()
    assert mock_call.call_args[0][0] == "summarize_redlines"


@pytest.mark.asyncio
async def test_summarize_redlines_no_redlines():
    """No redlines → returns result with 'No redlines' in summary, no LLM call."""
    session = MagicMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()

    with (
        patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=contract)),
        patch(PATCH_GET_REDLINES, new=AsyncMock(return_value=[])),
        patch(PATCH_CALL_TEXT) as mock_call,
    ):
        result = await summarize_redlines(session, contract_id)

    assert isinstance(result, RedlineSummaryResult)
    assert "No redlines" in result.summary
    assert result.clause_type == ""
    mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_summarize_redlines_contract_not_found():
    """Contract not found → AppError raised."""
    session = MagicMock()
    contract_id = uuid.uuid4()

    with patch(PATCH_GET_CONTRACT, new=AsyncMock(return_value=None)):
        with pytest.raises(AppError) as exc_info:
            await summarize_redlines(session, contract_id)

    assert exc_info.value.status_code == 404
