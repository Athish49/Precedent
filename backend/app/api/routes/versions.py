from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.versions import VersionDiffResponse, VersionSummaryRequest, VersionSummaryResponse
from app.workflows import version_comparison, version_semantic_summary

router = APIRouter(tags=["versions"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.post("/versions/diff/summary", response_model=VersionSummaryResponse)
async def summarize_diff(
    body: VersionSummaryRequest,
    session: SessionDep,
) -> VersionSummaryResponse:
    from dataclasses import asdict

    result = await version_semantic_summary.summarize_diff(
        session, body.contract_id, body.v_a, body.v_b
    )
    return VersionSummaryResponse.model_validate(asdict(result))


@router.get("/versions/diff", response_model=VersionDiffResponse)
async def diff_versions(
    contract_id: uuid.UUID,
    v_a: uuid.UUID,
    v_b: uuid.UUID,
    session: SessionDep,
) -> VersionDiffResponse:
    result = await version_comparison.compare_versions(session, contract_id, v_a, v_b)
    return VersionDiffResponse.model_validate(asdict(result))
