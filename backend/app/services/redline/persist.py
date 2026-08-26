"""S3 rationale assembly and persistence (T-049).

Assembles the deterministic ``rationale`` dict, persists a ``Redline`` row,
and appends a ``DecisionEvent`` with outcome="pending".  No LLM calls here.
"""

from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.schemas.redline import RedlineOut
from app.db.models.nms import DecisionEvent
from app.db.models.redline import Redline
from app.db.repositories import nms_repo, redline_repo
from app.schemas.analysis import FlagDTO
from app.services.redline.render import RenderResult


async def persist_redline(
    session: AsyncSession,
    contract_id: uuid.UUID,
    counterparty_id: uuid.UUID,
    clause_type: str,
    flag: FlagDTO,
    redline_out: RedlineOut,
    render_result: RenderResult,
    stance_mode: str,
    preferred_language: str | None,
    review_run_id: uuid.UUID | None = None,
) -> tuple[Redline, DecisionEvent]:
    """Assemble rationale, persist Redline + DecisionEvent, return both.

    Args:
        session: Active async DB session (caller manages transaction).
        contract_id: UUID of the contract being redlined.
        counterparty_id: UUID of the counterparty (for DecisionEvent).
        clause_type: Clause type label (for DecisionEvent).
        flag: The FlagDTO that triggered this redline.
        redline_out: LLM output from T-047.
        render_result: Tracked-changes render result from T-048.
        stance_mode: One of 'light', 'balanced', 'firm'.
        preferred_language: Playbook preferred language for this clause, or None.
        review_run_id: Optional review run UUID (no FK yet).

    Returns:
        A (Redline, DecisionEvent) tuple, both flushed to the session.
    """
    # 1. Assemble deterministic rationale dict (no LLM).
    rationale: dict = {
        "playbook_position": preferred_language,
        "flag_type": flag.flag_type,
        "flag_severity": flag.severity,
        "explanation": redline_out.explanation,
        "stance_mode": stance_mode,
        "interference_detected": render_result.interference_detected,
    }

    # 2. Serialise tracked_changes (list of Change dataclasses → list of dicts).
    tracked_changes_serialised = [
        dataclasses.asdict(c) for c in render_result.tracked_changes
    ]

    # 3. Serialise alternatives (list of AlternativeProposal pydantic models → list of dicts).
    alternatives_serialised = [a.model_dump() for a in redline_out.alternatives]

    # 4. Create and flush a Redline row.
    redline = Redline(
        contract_id=contract_id,
        clause_id=flag.clause_id,
        flag_id=flag.id,
        review_run_id=review_run_id,
        stance_mode=stance_mode,
        position="preferred",
        replacement_text=redline_out.replacement_text,
        tracked_changes=tracked_changes_serialised,
        alternatives=alternatives_serialised,
        explanation=redline_out.explanation,
        counterparty_comment=redline_out.counterparty_comment,
        rationale=rationale,
        status="proposed",
    )
    redline = await redline_repo.create_redline(session, redline)

    # 5. Create and flush a DecisionEvent row with outcome="pending".
    event = DecisionEvent(
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type=clause_type,
        position_offered="preferred",
        recommended_stance=stance_mode,
        outcome="pending",
        final_text=None,
    )
    event = await nms_repo.create_decision_event(session, event)

    # 6. Return both.
    return redline, event
