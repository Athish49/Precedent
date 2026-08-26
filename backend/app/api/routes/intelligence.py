from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.intelligence import (
    ClauseRefDTO,
    EasyPromptRequest,
    EasyPromptResponse,
    NavigationIndexDTO,
    QARequest,
    QAResponse,
    RedlineSummaryResponse,
    ResearchRequest,
    ResearchResponse,
    SummaryResponse,
)
from app.services.intelligence import easy_prompt as easy_prompt_service
from app.services.intelligence import navigation as navigation_service
from app.services.intelligence import qa as qa_service
from app.services.intelligence import research as research_service
from app.services.intelligence import summarize as summarize_service

router = APIRouter(tags=["intelligence"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.post("/intelligence/{contract_id}/summarize", response_model=SummaryResponse)
async def summarize(contract_id: uuid.UUID, session: SessionDep) -> SummaryResponse:
    result = await summarize_service.summarize_contract(session, contract_id)
    return SummaryResponse(summary=result.summary)


@router.post(
    "/intelligence/{contract_id}/summarize-redlines",
    response_model=RedlineSummaryResponse,
)
async def summarize_redlines(contract_id: uuid.UUID, session: SessionDep) -> RedlineSummaryResponse:
    result = await summarize_service.summarize_redlines(session, contract_id)
    return RedlineSummaryResponse(summary=result.summary, clause_type=result.clause_type)


@router.post("/intelligence/{contract_id}/qa", response_model=QAResponse)
async def qa(contract_id: uuid.UUID, body: QARequest, session: SessionDep) -> QAResponse:
    result = await qa_service.answer_question(session, contract_id, body.question)
    return QAResponse(answer=result.answer, citations=result.citations, cached=result.cached)


@router.post("/intelligence/{contract_id}/easy-prompt", response_model=EasyPromptResponse)
async def easy_prompt(
    contract_id: uuid.UUID, body: EasyPromptRequest, session: SessionDep
) -> EasyPromptResponse:
    result = await easy_prompt_service.generate_easy_prompt(
        session, contract_id, body.user_request
    )
    return EasyPromptResponse(structured_prompt=result.structured_prompt, route=result.route)


@router.post("/intelligence/{contract_id}/research", response_model=ResearchResponse)
async def research(
    contract_id: uuid.UUID, body: ResearchRequest, session: SessionDep
) -> ResearchResponse:
    result = await research_service.synthesize_research(
        session, contract_id, body.question, body.search_results
    )
    return ResearchResponse(answer=result.answer, sources=result.sources)


@router.get("/intelligence/{contract_id}/navigation", response_model=NavigationIndexDTO)
async def navigation(contract_id: uuid.UUID, session: SessionDep) -> NavigationIndexDTO:
    nav = await navigation_service.build_navigation_index(session, contract_id)
    index_dto = {
        ct: [
            ClauseRefDTO(
                clause_id=r.clause_id,
                ordinal=r.ordinal,
                heading_text=r.heading_text,
                char_start=r.char_start,
                char_end=r.char_end,
            )
            for r in refs
        ]
        for ct, refs in nav.index.items()
    }
    return NavigationIndexDTO(contract_id=nav.contract_id, index=index_dto, toc=nav.toc)
