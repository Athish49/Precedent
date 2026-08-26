"""Redline repository — create and query redline rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.redline import Redline


async def create_redline(session: AsyncSession, redline: Redline) -> Redline:
    """Persist a new Redline row and return it after flush."""
    session.add(redline)
    await session.flush()
    return redline


async def get_redline(session: AsyncSession, redline_id: uuid.UUID) -> Redline | None:
    """Return a single Redline by primary key, or None if not found."""
    result = await session.execute(
        select(Redline).where(Redline.id == redline_id)
    )
    return result.scalar_one_or_none()


async def get_redlines_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[Redline]:
    """Return all redlines for a contract, oldest first."""
    result = await session.execute(
        select(Redline)
        .where(Redline.contract_id == contract_id)
        .order_by(Redline.created_at)
    )
    return list(result.scalars().all())


async def update_redline(session: AsyncSession, redline: Redline) -> Redline:
    """Flush a modified Redline row. Caller mutates fields before calling."""
    await session.flush()
    return redline
