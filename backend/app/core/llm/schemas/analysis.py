"""LLM output schema for S2 Layer 2 contract analysis (T-042)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClauseFlagOut(BaseModel):
    """A single issue flag returned by the LLM for one clause.

    offending_quote is a verbatim excerpt from the clause text.  Layer 2 uses
    it to compute contract-level char offsets deterministically, rather than
    asking the model for positions it cannot reliably produce.
    """

    flag_type: Literal["non_standard", "high_risk", "vague", "inconsistent", "deviation"]
    severity: Literal["low", "medium", "high"]
    detail: str
    offending_quote: str | None = None


class ClauseAnalysisItem(BaseModel):
    """LLM analysis result for a single clause."""

    clause_id: str
    flags: list[ClauseFlagOut]


class ContractAnalysisOut(BaseModel):
    """Full LLM analysis for a contract — one item per clause submitted."""

    items: list[ClauseAnalysisItem]
