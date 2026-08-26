from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_intelligence(session: AsyncSession) -> list[dict]:
    sql = text("SELECT * FROM v_contract_intelligence ORDER BY created_at DESC")
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result]


async def get_portfolio_risk(session: AsyncSession) -> dict:
    result = await session.execute(text("SELECT * FROM v_portfolio_risk"))
    row = result.first()
    return dict(row._mapping) if row else {}


async def get_contract_value(session: AsyncSession) -> list[dict]:
    result = await session.execute(text("SELECT * FROM v_contract_value ORDER BY created_at DESC"))
    return [dict(row._mapping) for row in result]


async def get_tabular(
    session: AsyncSession,
    columns: list[str] | None = None,
) -> list[dict]:
    result = await session.execute(text("SELECT * FROM v_tabular_review ORDER BY created_at DESC"))
    rows = [dict(row._mapping) for row in result]
    if columns:
        allowed = set(columns)
        rows = [{k: v for k, v in row.items() if k in allowed} for row in rows]
    return rows


async def get_renewals(session: AsyncSession) -> list[dict]:
    sql = text("SELECT * FROM v_renewal_dashboard ORDER BY expiry_date ASC NULLS LAST")
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result]
