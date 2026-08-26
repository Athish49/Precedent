"""S3 fallback/refine/decision operations on existing Redline rows (T-050)."""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.diff.differ import diff
from app.core.llm import gateway
from app.core.llm.schemas.redline import RedlineOut
from app.db.models.nms import DecisionEvent
from app.db.models.redline import Redline
from app.db.repositories import nms_repo

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
    """Swap preferred↔fallback. Re-diffs. No LLM. Updates and flushes the row."""
    if not redline.alternatives:
        raise ValueError("No fallback alternative available")

    old_replacement = redline.replacement_text
    new_replacement = redline.alternatives[0]["text"]

    # Swap the current replacement into alternatives[0] so the toggle is reversible.
    updated_alternatives = list(redline.alternatives)
    updated_alternatives[0] = dict(updated_alternatives[0])
    updated_alternatives[0]["text"] = old_replacement

    redline.replacement_text = new_replacement
    redline.alternatives = updated_alternatives
    redline.position = "fallback" if redline.position == "preferred" else "preferred"
    redline.tracked_changes = _changes_to_json(original_clause_text, new_replacement)

    await session.flush()
    return redline


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

    redline.replacement_text = result.replacement_text
    redline.tracked_changes = _changes_to_json(original_clause_text, result.replacement_text)
    redline.alternatives = [a.model_dump() for a in result.alternatives]
    redline.explanation = result.explanation
    redline.counterparty_comment = result.counterparty_comment

    await session.flush()
    return redline


async def record_decision(
    session: AsyncSession,
    redline: Redline,
    counterparty_id: uuid.UUID,
    clause_type: str,
    outcome: str,
    final_text: str | None,
) -> tuple[Redline, DecisionEvent]:
    """Update redline status + append NMS DecisionEvent. Flushes. Returns both."""
    redline.status = outcome  # "accepted" or "rejected"
    await session.flush()

    event = DecisionEvent(
        contract_id=redline.contract_id,
        counterparty_id=counterparty_id,
        clause_type=clause_type,
        position_offered=redline.position,
        recommended_stance=redline.stance_mode,
        outcome=outcome,
        final_text=final_text,
    )
    event = await nms_repo.create_decision_event(session, event)

    return redline, event
