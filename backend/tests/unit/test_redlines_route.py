"""Unit tests for S3 Redlines API endpoints (T-051).

All DB and service calls are mocked — no real database or LLM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.redlines import _get_session
from app.db.models.redline import Redline
from app.main import app

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CONTRACT_ID = uuid.uuid4()
_REDLINE_ID = uuid.uuid4()
_CLAUSE_ID = uuid.uuid4()
_FLAG_ID = uuid.uuid4()


def _make_redline(
    redline_id: uuid.UUID = _REDLINE_ID,
    contract_id: uuid.UUID = _CONTRACT_ID,
    clause_id: uuid.UUID = _CLAUSE_ID,
    flag_id: uuid.UUID = _FLAG_ID,
    stance_mode: str = "balanced",
    position: str = "preferred",
    status: str = "proposed",
) -> MagicMock:
    r = MagicMock(spec=Redline)
    r.id = redline_id
    r.contract_id = contract_id
    r.clause_id = clause_id
    r.flag_id = flag_id
    r.stance_mode = stance_mode
    r.position = position
    r.replacement_text = "Revised clause text."
    r.tracked_changes = [{"op": "equal", "text": "Revised", "old_start": 0, "old_end": 7, "new_start": 0, "new_end": 7}]
    r.alternatives = [{"label": "fallback", "text": "Alternative text."}]
    r.explanation = "The original clause imposed unlimited liability."
    r.counterparty_comment = "This limits our exposure appropriately."
    r.rationale = {"flag_type": "liability", "flag_severity": "high"}
    r.status = status
    r.created_at = _NOW
    return r


mock_session = AsyncMock()
mock_session.commit = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)


# ── GET /api/redlines/{contract_id} ───────────────────────────────────────────


def test_get_redlines_returns_list() -> None:
    redline = _make_redline()
    with patch(
        "app.db.repositories.redline_repo.get_redlines_for_contract",
        new=AsyncMock(return_value=[redline]),
    ):
        response = client.get(f"/api/redlines/{_CONTRACT_ID}")

    assert response.status_code == 200
    body = response.json()
    assert "redlines" in body
    assert len(body["redlines"]) == 1
    assert body["redlines"][0]["status"] == "proposed"
    assert body["redlines"][0]["stance_mode"] == "balanced"


def test_get_redlines_empty() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redlines_for_contract",
        new=AsyncMock(return_value=[]),
    ):
        response = client.get(f"/api/redlines/{_CONTRACT_ID}")

    assert response.status_code == 200
    assert response.json() == {"redlines": []}


# ── POST /api/redlines/{redline_id}/toggle-fallback ───────────────────────────


def test_toggle_fallback_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(f"/api/redlines/{_REDLINE_ID}/toggle-fallback")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_toggle_fallback_success() -> None:
    redline = _make_redline(position="fallback")
    mock_clause = MagicMock()
    mock_clause.text = "Original clause text."

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.toggle_fallback",
            new=AsyncMock(return_value=redline),
        ),
    ):
        response = client.post(f"/api/redlines/{_REDLINE_ID}/toggle-fallback")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)
    assert body["position"] == "fallback"


# ── POST /api/redlines/{redline_id}/refine ────────────────────────────────────


def test_refine_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/refine",
            json={"instruction": "Make it shorter."},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_refine_success() -> None:
    redline = _make_redline()
    mock_clause = MagicMock()
    mock_clause.text = "Original clause text."

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.refine",
            new=AsyncMock(return_value=redline),
        ),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/refine",
            json={"instruction": "Make it shorter."},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)


# ── POST /api/redlines/{redline_id}/decision ──────────────────────────────────


def test_decision_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/decision",
            json={"outcome": "accepted"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_decision_success() -> None:
    redline = _make_redline(status="accepted")
    redline.contract_id = _CONTRACT_ID

    mock_contract = MagicMock()
    mock_contract.counterparty_id = uuid.uuid4()

    mock_clause = MagicMock()
    mock_clause.clause_type = "liability"

    mock_event = MagicMock()

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.contract_repo.get_contract",
            new=AsyncMock(return_value=mock_contract),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.record_decision",
            new=AsyncMock(return_value=(redline, mock_event)),
        ),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/decision",
            json={"outcome": "accepted"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)
    assert body["status"] == "accepted"
