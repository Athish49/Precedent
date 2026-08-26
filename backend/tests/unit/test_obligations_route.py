"""Unit tests for S8 Obligations API endpoints (T-083).

All DB and service calls are mocked — no real database or LLM.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.routes.obligations import _get_session
from app.db.models.obligation import Alert, Obligation
from app.main import app
from app.services.obligations.monitor import MonitorResult
from app.services.obligations.renewal import RenewalResult

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

_CONTRACT_ID = uuid.uuid4()
_ALERT_ID = uuid.uuid4()

_NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


def _make_obligation(**kwargs) -> Obligation:
    ob = MagicMock(spec=Obligation)
    ob.id = kwargs.get("id", uuid.uuid4())
    ob.contract_id = kwargs.get("contract_id", _CONTRACT_ID)
    ob.commitment = kwargs.get("commitment", "Deliver report")
    ob.owner = kwargs.get("owner", "legal")
    ob.deadline = kwargs.get("deadline", date(2026, 9, 1))
    ob.deliverable = kwargs.get("deliverable", "Report")
    ob.char_start = kwargs.get("char_start", 0)
    ob.char_end = kwargs.get("char_end", 100)
    ob.status = kwargs.get("status", "open")
    ob.created_at = kwargs.get("created_at", _NOW)
    return ob


def _make_alert(**kwargs) -> Alert:
    al = MagicMock(spec=Alert)
    al.id = kwargs.get("id", _ALERT_ID)
    al.contract_id = kwargs.get("contract_id", _CONTRACT_ID)
    al.alert_type = kwargs.get("alert_type", "deadline")
    al.payload = kwargs.get("payload", {"days_until_deadline": 5})
    al.fired_at = kwargs.get("fired_at", _NOW)
    al.acknowledged = kwargs.get("acknowledged", False)
    return al


# ── POST /api/obligations/{id}/extract ───────────────────────────────────────


def test_extract_obligations_returns_list() -> None:
    ob = _make_obligation()
    with patch(
        "app.api.routes.obligations.obligation_service.extract",
        new=AsyncMock(return_value=[ob]),
    ):
        response = client.post(f"/api/obligations/{_CONTRACT_ID}/extract")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["commitment"] == "Deliver report"
    assert body[0]["status"] == "open"


# ── GET /api/obligations/{id} ────────────────────────────────────────────────


def test_get_obligations_returns_list() -> None:
    ob = _make_obligation()
    with patch(
        "app.api.routes.obligations.obligation_service.get_obligations",
        new=AsyncMock(return_value=[ob]),
    ):
        response = client.get(f"/api/obligations/{_CONTRACT_ID}")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["owner"] == "legal"


# ── POST /api/obligations/monitor/run ────────────────────────────────────────


def test_run_monitor_returns_counts() -> None:
    deadline_alert = _make_alert(alert_type="deadline")
    renewal_alert = _make_alert(alert_type="renewal")
    monitor_result = MonitorResult(
        deadline_alerts=[deadline_alert],
        renewal_alerts=[renewal_alert],
    )
    with patch(
        "app.api.routes.obligations.monitor_service.run_monitor",
        new=AsyncMock(return_value=monitor_result),
    ):
        response = client.post("/api/obligations/monitor/run")

    assert response.status_code == 200
    body = response.json()
    assert body["deadline_alerts"] == 1
    assert body["renewal_alerts"] == 1
    assert body["total"] == 2


# ── POST /api/obligations/{id}/compliance-check ──────────────────────────────


def test_compliance_check_returns_result() -> None:
    renewal_result = RenewalResult(
        recommendation="renew",
        rationale="No issues found.",
        compliance_pass=True,
        compliance_issues=[],
    )
    with patch(
        "app.api.routes.obligations.renewal_service.check_compliance",
        new=AsyncMock(return_value=renewal_result),
    ):
        response = client.post(f"/api/obligations/{_CONTRACT_ID}/compliance-check")

    assert response.status_code == 200
    body = response.json()
    assert body["compliance_pass"] is True
    assert body["compliance_issues"] == []
    assert body["recommendation"] == "renew"
    assert body["rationale"] == "No issues found."


# ── GET /api/obligations/alerts ──────────────────────────────────────────────


def test_list_alerts_returns_all() -> None:
    al = _make_alert()
    with patch(
        "app.api.routes.obligations.obligation_repo.get_all_alerts",
        new=AsyncMock(return_value=[al]),
    ):
        response = client.get("/api/obligations/alerts")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["alert_type"] == "deadline"
    assert body[0]["acknowledged"] is False


def test_list_alerts_with_type_filter() -> None:
    al = _make_alert(alert_type="deadline")
    captured = {}

    async def _mock_get_all_alerts(session, *, alert_type=None, acknowledged=None):
        captured["alert_type"] = alert_type
        captured["acknowledged"] = acknowledged
        return [al]

    with patch(
        "app.api.routes.obligations.obligation_repo.get_all_alerts",
        new=_mock_get_all_alerts,
    ):
        response = client.get("/api/obligations/alerts?alert_type=deadline")

    assert response.status_code == 200
    assert captured["alert_type"] == "deadline"
    assert captured["acknowledged"] is None


# ── POST /api/obligations/alerts/{id}/ack ────────────────────────────────────


def test_acknowledge_alert_sets_acknowledged() -> None:
    # Use a simple object instead of MagicMock so attribute assignment works normally
    class _StubAlert:
        id = _ALERT_ID
        contract_id = _CONTRACT_ID
        alert_type = "deadline"
        payload: dict = {"days_until_deadline": 5}
        fired_at = _NOW
        acknowledged = False

    al = _StubAlert()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = al
    mock_session.execute = AsyncMock(return_value=execute_result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    response = client.post(f"/api/obligations/alerts/{_ALERT_ID}/ack")

    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged"] is True
    assert al.acknowledged is True


def test_acknowledge_alert_unknown_id_returns_404() -> None:
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=execute_result)

    unknown_id = uuid.uuid4()
    response = client.post(f"/api/obligations/alerts/{unknown_id}/ack")

    assert response.status_code == 404
