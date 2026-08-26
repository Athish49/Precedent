"""Unit tests for playbook_repo — all DB access is mocked."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.playbook import Playbook, PlaybookRule
from app.db.repositories import playbook_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value: object) -> MagicMock:
    """Mock execute() result suitable for scalar_one_or_none()."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    """Mock execute() result suitable for scalars().all()."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _rowcount_result(rowcount: int) -> MagicMock:
    """Mock execute() result with rowcount attribute."""
    mock = MagicMock()
    mock.rowcount = rowcount
    return mock


# ---------------------------------------------------------------------------
# Playbook tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_playbook() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await playbook_repo.create_playbook(session, "NDA Playbook", "nda", precedence=5)

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, Playbook)
    assert added.name == "NDA Playbook"
    assert added.practice_area == "nda"
    assert added.precedence == 5
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_playbook_found() -> None:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(pb)

    result = await playbook_repo.get_playbook(session, pb.id)

    assert result is pb
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_playbook(session, uuid.uuid4())

    assert result is None
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_playbooks() -> None:
    pb1 = MagicMock(spec=Playbook)
    pb2 = MagicMock(spec=Playbook)

    session = _make_session()
    session.execute.return_value = _scalars_all_result([pb1, pb2])

    result = await playbook_repo.list_playbooks(session)

    assert result == [pb1, pb2]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_playbook() -> None:
    pb_id = uuid.uuid4()
    pb = MagicMock(spec=Playbook)
    pb.id = pb_id

    session = _make_session()
    session.execute.return_value = _scalar_result(pb)

    result = await playbook_repo.update_playbook(session, pb_id, name="Updated Name", precedence=10)

    assert result is pb
    assert pb.name == "Updated Name"
    assert pb.precedence == 10
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.update_playbook(session, uuid.uuid4(), name="Ghost")

    assert result is None
    session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_delete_playbook_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(1)

    result = await playbook_repo.delete_playbook(session, uuid.uuid4())

    assert result is True
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(0)

    result = await playbook_repo.delete_playbook(session, uuid.uuid4())

    assert result is False


# ---------------------------------------------------------------------------
# PlaybookRule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule() -> None:
    session = _make_session()
    session.add = MagicMock()

    playbook_id = uuid.uuid4()
    result = await playbook_repo.create_rule(
        session,
        playbook_id=playbook_id,
        clause_type="indemnification",
        preferred_language="Each party shall indemnify the other.",
        required=True,
        risk_weight=2.0,
    )

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, PlaybookRule)
    assert added.playbook_id == playbook_id
    assert added.clause_type == "indemnification"
    assert added.preferred_language == "Each party shall indemnify the other."
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_rule_found() -> None:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(rule)

    result = await playbook_repo.get_rule(session, rule.id)

    assert result is rule
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_rule_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_rule(session, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_list_rules() -> None:
    playbook_id = uuid.uuid4()
    rule1 = MagicMock(spec=PlaybookRule)
    rule2 = MagicMock(spec=PlaybookRule)

    session = _make_session()
    session.execute.return_value = _scalars_all_result([rule1, rule2])

    result = await playbook_repo.list_rules(session, playbook_id)

    assert result == [rule1, rule2]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_rule() -> None:
    rule_id = uuid.uuid4()
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id

    session = _make_session()
    session.execute.return_value = _scalar_result(rule)

    result = await playbook_repo.update_rule(
        session, rule_id, clause_type="liability", required=False
    )

    assert result is rule
    assert rule.clause_type == "liability"
    assert rule.required is False
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_rule_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(1)

    result = await playbook_repo.delete_rule(session, uuid.uuid4())

    assert result is True


@pytest.mark.asyncio
async def test_delete_rule_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(0)

    result = await playbook_repo.delete_rule(session, uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_get_rules_by_clause_type() -> None:
    playbook_id = uuid.uuid4()
    rule = MagicMock(spec=PlaybookRule)
    rule.clause_type = "indemnification"

    session = _make_session()
    session.execute.return_value = _scalars_all_result([rule])

    result = await playbook_repo.get_rules_by_clause_type(session, playbook_id, "indemnification")

    assert result == [rule]
    session.execute.assert_called_once()
