"""Unit tests for S6 Playbook & Rules API endpoints (T-036).

All DB calls are mocked via dependency override — no real database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbooks import _get_session
from app.db.models.playbook import Playbook, PlaybookRule
from app.main import app

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PB_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()


def _make_playbook(
    pb_id: uuid.UUID = _PB_ID,
    name: str = "NDA Playbook",
    practice_area: str = "nda",
    precedence: int = 0,
) -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = pb_id
    pb.name = name
    pb.practice_area = practice_area
    pb.precedence = precedence
    pb.created_at = _NOW
    pb.updated_at = _NOW
    return pb


def _make_rule(
    rule_id: uuid.UUID = _RULE_ID,
    playbook_id: uuid.UUID = _PB_ID,
    clause_type: str = "indemnification",
) -> MagicMock:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id
    rule.playbook_id = playbook_id
    rule.clause_type = clause_type
    rule.preferred_language = "Standard indemnification language."
    rule.acceptable_variations = None
    rule.prohibited_terms = None
    rule.fallback_language = None
    rule.required = True
    rule.risk_weight = 1.5
    rule.escalation_threshold = None
    return rule


mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

# ── Helpers ───────────────────────────────────────────────────────────────────

_UNKNOWN_ID = str(uuid.uuid4())


def _scalar(value: object) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _scalars_all(items: list) -> MagicMock:
    m = MagicMock()
    m.scalars.return_value.all.return_value = items
    return m


def _rowcount(n: int) -> MagicMock:
    m = MagicMock()
    m.rowcount = n
    return m


# ── Playbook list ─────────────────────────────────────────────────────────────


def test_list_playbooks_empty() -> None:
    mock_session.execute = AsyncMock(return_value=_scalars_all([]))
    response = client.get("/api/playbooks")
    assert response.status_code == 200
    assert response.json() == []


def test_list_playbooks_returns_items() -> None:
    pb = _make_playbook()
    mock_session.execute = AsyncMock(return_value=_scalars_all([pb]))
    response = client.get("/api/playbooks")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "NDA Playbook"
    assert body[0]["practice_area"] == "nda"


# ── Playbook create ───────────────────────────────────────────────────────────


def test_create_playbook_success() -> None:
    pb = _make_playbook()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch(
        "app.db.repositories.playbook_repo.create_playbook",
        new=AsyncMock(return_value=pb),
    ):
        response = client.post(
            "/api/playbooks",
            json={"name": "NDA Playbook", "practice_area": "nda", "precedence": 0},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "NDA Playbook"
    assert body["practice_area"] == "nda"


def test_create_playbook_invalid_practice_area() -> None:
    response = client.post(
        "/api/playbooks",
        json={"name": "X", "practice_area": "invalid"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_practice_area"


# ── Get playbook by id ────────────────────────────────────────────────────────


def test_get_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.get(f"/api/playbooks/{_UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_playbook_with_rules() -> None:
    pb = _make_playbook()
    rule = _make_rule()

    call_count = 0

    async def _multi_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar(pb)
        return _scalars_all([rule])

    mock_session.execute = _multi_execute

    response = client.get(f"/api/playbooks/{_PB_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "NDA Playbook"
    assert len(body["rules"]) == 1
    assert body["rules"][0]["clause_type"] == "indemnification"


# ── Update playbook ───────────────────────────────────────────────────────────


def test_update_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.patch(
        f"/api/playbooks/{_UNKNOWN_ID}",
        json={"name": "New Name"},
    )
    assert response.status_code == 404


def test_update_playbook_success() -> None:
    pb = _make_playbook(name="Updated")

    with patch(
        "app.db.repositories.playbook_repo.get_playbook",
        new=AsyncMock(return_value=pb),
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        response = client.patch(
            f"/api/playbooks/{_PB_ID}",
            json={"name": "Updated"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


# ── Delete playbook ───────────────────────────────────────────────────────────


def test_delete_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(0))
    response = client.delete(f"/api/playbooks/{_UNKNOWN_ID}")
    assert response.status_code == 404


def test_delete_playbook_success() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(1))
    mock_session.commit = AsyncMock()
    response = client.delete(f"/api/playbooks/{_PB_ID}")
    assert response.status_code == 204


# ── Rules list ────────────────────────────────────────────────────────────────


def test_list_rules_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.get(f"/api/playbooks/{_UNKNOWN_ID}/rules")
    assert response.status_code == 404


def test_list_rules_success() -> None:
    pb = _make_playbook()
    rule = _make_rule()

    call_count = 0

    async def _multi_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar(pb)
        return _scalars_all([rule])

    mock_session.execute = _multi_execute

    response = client.get(f"/api/playbooks/{_PB_ID}/rules")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["clause_type"] == "indemnification"


# ── Rule create ───────────────────────────────────────────────────────────────


def test_create_rule_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.post(
        f"/api/playbooks/{_UNKNOWN_ID}/rules",
        json={"clause_type": "indemnification"},
    )
    assert response.status_code == 404


def test_create_rule_success() -> None:
    pb = _make_playbook()
    rule = _make_rule()

    with (
        patch(
            "app.db.repositories.playbook_repo.get_playbook",
            new=AsyncMock(return_value=pb),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_rule",
            new=AsyncMock(return_value=rule),
        ),
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        response = client.post(
            f"/api/playbooks/{_PB_ID}/rules",
            json={"clause_type": "indemnification", "required": True, "risk_weight": 1.5},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["clause_type"] == "indemnification"
    assert body["required"] is True


# ── Rule update ───────────────────────────────────────────────────────────────


def test_update_rule_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.patch(
        f"/api/playbooks/rules/{_UNKNOWN_ID}",
        json={"clause_type": "liability"},
    )
    assert response.status_code == 404


def test_update_rule_success() -> None:
    rule = _make_rule(clause_type="liability")

    with patch(
        "app.db.repositories.playbook_repo.get_rule",
        new=AsyncMock(return_value=rule),
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        response = client.patch(
            f"/api/playbooks/rules/{_RULE_ID}",
            json={"clause_type": "liability"},
        )

    assert response.status_code == 200
    assert response.json()["clause_type"] == "liability"


# ── Rule delete ───────────────────────────────────────────────────────────────


def test_delete_rule_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(0))
    response = client.delete(f"/api/playbooks/rules/{_UNKNOWN_ID}")
    assert response.status_code == 404


def test_delete_rule_success() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(1))
    mock_session.commit = AsyncMock()
    response = client.delete(f"/api/playbooks/rules/{_RULE_ID}")
    assert response.status_code == 204
