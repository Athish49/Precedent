"""LLM output schema for S6 playbook bootstrap (T-038)."""

from __future__ import annotations

from pydantic import BaseModel


class PlaybookBootstrapOut(BaseModel):
    """Structured output from the playbook bootstrap batch job.

    The LLM extracts preferred language and acceptable variations for one
    clause type from a sample of executed contracts.  Prohibited terms are
    NOT included — they come from the template seed, not executed contracts.
    """

    clause_type: str
    preferred_language: str
    acceptable_variations: list[str]
