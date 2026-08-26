"""S3 API — redline generation and management endpoints (T-051)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.repositories import analysis_repo, clause_repo, contract_repo, nms_repo, redline_repo
from app.schemas.analysis import FlagDTO
from app.schemas.redline import (
    DecisionRequest,
    GenerateRedlinesRequest,
    GenerateRedlinesResponse,
    RedlineDTO,
    RefineRequest,
)
from app.services.playbook import routing
from app.services.redline import llm_call, operations, persist, render, stance

router = APIRouter(tags=["redlines"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.post("/redlines/{contract_id}", response_model=GenerateRedlinesResponse, status_code=200)
async def generate_redlines(
    contract_id: uuid.UUID,
    body: GenerateRedlinesRequest,
    session: SessionDep,
) -> GenerateRedlinesResponse:
    """Generate redlines for all flagged clauses in a contract."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "not_found", f"Contract {contract_id} not found")

    counterparty_id = contract.counterparty_id
    contract_type = contract.contract_type or ""

    raw_flags = await analysis_repo.get_flags_for_contract(session, contract_id)
    flags = [FlagDTO.model_validate(f) for f in raw_flags]

    resolved = await routing.resolve(session, contract_type)
    rules = resolved.rules

    queued = stance.queue_clauses(flags, body.stance_mode)

    redlines = []
    for flag in queued:
        clause = await clause_repo.get_clause(session, flag.clause_id)  # type: ignore[arg-type]
        if clause is None:
            continue

        rule = rules.get(clause.clause_type, None)
        preferred_language = rule.preferred_language if rule is not None else None

        cp_id = counterparty_id if counterparty_id is not None else uuid.UUID(int=0)
        pattern = await nms_repo.get_counterparty_pattern(session, cp_id, clause.clause_type)
        nms_context = stance.build_nms_context(pattern, body.stance_mode)

        redline_out = llm_call.generate_redline(
            clause.text, flag, preferred_language, nms_context, body.stance_mode
        )
        render_result = render.render(clause.text, redline_out.replacement_text, flag)

        redline, _ = await persist.persist_redline(
            session,
            contract_id,
            cp_id,
            clause.clause_type,
            flag,
            redline_out,
            render_result,
            body.stance_mode,
            preferred_language,
        )
        redlines.append(redline)

    await session.commit()
    return GenerateRedlinesResponse(redlines=[RedlineDTO.model_validate(r) for r in redlines])


@router.get("/redlines/{contract_id}", response_model=GenerateRedlinesResponse, status_code=200)
async def get_redlines(
    contract_id: uuid.UUID,
    session: SessionDep,
) -> GenerateRedlinesResponse:
    """Fetch all redlines for a contract."""
    rows = await redline_repo.get_redlines_for_contract(session, contract_id)
    return GenerateRedlinesResponse(redlines=[RedlineDTO.model_validate(r) for r in rows])


@router.post(
    "/redlines/{redline_id}/toggle-fallback", response_model=RedlineDTO, status_code=200
)
async def toggle_fallback(
    redline_id: uuid.UUID,
    session: SessionDep,
) -> RedlineDTO:
    """Swap preferred↔fallback language; re-diffs tracked changes."""
    redline = await redline_repo.get_redline(session, redline_id)
    if redline is None:
        raise AppError(404, "not_found", f"Redline {redline_id} not found")

    clause = await clause_repo.get_clause(session, redline.clause_id)  # type: ignore[arg-type]
    redline = await operations.toggle_fallback(session, redline, clause.text)
    await session.commit()
    return RedlineDTO.model_validate(redline)


@router.post("/redlines/{redline_id}/refine", response_model=RedlineDTO, status_code=200)
async def refine_redline(
    redline_id: uuid.UUID,
    body: RefineRequest,
    session: SessionDep,
) -> RedlineDTO:
    """Refine a redline via LLM with a user instruction."""
    redline = await redline_repo.get_redline(session, redline_id)
    if redline is None:
        raise AppError(404, "not_found", f"Redline {redline_id} not found")

    clause = await clause_repo.get_clause(session, redline.clause_id)  # type: ignore[arg-type]
    redline = await operations.refine(session, redline, clause.text, body.instruction)
    await session.commit()
    return RedlineDTO.model_validate(redline)


@router.post("/redlines/{redline_id}/decision", response_model=RedlineDTO, status_code=200)
async def record_decision(
    redline_id: uuid.UUID,
    body: DecisionRequest,
    session: SessionDep,
) -> RedlineDTO:
    """Record an accept/reject decision on a redline and update NMS."""
    redline = await redline_repo.get_redline(session, redline_id)
    if redline is None:
        raise AppError(404, "not_found", f"Redline {redline_id} not found")

    contract = await contract_repo.get_contract(session, redline.contract_id)
    counterparty_id = (
        contract.counterparty_id if contract is not None and contract.counterparty_id is not None
        else uuid.UUID(int=0)
    )

    clause = await clause_repo.get_clause(session, redline.clause_id)  # type: ignore[arg-type]
    clause_type = clause.clause_type if clause is not None else ""

    redline, _ = await operations.record_decision(
        session, redline, counterparty_id, clause_type, body.outcome, body.final_text
    )
    await session.commit()
    return RedlineDTO.model_validate(redline)
