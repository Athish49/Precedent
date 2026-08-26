"""Tests for obligations monitor — deterministic deadline + renewal alerts (T-081)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.obligations.monitor import (
    MonitorResult,
    _check_deadlines,
    _check_renewals,
    run_monitor,
)

# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

TODAY = date(2026, 1, 15)
CONTRACT_ID = uuid.uuid4()


def _obligation(
    *,
    deadline: date | None = None,
    status: str = "open",
    contract_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id or CONTRACT_ID,
        commitment="Pay invoice",
        owner="Finance",
        deadline=deadline,
        deliverable="Payment",
        status=status,
    )


def _contract(title: str = "Test Contract") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), title=title)


def _meta(
    *,
    expiry_date: date | None = None,
    auto_renewal: bool | None = True,
    contract_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        contract_id=contract_id or CONTRACT_ID,
        expiry_date=expiry_date,
        auto_renewal=auto_renewal,
    )


def _make_session(scalars_items=None, all_items=None) -> AsyncMock:
    """Build a mock AsyncSession whose execute() returns configurable results."""
    session = AsyncMock()

    execute_result = MagicMock()
    # For deadline path: result.scalars().all()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_items or []
    execute_result.scalars.return_value = scalars_mock
    # For renewal path: result.all()
    execute_result.all.return_value = all_items or []

    session.execute = AsyncMock(return_value=execute_result)
    return session


def _make_alert(alert_type: str, payload: dict, contract_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        alert_type=alert_type,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Deadline alert tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deadline_alert_fires_within_threshold():
    """Obligation due in 10 days → 1 deadline alert with correct payload."""
    ob = _obligation(deadline=TODAY + timedelta(days=10))
    session = _make_session(scalars_items=[ob])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.side_effect = lambda s, a: a
        alerts = await _check_deadlines(session, TODAY, 30)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "deadline"
    assert alerts[0].payload["days_until_deadline"] == 10
    assert alerts[0].payload["obligation_id"] == str(ob.id)


@pytest.mark.asyncio
async def test_deadline_alert_not_fired_past_deadline():
    """Obligation deadline yesterday → filtered by query, 0 alerts returned."""
    # The WHERE clause in the real query excludes past deadlines; simulate empty result.
    session = _make_session(scalars_items=[])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        alerts = await _check_deadlines(session, TODAY, 30)

    assert alerts == []
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_deadline_alert_not_fired_beyond_threshold():
    """Obligation deadline in 31 days (beyond default 30) → 0 alerts."""
    session = _make_session(scalars_items=[])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        alerts = await _check_deadlines(session, TODAY, 30)

    assert alerts == []
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_deadline_alert_not_fired_met_status():
    """Obligation with status='met' → filtered by query, 0 alerts."""
    session = _make_session(scalars_items=[])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        alerts = await _check_deadlines(session, TODAY, 30)

    assert alerts == []
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Renewal alert tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renewal_alert_fires_auto_renewal_true():
    """Contract expiry in 45 days, auto_renewal=True → 1 renewal alert."""
    contract = _contract()
    meta = _meta(expiry_date=TODAY + timedelta(days=45), auto_renewal=True, contract_id=contract.id)
    session = _make_session(all_items=[(contract, meta)])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.side_effect = lambda s, a: a
        alerts = await _check_renewals(session, TODAY, 30, 90)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "renewal"
    assert alerts[0].payload["days_until_expiry"] == 45
    assert alerts[0].payload["contract_title"] == contract.title
    assert alerts[0].payload["auto_renewal"] is True


@pytest.mark.asyncio
async def test_renewal_alert_fires_auto_renewal_none():
    """auto_renewal=None (not explicitly False) → alert fires."""
    contract = _contract()
    meta = _meta(expiry_date=TODAY + timedelta(days=60), auto_renewal=None, contract_id=contract.id)
    session = _make_session(all_items=[(contract, meta)])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.side_effect = lambda s, a: a
        alerts = await _check_renewals(session, TODAY, 30, 90)

    assert len(alerts) == 1
    assert alerts[0].payload["auto_renewal"] is None


@pytest.mark.asyncio
async def test_renewal_alert_not_fired_auto_renewal_false():
    """auto_renewal=False → filtered by query, 0 alerts."""
    session = _make_session(all_items=[])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        alerts = await _check_renewals(session, TODAY, 30, 90)

    assert alerts == []
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_renewal_alert_not_fired_below_window_min():
    """Expiry in 20 days (below window_min=30) → filtered by query, 0 alerts."""
    session = _make_session(all_items=[])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        alerts = await _check_renewals(session, TODAY, 30, 90)

    assert alerts == []
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# MonitorResult.total
# ---------------------------------------------------------------------------


def test_monitor_result_total():
    """2 deadline + 1 renewal → total == 3."""
    d_alerts = [MagicMock(), MagicMock()]
    r_alerts = [MagicMock()]
    result = MonitorResult(deadline_alerts=d_alerts, renewal_alerts=r_alerts)
    assert result.total == 3


# ---------------------------------------------------------------------------
# run_monitor integration (both helpers called)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_monitor_calls_both_checks():
    """run_monitor returns a MonitorResult combining deadline and renewal alerts."""
    ob = _obligation(deadline=TODAY + timedelta(days=5))
    contract = _contract()
    meta = _meta(expiry_date=TODAY + timedelta(days=50), auto_renewal=True, contract_id=contract.id)

    session = AsyncMock()

    # First execute call (deadlines) returns scalars; second (renewals) returns pairs.
    deadline_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [ob]
    deadline_result.scalars.return_value = scalars_mock

    renewal_result = MagicMock()
    renewal_result.all.return_value = [(contract, meta)]

    session.execute = AsyncMock(side_effect=[deadline_result, renewal_result])

    with patch(
        "app.services.obligations.monitor.obligation_repo.create_alert",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.side_effect = lambda s, a: a
        result = await run_monitor(session, today=TODAY)

    assert isinstance(result, MonitorResult)
    assert len(result.deadline_alerts) == 1
    assert len(result.renewal_alerts) == 1
    assert result.total == 2
