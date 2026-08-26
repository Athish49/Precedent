"""S2 API — contract analysis endpoints (T-044).

Route ordering: GET /analysis/{contract_id}/flags must be declared before
GET /analysis/{contract_id} to avoid FastAPI treating "flags" as a UUID segment
(it won't since UUIDs are typed, but explicit ordering mirrors the playbooks pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.analysis import AnalysisResult, FlagDTO
from app.services.contract_analysis import service

router = APIRouter(tags=["analysis"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.post("/analysis/{contract_id}", response_model=AnalysisResult, status_code=200)
async def run_analysis(contract_id: uuid.UUID, session: SessionDep) -> AnalysisResult:
    """Trigger S2 analysis for a contract.

    Runs Layer 1 structural checks and Layer 2 LLM content analysis, then
    persists flags and a risk score. Re-running replaces prior results.
    """
    return await service.analyze(session, contract_id)


@router.get("/analysis/{contract_id}/flags", response_model=list[FlagDTO])
async def get_flags(
    contract_id: uuid.UUID,
    session: SessionDep,
    flag_type: str | None = Query(None, description="Filter by flag type"),
    severity: str | None = Query(None, description="Filter by severity"),
) -> list[FlagDTO]:
    """Return flags for a contract, optionally filtered by type or severity."""
    result = await service.get_analysis(session, contract_id)
    flags = result.flags
    if flag_type is not None:
        flags = [f for f in flags if f.flag_type == flag_type]
    if severity is not None:
        flags = [f for f in flags if f.severity == severity]
    return flags


@router.get("/analysis/{contract_id}", response_model=AnalysisResult)
async def get_analysis(contract_id: uuid.UUID, session: SessionDep) -> AnalysisResult:
    """Return the stored analysis result for a contract.

    Returns empty flags and null risk before any analysis has been run.
    """
    return await service.get_analysis(session, contract_id)
