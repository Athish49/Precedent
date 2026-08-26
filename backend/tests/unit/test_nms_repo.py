"""Tests for the NMS repository (T-045).

Note on coverage: these tests verify parameter-passing and parsing in the repo
layer.  The counterparty_pattern view's SQL arithmetic (accept_rate, last_closed_text
aggregation) is verified by construction from Data_Model §7 SQL — no Postgres-backed
integration fixture exists in this repo to run the view against a real DB.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.nms import DecisionEvent
from app.db.repositories.nms_repo import (
    CounterpartyPattern,
    create_decision_event,
    get_counterparty_pattern,
    get_events_for_contract,
    get_patterns_for_counterparty,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    contract_id: uuid.UUID | None = None,
    counterparty_id: uuid.UUID | None = None,
    clause_type: str = "indemnification",
    position_offered: str = "preferred",
    recommended_stance: str = "firm",
    outcome: str | None = "pending",
    final_text: str | None = None,
) -> DecisionEvent:
    return DecisionEvent(
        contract_id=contract_id or uuid.uuid4(),
        counterparty_id=counterparty_id or uuid.uuid4(),
        clause_type=clause_type,
        position_offered=position_offered,
        recommended_stance=recommended_stance,
        outcome=outcome,
        final_text=final_text,
    )


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# create_decision_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_decision_event_adds_to_session() -> None:
    session = _mock_session()
    event = _event()
    await create_decision_event(session, event)
    session.add.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_create_decision_event_flushes() -> None:
    session = _mock_session()
    event = _event()
    await create_decision_event(session, event)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_decision_event_returns_event() -> None:
    session = _mock_session()
    event = _event()
    result = await create_decision_event(session, event)
    assert result is event


@pytest.mark.asyncio
async def test_create_decision_event_with_pending_outcome() -> None:
    """Initial events are created with outcome=pending (T-049 appends resolved events)."""
    session = _mock_session()
    event = _event(outcome="pending")
    result = await create_decision_event(session, event)
    assert result.outcome == "pending"


@pytest.mark.asyncio
async def test_create_decision_event_null_final_text() -> None:
    session = _mock_session()
    event = _event(final_text=None)
    result = await create_decision_event(session, event)
    assert result.final_text is None


# ---------------------------------------------------------------------------
# get_events_for_contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_events_for_contract_returns_list() -> None:
    contract_id = uuid.uuid4()
    event1 = _event(contract_id=contract_id)
    event2 = _event(contract_id=contract_id, clause_type="termination")

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event1, event2]
    session.execute = AsyncMock(return_value=mock_result)

    events = await get_events_for_contract(session, contract_id)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_get_events_for_contract_returns_empty_when_none() -> None:
    contract_id = uuid.uuid4()
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    events = await get_events_for_contract(session, contract_id)
    assert events == []


# ---------------------------------------------------------------------------
# get_counterparty_pattern — view query and result parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_counterparty_pattern_returns_none_when_no_history() -> None:
    """No rows in the view GROUP BY → None (no prior decisions)."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    result = await get_counterparty_pattern(session, uuid.uuid4(), "indemnification")
    assert result is None


@pytest.mark.asyncio
async def test_get_counterparty_pattern_returns_pattern_when_found() -> None:
    counterparty_id = uuid.uuid4()
    session = AsyncMock()
    mock_row = SimpleNamespace(
        counterparty_id=str(counterparty_id),
        clause_type="indemnification",
        accept_rate=0.75,
        last_closed_text="Mutual indemnification for gross negligence.",
    )
    mock_result = MagicMock()
    mock_result.first.return_value = mock_row
    session.execute = AsyncMock(return_value=mock_result)

    pattern = await get_counterparty_pattern(session, counterparty_id, "indemnification")
    assert pattern is not None
    assert isinstance(pattern, CounterpartyPattern)


@pytest.mark.asyncio
async def test_get_counterparty_pattern_accept_rate_value() -> None:
    counterparty_id = uuid.uuid4()
    session = AsyncMock()
    mock_row = SimpleNamespace(
        counterparty_id=str(counterparty_id),
        clause_type="indemnification",
        accept_rate=0.5,
        last_closed_text=None,
    )
    mock_result = MagicMock()
    mock_result.first.return_value = mock_row
    session.execute = AsyncMock(return_value=mock_result)

    pattern = await get_counterparty_pattern(session, counterparty_id, "indemnification")
    assert pattern.accept_rate == 0.5


@pytest.mark.asyncio
async def test_get_counterparty_pattern_last_closed_text() -> None:
    counterparty_id = uuid.uuid4()
    expected_text = "Vendor indemnifies Client only for direct damages."
    session = AsyncMock()
    mock_row = SimpleNamespace(
        counterparty_id=str(counterparty_id),
        clause_type="indemnification",
        accept_rate=1.0,
        last_closed_text=expected_text,
    )
    mock_result = MagicMock()
    mock_result.first.return_value = mock_row
    session.execute = AsyncMock(return_value=mock_result)

    pattern = await get_counterparty_pattern(session, counterparty_id, "indemnification")
    assert pattern.last_closed_text == expected_text


@pytest.mark.asyncio
async def test_get_counterparty_pattern_null_accept_rate_when_no_closed() -> None:
    """accept_rate=None is valid — means events exist but none were accepted."""
    counterparty_id = uuid.uuid4()
    session = AsyncMock()
    mock_row = SimpleNamespace(
        counterparty_id=str(counterparty_id),
        clause_type="termination",
        accept_rate=None,
        last_closed_text=None,
    )
    mock_result = MagicMock()
    mock_result.first.return_value = mock_row
    session.execute = AsyncMock(return_value=mock_result)

    pattern = await get_counterparty_pattern(session, counterparty_id, "termination")
    assert pattern is not None
    assert pattern.accept_rate is None


@pytest.mark.asyncio
async def test_get_counterparty_pattern_queries_view_with_correct_params() -> None:
    """Verify the view is queried with both counterparty_id and clause_type."""
    counterparty_id = uuid.uuid4()
    clause_type = "governing_law"

    captured_params: list[dict] = []
    session = AsyncMock()

    async def _capture_execute(stmt, params=None):
        if params:
            captured_params.append(params)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        return mock_result

    session.execute = _capture_execute

    await get_counterparty_pattern(session, counterparty_id, clause_type)

    assert len(captured_params) == 1
    assert captured_params[0]["clause_type"] == clause_type
    assert str(counterparty_id) in str(captured_params[0]["counterparty_id"])


# ---------------------------------------------------------------------------
# get_patterns_for_counterparty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_patterns_for_counterparty_returns_all_clause_types() -> None:
    counterparty_id = uuid.uuid4()
    session = AsyncMock()
    rows = [
        SimpleNamespace(
            counterparty_id=str(counterparty_id),
            clause_type="indemnification",
            accept_rate=0.8,
            last_closed_text="Mutual indemnification.",
        ),
        SimpleNamespace(
            counterparty_id=str(counterparty_id),
            clause_type="termination",
            accept_rate=0.2,
            last_closed_text=None,
        ),
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    session.execute = AsyncMock(return_value=mock_result)

    patterns = await get_patterns_for_counterparty(session, counterparty_id)
    assert len(patterns) == 2
    clause_types = {p.clause_type for p in patterns}
    assert "indemnification" in clause_types
    assert "termination" in clause_types


@pytest.mark.asyncio
async def test_get_patterns_for_counterparty_returns_empty_when_none() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    patterns = await get_patterns_for_counterparty(session, uuid.uuid4())
    assert patterns == []
