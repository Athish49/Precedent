from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.drafting import (
    DraftClauseRequest,
    DraftDocumentRequest,
    DraftMemoRequest,
    DraftPrecedentRequest,
    DraftResponse,
)
from app.services.drafting import service as drafting_service

router = APIRouter(tags=["drafting"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.post("/drafting/clause", response_model=DraftResponse, status_code=200)
async def draft_clause(body: DraftClauseRequest, session: SessionDep) -> DraftResponse:
    result = await drafting_service.draft_clause(
        session,
        body.clause_type,
        context=body.context,
        instruction=body.instruction,
        preferred_language=body.preferred_language,
    )
    return DraftResponse(text=result.text, source=result.source)


@router.post("/drafting/document", response_model=DraftResponse, status_code=200)
async def draft_document(body: DraftDocumentRequest, session: SessionDep) -> DraftResponse:
    result = await drafting_service.draft_document(
        session, body.template, body.variables, polish=body.polish
    )
    return DraftResponse(text=result.text, source=result.source)


@router.post("/drafting/precedent", response_model=DraftResponse, status_code=200)
async def draft_precedent(body: DraftPrecedentRequest, session: SessionDep) -> DraftResponse:
    result = await drafting_service.draft_precedent(
        session, body.clause_type, context=body.context
    )
    return DraftResponse(text=result.text, source=result.source)


@router.post("/drafting/memo", response_model=DraftResponse, status_code=200)
async def draft_memo(body: DraftMemoRequest, session: SessionDep) -> DraftResponse:
    result = await drafting_service.draft_memo(body.context)
    return DraftResponse(text=result.text, source=result.source)
