from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.repositories import redline_repo, review_run_repo
from app.schemas.redline import RedlineDTO
from app.schemas.review import ReviewRunDTO, RunReviewRequest, RunReviewResponse, WebhookRequest
from app.services.contract_analysis import service as contract_analysis_service
from app.workflows.gate import GateResult, evaluate_gate
from app.workflows.review_pipeline import PipelineResult, run_pipeline

router = APIRouter(tags=["review"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


def _build_response(run, gate: GateResult, pipeline: PipelineResult) -> RunReviewResponse:
    return RunReviewResponse(
        run=ReviewRunDTO.model_validate(run),
        gate_decision=gate.gate_decision,
        gate_reason=gate.gate_reason,
        redlines=pipeline.redlines,
        flags_count=len(pipeline.analysis.flags),
        risk_score=pipeline.analysis.risk.score if pipeline.analysis.risk else None,
    )


@router.post("/review/run", response_model=RunReviewResponse, status_code=200)
async def run_review(body: RunReviewRequest, session: SessionDep) -> RunReviewResponse:
    pipeline = await run_pipeline(session, body.contract_id, body.stance_mode)
    gate = await evaluate_gate(session, pipeline, trigger="manual")
    run = await review_run_repo.get_review_run(session, gate.review_run_id)
    return _build_response(run, gate, pipeline)


@router.get("/review/runs/{run_id}", response_model=RunReviewResponse, status_code=200)
async def get_review_run(run_id: uuid.UUID, session: SessionDep) -> RunReviewResponse:
    run = await review_run_repo.get_review_run(session, run_id)
    if run is None:
        raise AppError(404, "run_not_found", f"Review run {run_id} not found")

    db_redlines = await redline_repo.get_redlines_for_contract(session, run.contract_id)
    analysis = await contract_analysis_service.get_analysis(session, run.contract_id)

    redlines = [RedlineDTO.model_validate(r) for r in db_redlines]
    return RunReviewResponse(
        run=ReviewRunDTO.model_validate(run),
        gate_decision=run.gate_decision or "",
        gate_reason=run.gate_reason or {},
        redlines=redlines,
        flags_count=len(analysis.flags),
        risk_score=analysis.risk.score if analysis.risk else None,
    )


@router.post("/review/webhook", response_model=RunReviewResponse, status_code=200)
async def webhook(body: WebhookRequest, session: SessionDep) -> RunReviewResponse:
    pipeline = await run_pipeline(session, body.contract_id, body.stance_mode)
    gate = await evaluate_gate(session, pipeline, trigger="upload_event")
    run = await review_run_repo.get_review_run(session, gate.review_run_id)
    return _build_response(run, gate, pipeline)
