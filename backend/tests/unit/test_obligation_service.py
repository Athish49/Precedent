"""Tests for T-080 S8 obligation extraction service."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.api.errors import AppError
from app.core.llm.schemas.obligation import ObligationItem, ObligationOut
from app.db.models.obligation import Obligation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contract(title: str = "Service Agreement", contract_type: str = "saas") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.title = title
    c.contract_type = contract_type
    c.paper_origin = "own"
    return c


def _clause(ordinal: int, clause_type: str = "payment", char_start: int = 0, char_end: int = 100) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.ordinal = ordinal
    c.clause_type = clause_type
    c.text = f"Clause {ordinal} text for {clause_type}."
    c.char_start = char_start
    c.char_end = char_end
    return c


def _obligation_item(
    clause_ordinal: int = 1,
    deadline: str | None = "2025-12-31",
) -> ObligationItem:
    return ObligationItem(
        commitment="Pay the monthly invoice",
        owner="Customer",
        deadline=deadline,
        deliverable="Payment confirmation",
        clause_ordinal=clause_ordinal,
        excerpt="Customer shall pay within 30 days of invoice.",
    )


def _obligation_out(items: list[ObligationItem] | None = None) -> ObligationOut:
    return ObligationOut(obligations=items or [_obligation_item()])


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


def _persisted_obligation(contract_id: uuid.UUID) -> Obligation:
    ob = MagicMock(spec=Obligation)
    ob.id = uuid.uuid4()
    ob.contract_id = contract_id
    ob.commitment = "Pay the monthly invoice"
    ob.owner = "Customer"
    ob.deadline = date(2025, 12, 31)
    ob.deliverable = "Payment confirmation"
    ob.char_start = 0
    ob.char_end = 100
    ob.status = "open"
    return ob


# ---------------------------------------------------------------------------
# Test 1: Extract happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_happy_path() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    contract.id = contract_id
    clause = _clause(ordinal=1)
    llm_result = _obligation_out()
    persisted = _persisted_obligation(contract_id)

    with (
        patch("app.services.obligations.service.contract_repo") as mock_cr,
        patch("app.services.obligations.service.clause_repo") as mock_cl,
        patch("app.services.obligations.service.gateway") as mock_gw,
        patch("app.services.obligations.service.obligation_repo") as mock_or,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[clause])
        mock_gw.call_structured = MagicMock(return_value=llm_result)
        mock_or.create_obligation = AsyncMock(return_value=persisted)

        from app.services.obligations import service
        result = await service.extract(_mock_session(), contract_id)

    mock_gw.call_structured.assert_called_once()
    call_args = mock_gw.call_structured.call_args
    assert call_args[0][0] == "obligation_extract"

    assert len(result) == 1
    assert result[0] is persisted


# ---------------------------------------------------------------------------
# Test 2: Contract not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_contract_not_found() -> None:
    with patch("app.services.obligations.service.contract_repo") as mock_cr:
        mock_cr.get_contract = AsyncMock(return_value=None)

        from app.services.obligations import service
        with pytest.raises(AppError) as exc_info:
            await service.extract(_mock_session(), uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


# ---------------------------------------------------------------------------
# Test 3: Deadline parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_deadline_parsing() -> None:
    from app.services.obligations.service import _parse_date

    assert _parse_date("2025-12-31") == date(2025, 12, 31)
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("not-a-date") is None
    assert _parse_date("2025-99-99") is None


# ---------------------------------------------------------------------------
# Test 4: Citation resolution — ordinal maps to correct clause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_citation_resolution() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    contract.id = contract_id
    clause1 = _clause(ordinal=1, char_start=0, char_end=50)
    clause2 = _clause(ordinal=2, char_start=51, char_end=200)

    item = _obligation_item(clause_ordinal=2)
    llm_result = ObligationOut(obligations=[item])
    captured: list[Obligation] = []

    async def capture_obligation(session, ob):
        captured.append(ob)
        return ob

    with (
        patch("app.services.obligations.service.contract_repo") as mock_cr,
        patch("app.services.obligations.service.clause_repo") as mock_cl,
        patch("app.services.obligations.service.gateway") as mock_gw,
        patch("app.services.obligations.service.obligation_repo") as mock_or,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[clause1, clause2])
        mock_gw.call_structured = MagicMock(return_value=llm_result)
        mock_or.create_obligation = AsyncMock(side_effect=capture_obligation)

        from app.services.obligations import service
        await service.extract(_mock_session(), contract_id)

    assert len(captured) == 1
    assert captured[0].char_start == 51
    assert captured[0].char_end == 200


# ---------------------------------------------------------------------------
# Test 5: Unresolved ordinal → char_start/char_end are None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_unresolved_ordinal() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    contract.id = contract_id
    clause1 = _clause(ordinal=1)

    # ordinal 99 does not exist in clauses
    item = _obligation_item(clause_ordinal=99)
    llm_result = ObligationOut(obligations=[item])
    captured: list[Obligation] = []

    async def capture_obligation(session, ob):
        captured.append(ob)
        return ob

    with (
        patch("app.services.obligations.service.contract_repo") as mock_cr,
        patch("app.services.obligations.service.clause_repo") as mock_cl,
        patch("app.services.obligations.service.gateway") as mock_gw,
        patch("app.services.obligations.service.obligation_repo") as mock_or,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[clause1])
        mock_gw.call_structured = MagicMock(return_value=llm_result)
        mock_or.create_obligation = AsyncMock(side_effect=capture_obligation)

        from app.services.obligations import service
        await service.extract(_mock_session(), contract_id)

    assert len(captured) == 1
    assert captured[0].char_start is None
    assert captured[0].char_end is None


# ---------------------------------------------------------------------------
# Test 6: Re-entrant — delete executed before insert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_reentrant_deletes_before_insert() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    contract.id = contract_id
    clause = _clause(ordinal=1)
    llm_result = _obligation_out()
    persisted = _persisted_obligation(contract_id)
    call_order: list[str] = []

    session = _mock_session()

    async def track_execute(stmt):
        call_order.append("delete")

    async def track_create(sess, ob):
        call_order.append("create")
        return persisted

    session.execute = AsyncMock(side_effect=track_execute)

    with (
        patch("app.services.obligations.service.contract_repo") as mock_cr,
        patch("app.services.obligations.service.clause_repo") as mock_cl,
        patch("app.services.obligations.service.gateway") as mock_gw,
        patch("app.services.obligations.service.obligation_repo") as mock_or,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[clause])
        mock_gw.call_structured = MagicMock(return_value=llm_result)
        mock_or.create_obligation = AsyncMock(side_effect=track_create)

        from app.services.obligations import service
        await service.extract(session, contract_id)

    assert call_order[0] == "delete", "delete must happen before create"
    assert "create" in call_order
    assert call_order.index("delete") < call_order.index("create")
