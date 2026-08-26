"""Obligation and Alert repository — create and query rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.obligation import Alert, Obligation


async def create_obligation(session: AsyncSession, ob: Obligation) -> Obligation:
    """Persist a new Obligation row and return it after flush."""
    session.add(ob)
    await session.flush()
    return ob


async def get_obligations_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[Obligation]:
    """Return all obligations for a contract, oldest first."""
    result = await session.execute(
        select(Obligation)
        .where(Obligation.contract_id == contract_id)
        .order_by(Obligation.created_at)
    )
    return list(result.scalars().all())


async def create_alert(session: AsyncSession, alert: Alert) -> Alert:
    """Persist a new Alert row and return it after flush."""
    session.add(alert)
    await session.flush()
    return alert


async def get_alerts_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[Alert]:
    """Return all alerts for a contract, newest first."""
    result = await session.execute(
        select(Alert)
        .where(Alert.contract_id == contract_id)
        .order_by(Alert.fired_at.desc())
    )
    return list(result.scalars().all())


async def get_all_alerts(
    session: AsyncSession,
    *,
    alert_type: str | None = None,
    acknowledged: bool | None = None,
) -> list[Alert]:
    """Return all alerts with optional filters, newest first."""
    stmt = select(Alert).order_by(Alert.fired_at.desc())
    if alert_type is not None:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged == acknowledged)
    result = await session.execute(stmt)
    return list(result.scalars().all())
