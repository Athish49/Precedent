from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.clause import Clause


async def get_clauses_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[Clause]:
    """Return all clauses for a contract, ordered by ordinal."""
    result = await session.execute(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.ordinal)
    )
    return list(result.scalars().all())


async def get_clause(session: AsyncSession, clause_id: uuid.UUID) -> Clause | None:
    """Fetch a single Clause by its UUID primary key."""
    result = await session.execute(select(Clause).where(Clause.id == clause_id))
    return result.scalar_one_or_none()
