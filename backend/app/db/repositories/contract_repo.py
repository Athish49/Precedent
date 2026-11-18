from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contract import Contract, ContractMetadata, Party


async def get_contract(session: AsyncSession, contract_id: uuid.UUID) -> Contract | None:
    """Fetch a Contract by id, or None if not found."""
    result = await session.execute(select(Contract).where(Contract.id == contract_id))
    return result.scalar_one_or_none()


async def get_contract_with_metadata(
    session: AsyncSession, contract_id: uuid.UUID
) -> tuple[Contract, ContractMetadata | None] | None:
    """Fetch Contract + its ContractMetadata in one query (LEFT OUTER JOIN).
    Returns None if contract doesn't exist.
    """
    stmt = (
        select(Contract, ContractMetadata)
        .outerjoin(ContractMetadata, Contract.id == ContractMetadata.contract_id)
        .where(Contract.id == contract_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    contract, metadata = row
    return (contract, metadata)


def _build_contract_filters(
    stmt,
    *,
    contract_type: str | None,
    counterparty_id: uuid.UUID | None,
    status: str | None,
    effective_date_from: date | None,
    effective_date_to: date | None,
):
    """Apply optional WHERE clauses to a statement (shared by list + count queries)."""
    if contract_type is not None:
        stmt = stmt.where(Contract.contract_type == contract_type)
    if counterparty_id is not None:
        stmt = stmt.where(Contract.counterparty_id == counterparty_id)
    if status is not None:
        stmt = stmt.where(Contract.status == status)
    if effective_date_from is not None:
        stmt = stmt.where(ContractMetadata.effective_date >= effective_date_from)
    if effective_date_to is not None:
        stmt = stmt.where(ContractMetadata.effective_date <= effective_date_to)
    return stmt


async def list_contracts(
    session: AsyncSession,
    *,
    contract_type: str | None = None,
    counterparty_id: uuid.UUID | None = None,
    status: str | None = None,
    effective_date_from: date | None = None,
    effective_date_to: date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Contract], int]:
    """Faceted list with optional filters. Returns (items, total_count).
    Filters on contract columns + contract_metadata date columns.
    total_count is the count with same filters applied (without pagination).
    """
    base = select(Contract).outerjoin(ContractMetadata, Contract.id == ContractMetadata.contract_id)
    base = _build_contract_filters(
        base,
        contract_type=contract_type,
        counterparty_id=counterparty_id,
        status=status,
        effective_date_from=effective_date_from,
        effective_date_to=effective_date_to,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    list_stmt = base.limit(limit).offset(offset)
    list_result = await session.execute(list_stmt)
    items = list(list_result.scalars().all())

    return items, total


async def update_contract(session: AsyncSession, contract_id: uuid.UUID, **kwargs: object) -> Contract | None:
    """Partially update a Contract row (task 4.1, item 5: PATCH
    /api/repository/contracts/{id}). Returns None if the contract does not
    exist; does not commit (caller's responsibility).
    """
    contract = await get_contract(session, contract_id)
    if contract is None:
        return None
    for field, value in kwargs.items():
        setattr(contract, field, value)
    await session.flush()
    return contract


async def upsert_party(
    session: AsyncSession, normalized_name: str, display_name: str
) -> Party:
    """Insert party if not exists (by normalized_name), else return existing."""
    result = await session.execute(
        select(Party).where(Party.normalized_name == normalized_name)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    party = Party(normalized_name=normalized_name, display_name=display_name)
    session.add(party)
    return party
