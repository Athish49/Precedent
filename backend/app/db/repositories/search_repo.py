from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contract import Contract, ContractMetadata


def _build_facet_filters(
    stmt,
    *,
    contract_type: str | None,
    counterparty_id: uuid.UUID | None,
    status: str | None,
    effective_date_from: date | None,
    effective_date_to: date | None,
    q: str | None,
):
    """Apply optional WHERE clauses for faceted + FTS filtering."""
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
    if q is not None:
        fts_filter = text(
            "to_tsvector('english', canonical_text) @@ plainto_tsquery('english', :q)"
        ).bindparams(q=q)
        stmt = stmt.where(fts_filter)
    return stmt


async def full_text_search(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Contract], int]:
    """Full-text search on contract.canonical_text using tsvector.
    Uses: WHERE to_tsvector('english', canonical_text) @@ plainto_tsquery('english', :query)
    Returns (items, total_count).
    """
    fts_filter = text(
        "to_tsvector('english', canonical_text) @@ plainto_tsquery('english', :q)"
    ).bindparams(q=query)

    base = select(Contract).where(fts_filter)

    count_stmt = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    list_stmt = base.limit(limit).offset(offset)
    list_result = await session.execute(list_stmt)
    items = list(list_result.scalars().all())

    return items, total


async def faceted_search(
    session: AsyncSession,
    *,
    contract_type: str | None = None,
    counterparty_id: uuid.UUID | None = None,
    status: str | None = None,
    effective_date_from: date | None = None,
    effective_date_to: date | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Contract], int]:
    """Combined faceted + optional full-text search. Returns (items, total_count)."""
    base = select(Contract).outerjoin(ContractMetadata, Contract.id == ContractMetadata.contract_id)
    base = _build_facet_filters(
        base,
        contract_type=contract_type,
        counterparty_id=counterparty_id,
        status=status,
        effective_date_from=effective_date_from,
        effective_date_to=effective_date_to,
        q=q,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    list_stmt = base.limit(limit).offset(offset)
    list_result = await session.execute(list_stmt)
    items = list(list_result.scalars().all())

    return items, total
