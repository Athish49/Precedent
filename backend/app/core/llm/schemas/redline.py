"""LLM output schema for S3 redline generation (T-047)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AlternativeProposal(BaseModel):
    """One alternative clause formulation.

    ``position_id`` and ``rung`` (task 4.6; ``playbook_plan.md`` section 5.4)
    identify which rung of the playbook's ladder this alternative stands in
    for, when it was generated from one. They are not trusted from the raw
    LLM output — ``app.services.redline.ladder.reconcile_alternatives``
    overwrites them deterministically from the rule's own ``RulePosition``
    rows after the call returns, so the model can adapt wording but can
    never invent a position that was not actually offered. Both are ``None``
    for the legacy free-form path (no playbook rule matched).
    """

    label: str
    text: str
    position_id: uuid.UUID | None = None
    rung: int | None = None


class RedlineOut(BaseModel):
    """Bundled LLM output for a single clause redline.

    The LLM produces the preferred replacement text plus alternatives, a
    plain-language explanation, and a counterparty-ready negotiation
    comment. Tracked changes are computed deterministically in T-048 from
    replacement_text; they are not produced by the LLM.

    ``alternatives`` no longer has a fixed 2-3 length (task 4.6): when a
    playbook rule matched, its count is dictated by however many fallback
    rungs ``conditions`` leaves available for this contract's context — that
    can be zero, one, or several. The free-form path (no rule matched)
    still typically asks the model for 2-3, but that is a prompt
    instruction now, not a schema constraint.
    """

    replacement_text: str
    alternatives: list[AlternativeProposal] = Field(default_factory=list)
    explanation: str
    counterparty_comment: str
