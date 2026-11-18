"""S3 fallback/refine/decision operations on existing Redline rows (T-050).

Task 4.6 fixed two bugs here against the widened ``ck_redline_position``
check (migration 012, ``position = 'preferred' OR position ~
'^fallback_[0-9]+$'``):

1. ``toggle_fallback`` previously flipped between the bare literals
   ``"preferred"``/``"fallback"`` — the latter no longer satisfies the
   check constraint at all. It now steps one rung at a time through
   ``redline.alternatives`` (each tagged with its own ``rung`` by
   ``app.services.redline.ladder.reconcile_alternatives`` at generation
   time) and writes ``fallback_1``, ``fallback_2``, etc.
2. ``record_decision`` never populated the new ``decision_event`` or
   ``playbook_exception`` provenance columns added by migration 012 /
   task 1.3. It now looks up the rule and position behind
   ``redline.position_id`` and records them, and creates a
   ``playbook_exception`` in ``requested`` status when an accepted
   decision's rung is in the yellow zone (``playbook_plan.md`` section 5.4).
"""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.diff.differ import diff
from app.core.llm import gateway
from app.core.llm.schemas.redline import AlternativeProposal, RedlineOut
from app.db.models.exception import PlaybookException
from app.db.models.nms import DecisionEvent
from app.db.models.playbook import PlaybookRule, RulePosition
from app.db.models.redline import Redline
from app.db.repositories import exception_repo, nms_repo, playbook_repo
from app.schemas.playbook import RulePositionResponse
from app.services.redline import ladder

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_REFINE_SYSTEM = (_PROMPTS_DIR / "redline_refine.md").read_text()

_REFINE_TASK = "redline_refine"


def _changes_to_json(original: str, revised: str) -> list[dict]:
    """Diff two strings and return a list of serialisable Change dicts."""
    return [dataclasses.asdict(c) for c in diff(original, revised)]


async def toggle_fallback(
    session: AsyncSession,
    redline: Redline,
    original_clause_text: str,
) -> Redline:
    """Step the redline one rung down the ladder. Re-diffs. No LLM.

    ``redline.alternatives`` is treated as a queue of not-currently-active
    rungs, in rung order. Toggling promotes the front of the queue into
    ``replacement_text``/``position``/``position_id``, and appends the
    rung just vacated to the back of the queue — so with a single
    alternative this degenerates to the old reversible two-state swap, and
    with several it walks the whole ladder (preferred -> fallback_1 ->
    fallback_2 -> ... -> back to preferred) rather than ever writing the
    bare literal ``"fallback"``.
    """
    if not redline.alternatives:
        raise ValueError("No fallback alternative available")

    current_rung = ladder.rung_from_position(redline.position)
    current_entry = {
        "label": "Preferred position" if current_rung == 0 else f"Fallback {current_rung}",
        "text": redline.replacement_text,
        "position_id": str(redline.position_id) if redline.position_id is not None else None,
        "rung": current_rung,
    }

    next_entry = dict(redline.alternatives[0])
    remaining_queue = [*redline.alternatives[1:], current_entry]

    next_position_id = next_entry.get("position_id")
    next_rung = next_entry.get("rung")

    redline.replacement_text = next_entry["text"]
    redline.alternatives = remaining_queue
    redline.position_id = uuid.UUID(next_position_id) if next_position_id else None
    redline.position = ladder.position_label(next_rung)
    redline.tracked_changes = _changes_to_json(original_clause_text, next_entry["text"])

    await session.flush()
    return redline


async def _reconcile_refined_alternatives(
    session: AsyncSession,
    redline: Redline,
    raw: list[AlternativeProposal],
) -> list[AlternativeProposal]:
    """Re-attach the model's refined alternative wording to this redline's
    existing ladder slots, so each keeps its canonical ``position_id``/``rung``.

    Two cases, because ``redline.alternatives`` is a rotating queue (see
    ``toggle_fallback``), not always "fallback rungs in rung order":

    - At ``preferred`` the queue has exactly its generation-time shape (the
      offered fallback rungs, rung-ascending). The canonical
      ``RulePosition`` rows behind it are re-fetched and the model output is
      routed through ``ladder.reconcile_alternatives`` — the same function
      ``llm_call.generate_redline`` uses at generation time. With no
      position-backed entries (the free-form path) that call's empty-ladder
      branch stamps sequential rungs, exactly as at generation.
    - Anywhere else (after one or more toggles) the queue may hold the
      rung-0 entry and be rotated, e.g. ``[fallback_2, preferred]`` while on
      ``fallback_1``. ``reconcile_alternatives`` would re-sort that by rung
      (changing the toggle cycle) or, on the free-form path, restamp rungs
      1..n (colliding with the active rung and losing rung 0). So instead
      the model's wording is zipped by index onto the existing entries, each
      keeping its own ``position_id``/``rung``; a short model response keeps
      the stored text for the remaining slots, and extras are dropped (they
      would be invented positions) — the same rules ``reconcile_alternatives``
      applies.
    """
    prior: list[dict] = list(redline.alternatives or [])

    if redline.position == ladder.PREFERRED_POSITION:
        prior_ids = [e.get("position_id") for e in prior if e.get("position_id")]
        positions: list[RulePositionResponse] = []
        for pid in prior_ids:
            row = await playbook_repo.get_rule_position(session, uuid.UUID(str(pid)))
            if row is not None:
                positions.append(RulePositionResponse.model_validate(row))
        # Use the canonical-ladder path when every position-backed slot was
        # found (or there were none: free-form). If some position rows have
        # since disappeared, fall through to slot-preserving zip below rather
        # than silently shrinking the ladder.
        if len(positions) == len(prior_ids):
            return ladder.reconcile_alternatives(raw, positions)

    reconciled: list[AlternativeProposal] = []
    for index, entry in enumerate(prior):
        if index < len(raw):
            label, text = raw[index].label, raw[index].text
        else:
            label, text = entry.get("label", ""), entry["text"]
        position_id = entry.get("position_id")
        reconciled.append(
            AlternativeProposal(
                label=label,
                text=text,
                position_id=uuid.UUID(str(position_id)) if position_id else None,
                rung=entry.get("rung"),
            )
        )
    return reconciled


async def refine(
    session: AsyncSession,
    redline: Redline,
    original_clause_text: str,
    instruction: str,
) -> Redline:
    """One LLM call (redline_refine task). Re-diffs. Updates and flushes the row."""
    user_content = "\n".join([
        "## Original clause",
        original_clause_text,
        "",
        "## Current replacement",
        redline.replacement_text,
        "",
        "## Refinement instruction",
        instruction,
        "",
        "## Prior explanation",
        redline.explanation,
    ])
    messages = [
        {"role": "system", "content": _REFINE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    result: RedlineOut = gateway.call_structured(
        _REFINE_TASK, messages, RedlineOut, cache_prefix=_REFINE_SYSTEM
    )

    # The refined replacement stays on the redline's current rung:
    # ``position``/``position_id`` are deliberately left untouched.
    redline.replacement_text = result.replacement_text
    redline.tracked_changes = _changes_to_json(original_clause_text, result.replacement_text)
    # Never store the model's raw alternatives: their position_id/rung are
    # untrusted (and None), which would make a later toggle_fallback write a
    # mislabeled "preferred" rung. Reconcile them against the ladder this
    # redline already carries, then serialise exactly as persist.py does
    # (mode="json", so position_id is a str that toggle_fallback can parse).
    reconciled = await _reconcile_refined_alternatives(session, redline, result.alternatives)
    redline.alternatives = [a.model_dump(mode="json") for a in reconciled]
    redline.explanation = result.explanation
    redline.counterparty_comment = result.counterparty_comment

    await session.flush()
    return redline


async def _lookup_rule_and_position(
    session: AsyncSession, position_id: uuid.UUID | None
) -> tuple[PlaybookRule | None, RulePosition | None]:
    """Resolve the rule and position behind a redline's current rung.

    ``Redline`` only carries ``position_id`` (migration 012); the rule's own
    identity (``rule_key``, ``playbook_version_id``) lives on
    ``PlaybookRule``, reached via ``RulePosition.rule_id``. Returns
    ``(None, None)`` when there is no position (no playbook rule matched
    when this redline was generated).
    """
    if position_id is None:
        return None, None
    position = await playbook_repo.get_rule_position(session, position_id)
    if position is None:
        return None, None
    rule = await playbook_repo.get_rule(session, position.rule_id)
    return rule, position


async def _create_exception_for_acceptance(
    session: AsyncSession,
    redline: Redline,
    rule: PlaybookRule | None,
    position: RulePosition,
    final_text: str | None,
) -> PlaybookException:
    """Create the ``requested`` ``playbook_exception`` row for accepting a
    yellow-zone rung (task 4.6 item 5; ``playbook_plan.md`` section 5.4).

    ``position.approver_role_id`` is already a resolved ``approver_role.id``
    FK on ``rule_position`` (not a bare key string), so it is used directly
    rather than re-resolved through ``authority_repo`` — see this task's
    report for that judgment call. ``approved_by`` is a placeholder: this
    row is created in ``requested`` status, before anyone has approved it;
    the actual approver identity belongs to the (not-yet-built) approval
    workflow that moves it to ``approved``/``rejected``.
    """
    rule_key = rule.rule_key if rule is not None and rule.rule_key else str(position.rule_id)
    exception = PlaybookException(
        contract_id=redline.contract_id,
        review_run_id=redline.review_run_id,
        rule_id=position.rule_id,
        rule_key=rule_key,
        position_id=position.id,
        zone=position.zone,
        agreed_text=final_text or redline.replacement_text,
        approver_role_id=position.approver_role_id,
        approved_by="pending",
        rationale=f"Accepted '{position.label}' ({position.zone} zone) for rule {rule_key}.",
        status="requested",
    )
    return await exception_repo.create_exception(session, exception)


async def record_decision(
    session: AsyncSession,
    redline: Redline,
    counterparty_id: uuid.UUID | None,
    clause_type: str,
    outcome: str,
    final_text: str | None,
) -> tuple[Redline, DecisionEvent]:
    """Update redline status + append NMS DecisionEvent. Flushes. Returns both.

    ``counterparty_id`` may be None (task 4.6 item 6 — unknown
    counterparty is no longer papered over with a zero/nil UUID; the
    column is nullable instead).

    Task 4.6 items 4 and 5: the DecisionEvent records ``rule_id``,
    ``rule_key``, ``position_id`` and ``playbook_version_id`` looked up
    from the redline's current rung, and an accepted decision on a
    yellow-zone rung creates a ``playbook_exception`` in ``requested``
    status.
    """
    redline.status = outcome  # "accepted" or "rejected"
    await session.flush()

    rule, position = await _lookup_rule_and_position(session, redline.position_id)

    event = DecisionEvent(
        contract_id=redline.contract_id,
        counterparty_id=counterparty_id,
        clause_type=clause_type,
        position_offered=redline.position,
        recommended_stance=redline.stance_mode,
        outcome=outcome,
        final_text=final_text,
        rule_id=rule.id if rule is not None else None,
        rule_key=rule.rule_key if rule is not None else None,
        position_id=redline.position_id,
        playbook_version_id=rule.playbook_version_id if rule is not None else None,
    )
    event = await nms_repo.create_decision_event(session, event)

    if outcome == "accepted" and position is not None and position.zone == "yellow":
        await _create_exception_for_acceptance(session, redline, rule, position, final_text)

    return redline, event
