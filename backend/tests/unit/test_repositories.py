"""Unit tests for db repository modules — all DB access is mocked."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.clause import Clause
from app.db.models.contract import Contract, Party
from app.db.repositories import clause_repo, contract_repo, search_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value) -> MagicMock:
    """Mock execute() result suitable for scalar_one_or_none() / scalar_one()."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    mock.scalar_one.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    """Mock execute() result suitable for scalars().all()."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


# ---------------------------------------------------------------------------
# contract_repo tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_contract_found() -> None:
    contract = MagicMock(spec=Contract)
    contract.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(contract)

    result = await contract_repo.get_contract(session, contract.id)

    assert result is contract
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_contract_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await contract_repo.get_contract(session, uuid.uuid4())

    assert result is None
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_contracts_no_filters() -> None:
    contract = MagicMock(spec=Contract)

    session = _make_session()
    count_result = _scalar_result(1)
    list_result = _scalars_all_result([contract])
    # execute called twice: count then list
    session.execute.side_effect = [count_result, list_result]

    items, total = await contract_repo.list_contracts(session)

    assert items == [contract]
    assert total == 1
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_list_contracts_with_status_filter() -> None:
    contract = MagicMock(spec=Contract)

    session = _make_session()
    count_result = _scalar_result(3)
    list_result = _scalars_all_result([contract])
    session.execute.side_effect = [count_result, list_result]

    items, total = await contract_repo.list_contracts(session, status="analyzed")

    assert total == 3
    assert items == [contract]
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_upsert_party_existing() -> None:
    existing_party = MagicMock(spec=Party)
    existing_party.normalized_name = "acme corp"

    session = _make_session()
    session.execute.return_value = _scalar_result(existing_party)
    session.add = MagicMock()

    result = await contract_repo.upsert_party(session, "acme corp", "Acme Corp")

    assert result is existing_party
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_party_new() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)
    session.add = MagicMock()

    result = await contract_repo.upsert_party(session, "new corp", "New Corp")

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, Party)
    assert added.normalized_name == "new corp"
    assert added.display_name == "New Corp"
    assert result is added


# ---------------------------------------------------------------------------
# clause_repo tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_clauses_for_contract() -> None:
    clause_a = MagicMock(spec=Clause)
    clause_a.ordinal = 1
    clause_b = MagicMock(spec=Clause)
    clause_b.ordinal = 2

    session = _make_session()
    session.execute.return_value = _scalars_all_result([clause_a, clause_b])

    contract_id = uuid.uuid4()
    result = await clause_repo.get_clauses_for_contract(session, contract_id)

    assert result == [clause_a, clause_b]
    session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# search_repo tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_text_search_calls_execute() -> None:
    contract = MagicMock(spec=Contract)

    session = _make_session()
    count_result = _scalar_result(5)
    list_result = _scalars_all_result([contract])
    session.execute.side_effect = [count_result, list_result]

    items, total = await search_repo.full_text_search(session, "indemnification")

    assert total == 5
    assert items == [contract]
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_faceted_search_with_query() -> None:
    contract = MagicMock(spec=Contract)

    session = _make_session()
    count_result = _scalar_result(2)
    list_result = _scalars_all_result([contract])
    session.execute.side_effect = [count_result, list_result]

    items, total = await search_repo.faceted_search(
        session,
        status="analyzed",
        q="liability cap",
    )

    assert total == 2
    assert items == [contract]
    assert session.execute.call_count == 2
