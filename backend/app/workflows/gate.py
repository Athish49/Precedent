from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.review_run import ReviewRun
from app.db.repositories import review_run_repo
from app.workflows.review_pipeline import PipelineResult

_HARD_STOP_FLAG_TYPES = frozenset({"missing", "prohibited"})


@dataclass
class GateResult:
    review_run_id: uuid.UUID
    contract_id: uuid.UUID
    gate_decision: str          # "auto_applied" | "escalated"
    gate_reason: dict           # which hard-stop fired (or score info)
    pipeline: PipelineResult


async def evaluate_gate(
    session: AsyncSession,
    pipeline: PipelineResult,
    trigger: str = "manual",
    escalation_score_threshold: float = 0.7,
    auto_apply_score_threshold: float = 0.4,
) -> GateResult:
    # 1. Create review_run with status='running'
    run = ReviewRun(contract_id=pipeline.contract_id, trigger=trigger, status="running")
    run = await review_run_repo.create_review_run(session, run)
    await session.flush()

    # 2. Evaluate hard-stops
    hard_stop_reason: str | None = None

    # Check flag types
    for flag in pipeline.analysis.flags:
        if flag.flag_type in _HARD_STOP_FLAG_TYPES:
            hard_stop_reason = f"hard_stop: flag_type={flag.flag_type}"
            break

    # Check max_clause_severity
    if hard_stop_reason is None and pipeline.analysis.risk is not None:
        if pipeline.analysis.risk.max_clause_severity == "high":
            hard_stop_reason = "hard_stop: max_clause_severity=high"

    # Check interference in redlines
    if hard_stop_reason is None:
        for rdto in pipeline.redlines:
            if rdto.rationale.get("interference_detected"):
                hard_stop_reason = "hard_stop: non_interference_failure"
                break

    # Check aggregate score
    if hard_stop_reason is None and pipeline.analysis.risk is not None:
        if pipeline.analysis.risk.score >= escalation_score_threshold:
            hard_stop_reason = f"hard_stop: aggregate_score={pipeline.analysis.risk.score:.3f}"

    # 3. Determine decision
    risk = pipeline.analysis.risk
    if hard_stop_reason is not None:
        decision = "escalated"
        reason = {
            "hard_stop": hard_stop_reason,
            "aggregate_score": risk.score if risk else None,
            "max_clause_severity": risk.max_clause_severity if risk else None,
        }
    elif risk is not None and risk.score < auto_apply_score_threshold:
        decision = "auto_applied"
        reason = {
            "hard_stop": None,
            "aggregate_score": risk.score,
            "max_clause_severity": risk.max_clause_severity,
        }
    else:
        # Score in ambiguous range — escalate by default (safer per FR-5)
        decision = "escalated"
        reason = {
            "hard_stop": None,
            "aggregate_score": risk.score if risk else None,
            "max_clause_severity": risk.max_clause_severity if risk else None,
            "reason": "score_in_ambiguous_range",
        }

    # 4. Persist decision
    run = await review_run_repo.complete_review_run(session, run, decision, reason)
    await session.commit()

    return GateResult(
        review_run_id=run.id,
        contract_id=pipeline.contract_id,
        gate_decision=decision,
        gate_reason=reason,
        pipeline=pipeline,
    )
