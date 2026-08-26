from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.repositories import clause_repo, contract_repo, nms_repo
from app.schemas.analysis import AnalysisResult
from app.schemas.redline import RedlineDTO
from app.services.contract_analysis import service as contract_analysis_service
from app.services.playbook import routing
from app.services.redline import llm_call, persist, render, stance


@dataclass
class PipelineResult:
    contract_id: uuid.UUID
    analysis: AnalysisResult
    redlines: list[RedlineDTO]
    stance_mode: str


async def run_pipeline(
    session: AsyncSession,
    contract_id: uuid.UUID,
    stance_mode: str = "balanced",
) -> PipelineResult:
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    contract_type = contract.contract_type or ""
    counterparty_id = contract.counterparty_id or uuid.UUID(int=0)

    # S6 + clause load run concurrently; S1 already processed the contract
    resolved, clauses = await asyncio.gather(
        routing.resolve(session, contract_type),
        clause_repo.get_clauses_for_contract(session, contract_id),
    )
    rules = resolved.rules

    # S2 — analyze commits internally
    analysis = await contract_analysis_service.analyze(session, contract_id)

    # S3 — redline each queued flag
    queued_flags = stance.queue_clauses(analysis.flags, stance_mode)

    clause_map = {c.id: c for c in clauses}

    redlines = []
    for flag in queued_flags:
        if flag.clause_id is None:
            continue
        clause = clause_map.get(flag.clause_id)
        if clause is None:
            continue

        rule = rules.get(clause.clause_type)
        preferred_language = rule.preferred_language if rule is not None else None

        pattern = await nms_repo.get_counterparty_pattern(
            session, counterparty_id, clause.clause_type
        )
        nms_context = stance.build_nms_context(pattern, stance_mode)

        redline_out = llm_call.generate_redline(
            clause.text, flag, preferred_language, nms_context, stance_mode
        )
        render_result = render.render(clause.text, redline_out.replacement_text, flag)

        redline_row, _ = await persist.persist_redline(
            session, contract_id, counterparty_id,
            clause.clause_type, flag, redline_out, render_result,
            stance_mode, preferred_language,
        )
        redlines.append(redline_row)

    await session.commit()

    return PipelineResult(
        contract_id=contract_id,
        analysis=analysis,
        redlines=[RedlineDTO.model_validate(r) for r in redlines],
        stance_mode=stance_mode,
    )
