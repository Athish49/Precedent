from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import qualified

# The analytics views live in the project schema. Each query names it
# explicitly; nothing here relies on the session search path.
_V_INTELLIGENCE = qualified("v_contract_intelligence")
_V_PORTFOLIO_RISK = qualified("v_portfolio_risk")
_V_CONTRACT_VALUE = qualified("v_contract_value")
_V_TABULAR_REVIEW = qualified("v_tabular_review")
_V_RENEWAL_DASHBOARD = qualified("v_renewal_dashboard")


async def get_intelligence(session: AsyncSession) -> list[dict]:
    sql = text(f"SELECT * FROM {_V_INTELLIGENCE} ORDER BY created_at DESC")
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result]


async def get_portfolio_risk(session: AsyncSession) -> dict:
    result = await session.execute(text(f"SELECT * FROM {_V_PORTFOLIO_RISK}"))
    row = result.first()
    return dict(row._mapping) if row else {}


async def get_contract_value(session: AsyncSession) -> list[dict]:
    sql = text(f"SELECT * FROM {_V_CONTRACT_VALUE} ORDER BY created_at DESC")
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result]


async def get_tabular(
    session: AsyncSession,
    columns: list[str] | None = None,
) -> list[dict]:
    sql = text(f"SELECT * FROM {_V_TABULAR_REVIEW} ORDER BY created_at DESC")
    result = await session.execute(sql)
    rows = [dict(row._mapping) for row in result]
    if columns:
        allowed = set(columns)
        rows = [{k: v for k, v in row.items() if k in allowed} for row in rows]
    return rows


async def get_renewals(session: AsyncSession) -> list[dict]:
    sql = text(f"SELECT * FROM {_V_RENEWAL_DASHBOARD} ORDER BY expiry_date ASC NULLS LAST")
    result = await session.execute(sql)
    return [dict(row._mapping) for row in result]
