"""S8 Obligations API — extract/monitor/compliance/alerts endpoints (T-083)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.models.obligation import Alert
from app.db.repositories import obligation_repo
from app.schemas.obligations import (
    AlertDTO,
    ComplianceCheckResponse,
    MonitorRunResponse,
    ObligationDTO,
)
from app.services.obligations import monitor as monitor_service
from app.services.obligations import renewal as renewal_service
from app.services.obligations import service as obligation_service

router = APIRouter(tags=["obligations"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


# Literal routes MUST come before /{contract_id} to avoid UUID parsing conflicts


@router.post("/obligations/monitor/run", response_model=MonitorRunResponse)
async def run_monitor(session: SessionDep) -> MonitorRunResponse:
    result = await monitor_service.run_monitor(session)
    await session.commit()
    return MonitorRunResponse(
        deadline_alerts=len(result.deadline_alerts),
        renewal_alerts=len(result.renewal_alerts),
        total=result.total,
    )


@router.get("/obligations/alerts", response_model=list[AlertDTO])
async def list_alerts(
    session: SessionDep,
    alert_type: str | None = Query(None),
    acknowledged: bool | None = Query(None),
) -> list[AlertDTO]:
    alerts = await obligation_repo.get_all_alerts(
        session, alert_type=alert_type, acknowledged=acknowledged
    )
    return [AlertDTO.model_validate(a) for a in alerts]


@router.post("/obligations/alerts/{alert_id}/ack", response_model=AlertDTO)
async def acknowledge_alert(alert_id: uuid.UUID, session: SessionDep) -> AlertDTO:
    result = await session.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise AppError(404, "alert_not_found", f"Alert {alert_id} not found")
    alert.acknowledged = True
    await session.flush()
    await session.commit()
    return AlertDTO.model_validate(alert)


@router.post("/obligations/{contract_id}/extract", response_model=list[ObligationDTO])
async def extract_obligations(contract_id: uuid.UUID, session: SessionDep) -> list[ObligationDTO]:
    obligations = await obligation_service.extract(session, contract_id)
    return [ObligationDTO.model_validate(ob) for ob in obligations]


@router.get("/obligations/{contract_id}", response_model=list[ObligationDTO])
async def get_obligations(contract_id: uuid.UUID, session: SessionDep) -> list[ObligationDTO]:
    obligations = await obligation_service.get_obligations(session, contract_id)
    return [ObligationDTO.model_validate(ob) for ob in obligations]


@router.post("/obligations/{contract_id}/compliance-check", response_model=ComplianceCheckResponse)
async def compliance_check(contract_id: uuid.UUID, session: SessionDep) -> ComplianceCheckResponse:
    result = await renewal_service.check_compliance(session, contract_id)
    return ComplianceCheckResponse(
        compliance_pass=result.compliance_pass,
        compliance_issues=result.compliance_issues,
        recommendation=result.recommendation,
        rationale=result.rationale,
    )
