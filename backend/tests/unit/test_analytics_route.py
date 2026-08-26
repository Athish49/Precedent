"""Unit tests for S9 Analytics API endpoints (T-085).

All DB calls are mocked — no real database or LLM.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routes.analytics import _get_session
from app.main import app

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

_NOW = datetime.datetime.now(datetime.timezone.utc)

FAKE_INTELLIGENCE_ROW = {
    "contract_id": uuid.uuid4(),
    "title": "Test Contract",
    "contract_type": None,
    "paper_origin": "own",
    "status": "analyzed",
    "counterparty_id": None,
    "counterparty_name": None,
    "effective_date": None,
    "expiry_date": None,
    "governing_law": None,
    "auto_renewal": None,
    "notice_period_days": None,
    "liability_cap": None,
    "payment_terms": None,
    "risk_score": None,
    "max_clause_severity": None,
    "created_at": _NOW,
    "updated_at": None,
}

FAKE_PORTFOLIO_RISK = {
    "total_contracts": 5,
    "total_high_flags": 2,
    "total_medium_flags": 3,
    "total_low_flags": 1,
    "total_flags": 6,
    "avg_weighted_flag_score": 4.5,
    "avg_risk_score": 6.0,
    "contracts_high_severity": 1,
    "contracts_medium_severity": 2,
    "contracts_low_severity": 2,
}

FAKE_VALUE_ROW = {
    "contract_id": uuid.uuid4(),
    "title": "Value Contract",
    "contract_type": None,
    "counterparty_id": None,
    "counterparty_name": None,
    "financial_fields": None,
    "total_value": None,
    "currency": None,
    "annual_value": None,
    "payment_frequency": None,
    "effective_date": None,
    "expiry_date": None,
    "duration_days": None,
    "status": "draft",
    "created_at": _NOW,
}

FAKE_TABULAR_ROW = {
    "contract_id": uuid.uuid4(),
    "title": "Tabular Contract",
    "contract_type": None,
    "paper_origin": None,
    "status": None,
    "counterparty_name": None,
    "effective_date": None,
    "expiry_date": None,
    "governing_law": None,
    "auto_renewal": None,
    "notice_period_days": None,
    "payment_terms": None,
    "liability_cap": None,
    "risk_score": None,
    "max_clause_severity": None,
    "high_flags": 0,
    "medium_flags": 0,
    "low_flags": 0,
    "open_obligations": 0,
    "overdue_obligations": 0,
    "proposed_redlines": None,
    "accepted_redlines": None,
    "created_at": _NOW,
    "updated_at": None,
}

FAKE_RENEWAL_ROW = {
    "contract_id": uuid.uuid4(),
    "title": "Renewal Contract",
    "contract_type": None,
    "counterparty_id": None,
    "counterparty_name": None,
    "expiry_date": None,
    "auto_renewal": None,
    "notice_period_days": None,
    "governing_law": None,
    "risk_score": None,
    "max_clause_severity": None,
    "renewal_recommendation": None,
    "renewal_rationale": None,
    "compliance_pass": None,
    "last_alert_at": None,
    "alert_acknowledged": None,
    "contract_status": None,
}


def test_get_intelligence_returns_list() -> None:
    """GET /api/analytics/intelligence → 200, list with one row."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_intelligence",
        new=AsyncMock(return_value=[FAKE_INTELLIGENCE_ROW]),
    ):
        response = client.get("/api/analytics/intelligence")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["title"] == "Test Contract"


def test_get_portfolio_risk_returns_dict() -> None:
    """GET /api/analytics/portfolio-risk → 200, dict with expected keys."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_portfolio_risk",
        new=AsyncMock(return_value=FAKE_PORTFOLIO_RISK),
    ):
        response = client.get("/api/analytics/portfolio-risk")

    assert response.status_code == 200
    body = response.json()
    assert body["total_contracts"] == 5
    assert body["total_high_flags"] == 2
    assert body["avg_risk_score"] == 6.0


def test_get_portfolio_risk_empty_returns_zeroed() -> None:
    """GET /api/analytics/portfolio-risk when service returns {} → 200 with zeroed response."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_portfolio_risk",
        new=AsyncMock(return_value={}),
    ):
        response = client.get("/api/analytics/portfolio-risk")

    assert response.status_code == 200
    body = response.json()
    assert body["total_contracts"] == 0
    assert body["total_flags"] == 0
    assert body["avg_risk_score"] is None


def test_get_contract_value_returns_list() -> None:
    """GET /api/analytics/contract-value → 200, list."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_contract_value",
        new=AsyncMock(return_value=[FAKE_VALUE_ROW]),
    ):
        response = client.get("/api/analytics/contract-value")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["title"] == "Value Contract"


def test_get_tabular_returns_list() -> None:
    """GET /api/analytics/tabular → 200, list."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_tabular",
        new=AsyncMock(return_value=[FAKE_TABULAR_ROW]),
    ):
        response = client.get("/api/analytics/tabular")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["high_flags"] == 0


def test_get_tabular_with_columns_param() -> None:
    """GET /api/analytics/tabular?columns=title&columns=status → 200, columns param accepted."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_tabular",
        new=AsyncMock(return_value=[FAKE_TABULAR_ROW]),
    ) as mock_fn:
        response = client.get("/api/analytics/tabular?columns=title&columns=status")

    assert response.status_code == 200
    # Verify the service was called with the columns list
    mock_fn.assert_called_once()
    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("columns") == ["title", "status"] or (
        len(call_kwargs.args) > 1 and call_kwargs.args[1] == ["title", "status"]
    )


def test_get_renewals_returns_list() -> None:
    """GET /api/analytics/renewals → 200, list."""
    with patch(
        "app.api.routes.analytics.analytics_service.get_renewals",
        new=AsyncMock(return_value=[FAKE_RENEWAL_ROW]),
    ):
        response = client.get("/api/analytics/renewals")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["title"] == "Renewal Contract"
