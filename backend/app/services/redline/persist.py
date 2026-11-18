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
from app.schemas.playbook import ResolvedRule, RuleObjectionResponse, RulePositionResponse
from app.services.redline import ladder
from app.services.redline.render import RenderResult


async def persist_redline(
    session: AsyncSession,
    contract_id: uuid.UUID,
    counterparty_id: uuid.UUID | None,
    clause_type: str,
    flag: FlagDTO,
    redline_out: RedlineOut,
    render_result: RenderResult,
    stance_mode: str,
    preferred_language: str | None,
    review_run_id: uuid.UUID | None = None,
    rule: ResolvedRule | None = None,
    preferred_position: RulePositionResponse | None = None,
    matched_objection: RuleObjectionResponse | None = None,
) -> tuple[Redline, DecisionEvent]:
    """Assemble rationale, persist Redline + DecisionEvent, return both.

    Args:
        session: Active async DB session (caller manages transaction).
        contract_id: UUID of the contract being redlined.
        counterparty_id: UUID of the counterparty (for DecisionEvent), or
            None when the counterparty is not known (task 4.6 item 6 — this
            used to be papered over with a zero/nil UUID; the column is now
            nullable instead).
        clause_type: Clause type label (for DecisionEvent).
        flag: The FlagDTO that triggered this redline.
        redline_out: LLM output from T-047, with ``alternatives`` already
            reconciled against the offered fallback ladder by
            ``llm_call.generate_redline``.
        render_result: Tracked-changes render result from T-048.
        stance_mode: One of 'light', 'balanced', 'firm'.
        preferred_language: Playbook preferred (rung 0) language for this
            clause, or None.
        review_run_id: Optional review run UUID (no FK yet).
        rule: The resolved playbook rule this redline was generated from, or
            None if no rule matched (task 4.6 item 4: supplies
            ``rule_id``/``rule_key``/``playbook_version_id`` for the
            DecisionEvent).
        preferred_position: The rule's rung-0 ``RulePosition``, or None.
            Recorded as ``redline.position_id`` and
            ``decision_event.position_id`` (task 4.6 items 1 and 4) — this
            redline opens at the preferred rung, so that is the position
            being offered until a toggle moves it.
        matched_objection: The best-matching ``RuleObjection`` for this rule
            (``ladder.select_best_objection``), or None. When present, its
            ``response`` replaces the model's free-form
            ``counterparty_comment`` (task 4.6 item 2) and its id is
            recorded as ``redline.objection_id``.

    Returns:
        A (Redline, DecisionEvent) tuple, both flushed to the session.
    """
    # 1. The counterparty comment: the matching objection's response wins
    #    over whatever the model wrote (task 4.6 item 2).
    counterparty_comment = (
        matched_objection.response if matched_objection is not None else redline_out.counterparty_comment
    )

    # 2. Assemble deterministic rationale dict (no LLM).
    rationale: dict = {
        "playbook_position": preferred_language,
        "flag_type": flag.flag_type,
        "flag_severity": flag.severity,
        "explanation": redline_out.explanation,
        "stance_mode": stance_mode,
        "interference_detected": render_result.interference_detected,
    }

    # 3. Serialise tracked_changes (list of Change dataclasses → list of dicts).
    tracked_changes_serialised = [
        dataclasses.asdict(c) for c in render_result.tracked_changes
    ]

    # 4. Serialise alternatives (list of AlternativeProposal pydantic models → list of dicts).
    alternatives_serialised = [a.model_dump(mode="json") for a in redline_out.alternatives]

    # 5. Create and flush a Redline row. Every redline opens at the
    #    preferred (rung 0) position; toggle_fallback steps it down the
    #    ladder from there.
    redline = Redline(
        contract_id=contract_id,
        clause_id=flag.clause_id,
        flag_id=flag.id,
        review_run_id=review_run_id,
        position_id=preferred_position.id if preferred_position is not None else None,
        objection_id=matched_objection.id if matched_objection is not None else None,
        stance_mode=stance_mode,
        position=ladder.PREFERRED_POSITION,
        replacement_text=redline_out.replacement_text,
        tracked_changes=tracked_changes_serialised,
        alternatives=alternatives_serialised,
        explanation=redline_out.explanation,
        counterparty_comment=counterparty_comment,
        rationale=rationale,
        status="proposed",
    )
    redline = await redline_repo.create_redline(session, redline)

    # 6. Create and flush a DecisionEvent row with outcome="pending". Task
    #    4.6 item 4: record rule_id, rule_key, position_id and
    #    playbook_version_id when a rule matched.
    event = DecisionEvent(
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type=clause_type,
        position_offered=ladder.PREFERRED_POSITION,
        recommended_stance=stance_mode,
        outcome="pending",
        final_text=None,
        rule_id=rule.id if rule is not None else None,
        rule_key=rule.rule_key if rule is not None else None,
        position_id=preferred_position.id if preferred_position is not None else None,
        playbook_version_id=rule.playbook_version_id if rule is not None else None,
    )
    event = await nms_repo.create_decision_event(session, event)

    # 7. Return both.
    return redline, event
