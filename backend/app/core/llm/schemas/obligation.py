"""LLM output schema for obligation extraction (T-080)."""

from __future__ import annotations

from pydantic import BaseModel


class ObligationItem(BaseModel):
    commitment: str
    owner: str
    deadline: str | None    # ISO date "YYYY-MM-DD" or null
    deliverable: str
    clause_ordinal: int
    excerpt: str


class ObligationOut(BaseModel):
    obligations: list[ObligationItem]
