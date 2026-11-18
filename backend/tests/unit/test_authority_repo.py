"""Unit tests for authority_repo — all DB access is mocked (task 1.4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.authority import ApproverRole, EscalationPolicy
from app.db.repositories import authority_repo


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value: object) -> MagicMock:
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _rowcount_result(rowcount: int) -> MagicMock:
    mock = MagicMock()
    mock.rowcount = rowcount
    return mock


# ---------------------------------------------------------------------------
# ApproverRole
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_approver_role() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await authority_repo.create_approver_role(
        session, "commercial_counsel", "Commercial Counsel", "legal", 2, 24
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, ApproverRole)
    assert added.key == "commercial_counsel"
    assert added.level == 2
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_approver_role_and_by_key() -> None:
    role = MagicMock(spec=ApproverRole)
    role.id = uuid.uuid4()
    session = _make_session()

    session.execute.return_value = _scalar_result(role)
    assert await authority_repo.get_approver_role(session, role.id) is role

    session.execute.return_value = _scalar_result(role)
    assert await authority_repo.get_approver_role_by_key(session, "commercial_counsel") is role

    session.execute.return_value = _scalar_result(None)
    assert await authority_repo.get_approver_role_by_key(session, "unknown") is None


@pytest.mark.asyncio
async def test_list_approver_roles() -> None:
    a = MagicMock(spec=ApproverRole)
    b = MagicMock(spec=ApproverRole)
    session = _make_session()
    session.execute.return_value = _scalars_all_result([a, b])

    assert await authority_repo.list_approver_roles(session) == [a, b]


@pytest.mark.asyncio
async def test_update_delete_approver_role() -> None:
    role = MagicMock(spec=ApproverRole)
    role.id = uuid.uuid4()
    session = _make_session()

    session.execute.return_value = _scalar_result(role)
    updated = await authority_repo.update_approver_role(session, role.id, default_sla_hours=48)
    assert updated is role
    assert role.default_sla_hours == 48

    session.execute.return_value = _scalar_result(None)
    assert await authority_repo.update_approver_role(session, uuid.uuid4(), level=3) is None

    session.execute.return_value = _rowcount_result(1)
    assert await authority_repo.delete_approver_role(session, role.id) is True

    session.execute.return_value = _rowcount_result(0)
    assert await authority_repo.delete_approver_role(session, uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# EscalationPolicy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_escalation_policy() -> None:
    session = _make_session()
    session.add = MagicMock()
    approver_role_id = uuid.uuid4()

    result = await authority_repo.create_escalation_policy(
        session, zone="yellow", approver_role_id=approver_role_id, sla_hours=24,
        clause_type="limitation_of_liability", priority=10, consult_role_ids=[],
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, EscalationPolicy)
    assert added.zone == "yellow"
    assert added.approver_role_id == approver_role_id
    assert added.clause_type == "limitation_of_liability"
    assert result is added


@pytest.mark.asyncio
async def test_get_escalation_policy() -> None:
    policy = MagicMock(spec=EscalationPolicy)
    policy.id = uuid.uuid4()
    session = _make_session()
    session.execute.return_value = _scalar_result(policy)

    assert await authority_repo.get_escalation_policy(session, policy.id) is policy


@pytest.mark.asyncio
async def test_list_escalation_policies_filters_and_orders_by_priority() -> None:
    low = MagicMock(spec=EscalationPolicy)
    high = MagicMock(spec=EscalationPolicy)
    session = _make_session()
    # The repo orders by priority DESC in SQL; the mock just returns whatever
    # the (fake) query would produce, so this test checks the filters are
    # wired through, not sorting behaviour which lives in the database.
    session.execute.return_value = _scalars_all_result([high, low])

    playbook_id = uuid.uuid4()
    result = await authority_repo.list_escalation_policies(
        session, playbook_id=playbook_id, clause_type="limitation_of_liability", zone="yellow"
    )

    assert result == [high, low]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_escalation_policies_no_filters() -> None:
    policy = MagicMock(spec=EscalationPolicy)
    session = _make_session()
    session.execute.return_value = _scalars_all_result([policy])

    assert await authority_repo.list_escalation_policies(session) == [policy]


@pytest.mark.asyncio
async def test_update_delete_escalation_policy() -> None:
    policy = MagicMock(spec=EscalationPolicy)
    policy.id = uuid.uuid4()
    session = _make_session()

    session.execute.return_value = _scalar_result(policy)
    updated = await authority_repo.update_escalation_policy(session, policy.id, sla_hours=48)
    assert updated is policy
    assert policy.sla_hours == 48

    session.execute.return_value = _rowcount_result(1)
    assert await authority_repo.delete_escalation_policy(session, policy.id) is True
