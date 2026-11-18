from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.repositories import clause_repo, contract_repo, nms_repo
from app.schemas.analysis import AnalysisResult
from app.schemas.redline import RedlineDTO
from app.services.contract_analysis import service as contract_analysis_service
from app.services.playbook import routing
from app.services.redline import ladder, llm_call, persist, render, stance


@dataclass
class PipelineResult:
    contract_id: uuid.UUID
    analysis: AnalysisResult
    redlines: list[RedlineDTO]
    stance_mode: str
    # New (task 4.5; playbook_plan.md section 5.3 item 6): the playbook
    # versions this review ran against, for app/workflows/gate.py to record
    # on the review_run row (ReviewRun.playbook_version_ids, migration 012).
    # Defaulted so existing callers that construct a PipelineResult without
    # it (tests outside this task's scope) keep working.
    pinned_version_ids: list[uuid.UUID] = field(default_factory=list)


async def run_pipeline(
    session: AsyncSession,
    contract_id: uuid.UUID,
    stance_mode: str = "balanced",
) -> PipelineResult:
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    contract_type = contract.contract_type or ""
    # Task 4.6 item 6: an unknown counterparty is None, not a zero/nil UUID
    # placeholder — decision_event.counterparty_id is nullable (migration 013).
    counterparty_id = contract.counterparty_id

    # S6 + clause load run concurrently; S1 already processed the contract
    resolved, clauses = await asyncio.gather(
        routing.resolve(
            session,
            contract_type,
            contract.party_role or "vendor",
            contract.paper_origin,
            contract.context,
        ),
        clause_repo.get_clauses_for_contract(session, contract_id),
    )
    # Rules are looked up per flag by the flag's own rule_key; the
    # clause-type index is only the fallback for flags with no rule_key
    # (see routing.rule_for_flag).
    rules_by_key = routing.rules_by_rule_key(resolved)
    rules = routing.rules_by_clause_type(resolved)

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

        rule = routing.rule_for_flag(flag.rule_key, clause.clause_type, rules_by_key, rules)
        preferred_position, fallback_positions = ladder.select_offered_positions(
            rule, contract.context
        )
        # Rung-0 language comes from the rule's positions only (the legacy
        # flat column is gone, migration 015). None when the rule has no
        # preferred/rung-0 position, or there is no rule.
        preferred_language = (
            preferred_position.language
            if preferred_position is not None
            else ladder.rung0_language(rule)
        )
        matched_objection = ladder.select_best_objection(rule, fallback_positions)

        pattern = await nms_repo.get_counterparty_pattern(
            session, counterparty_id, clause.clause_type
        )
        nms_context = stance.build_nms_context(pattern, stance_mode)

        redline_out = llm_call.generate_redline(
            clause.text, flag, preferred_language, nms_context, stance_mode, fallback_positions
        )
        render_result = render.render(clause.text, redline_out.replacement_text, flag)

        redline_row, _ = await persist.persist_redline(
            session, contract_id, counterparty_id,
            clause.clause_type, flag, redline_out, render_result,
            stance_mode, preferred_language,
            rule=rule, preferred_position=preferred_position,
            matched_objection=matched_objection,
        )
        redlines.append(redline_row)

    await session.commit()

    return PipelineResult(
        contract_id=contract_id,
        analysis=analysis,
        redlines=[RedlineDTO.model_validate(r) for r in redlines],
        stance_mode=stance_mode,
        pinned_version_ids=resolved.pinned_version_ids,
    )
