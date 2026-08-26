from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import Flag, RiskScore


async def bulk_create_flags(session: AsyncSession, flags: list[Flag]) -> list[Flag]:
    """Persist a list of Flag rows and return them with server-generated ids/timestamps."""
    for f in flags:
        session.add(f)
    await session.flush()
    return flags


async def create_risk_score(session: AsyncSession, row: RiskScore) -> RiskScore:
    """Persist a RiskScore row and return it after flush."""
    session.add(row)
    await session.flush()
    return row


async def get_flags_for_contract(
    session: AsyncSession,
    contract_id: uuid.UUID,
    *,
    flag_type: str | None = None,
    severity: str | None = None,
) -> list[Flag]:
    """Return all flags for a contract, optionally filtered by type or severity."""
    stmt = select(Flag).where(Flag.contract_id == contract_id).order_by(Flag.created_at)
    if flag_type is not None:
        stmt = stmt.where(Flag.flag_type == flag_type)
    if severity is not None:
        stmt = stmt.where(Flag.severity == severity)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_risk_score_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> RiskScore | None:
    """Return the most recent risk score for a contract, or None."""
    result = await session.execute(
        select(RiskScore)
        .where(RiskScore.contract_id == contract_id)
        .order_by(RiskScore.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def delete_flags_for_contract(session: AsyncSession, contract_id: uuid.UUID) -> None:
    """Delete all flags for a contract (used before re-analysis)."""
    await session.execute(delete(Flag).where(Flag.contract_id == contract_id))


async def delete_risk_score_for_contract(session: AsyncSession, contract_id: uuid.UUID) -> None:
    """Delete all risk scores for a contract (used before re-analysis)."""
    await session.execute(delete(RiskScore).where(RiskScore.contract_id == contract_id))
