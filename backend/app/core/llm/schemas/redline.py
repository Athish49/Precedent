"""LLM output schema for S3 redline generation (T-047)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlternativeProposal(BaseModel):
    """One alternative clause formulation returned by the LLM."""

    label: str
    text: str


class RedlineOut(BaseModel):
    """Bundled LLM output for a single clause redline.

    The LLM produces the preferred replacement text plus 2–3 alternatives,
    a plain-language explanation, and a counterparty-ready negotiation comment.
    Tracked changes are computed deterministically in T-048 from replacement_text;
    they are not produced by the LLM.
    """

    replacement_text: str
    alternatives: list[AlternativeProposal] = Field(min_length=2, max_length=3)
    explanation: str
    counterparty_comment: str
