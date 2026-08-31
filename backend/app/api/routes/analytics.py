from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.analytics import (
    ContractIntelligenceRow,
    ContractValueRow,
    PortfolioRiskResponse,
    RenewalDashboardRow,
    TabularReviewRow,
)
from app.services.analytics import service as analytics_service

router = APIRouter(tags=["analytics"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.get("/analytics/intelligence", response_model=list[ContractIntelligenceRow])
async def get_intelligence(session: SessionDep) -> list[ContractIntelligenceRow]:
    rows = await analytics_service.get_intelligence(session)
    return [ContractIntelligenceRow.model_validate(r) for r in rows]


@router.get("/analytics/portfolio-risk", response_model=PortfolioRiskResponse)
async def get_portfolio_risk(session: SessionDep) -> PortfolioRiskResponse:
    data = await analytics_service.get_portfolio_risk(session)
    if not data or data.get("total_contracts") == 0:
        return PortfolioRiskResponse(
            total_contracts=int(data["total_contracts"]) if data else 0,
            total_high_flags=0, total_medium_flags=0,
            total_low_flags=0, total_flags=0, avg_weighted_flag_score=None,
            avg_risk_score=None, contracts_high_severity=0,
            contracts_medium_severity=0, contracts_low_severity=0,
        )
    # Coalesce nullable int fields that SUM() returns as None on empty partitions
    int_fields = ("total_high_flags", "total_medium_flags", "total_low_flags",
                  "total_flags", "contracts_high_severity",
                  "contracts_medium_severity", "contracts_low_severity")
    for field in int_fields:
        if data.get(field) is None:
            data[field] = 0
    return PortfolioRiskResponse.model_validate(data)


@router.get("/analytics/contract-value", response_model=list[ContractValueRow])
async def get_contract_value(session: SessionDep) -> list[ContractValueRow]:
    rows = await analytics_service.get_contract_value(session)
    return [ContractValueRow.model_validate(r) for r in rows]


@router.get("/analytics/tabular", response_model=list[TabularReviewRow])
async def get_tabular(
    session: SessionDep,
    columns: list[str] | None = Query(None),
) -> list[TabularReviewRow]:
    rows = await analytics_service.get_tabular(session, columns=columns)
    return [TabularReviewRow.model_validate(r) for r in rows]


@router.get("/analytics/renewals", response_model=list[RenewalDashboardRow])
async def get_renewals(session: SessionDep) -> list[RenewalDashboardRow]:
    rows = await analytics_service.get_renewals(session)
    return [RenewalDashboardRow.model_validate(r) for r in rows]
