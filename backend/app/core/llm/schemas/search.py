from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SmartSearchFilters(BaseModel):
    """Structured output from the NL→search-filters LLM call."""

    contract_type: str | None = Field(
        default=None,
        description="e.g. 'nda', 'saas_msa', 'dpa'. None if not mentioned.",
    )
    status: str | None = Field(
        default=None,
        description="One of: processing, analyzed, redlined, executed. None if not specified.",
    )
    auto_renewal: bool | None = Field(
        default=None,
        description=(
            "True if user wants auto-renewal contracts, False for non-auto-renewal, "
            "None if not mentioned."
        ),
    )
    notice_period_days: int | None = Field(
        default=None,
        description="Exact notice period in days if mentioned (e.g. 30). None otherwise.",
    )
    governing_law: str | None = Field(
        default=None,
        description="State/country of governing law if mentioned. None otherwise.",
    )
    effective_date_from: date | None = Field(
        default=None,
        description="Start of effective date range (inclusive). None if not specified.",
    )
    effective_date_to: date | None = Field(
        default=None,
        description="End of effective date range (inclusive). None if not specified.",
    )
    semantic_query: str | None = Field(
        default=None,
        description=(
            "A semantic search string for vector similarity search — use when the user's "
            "query refers to clause content, topics, or concepts rather than metadata fields. "
            "For example: 'IP indemnification', 'liability cap unlimited'. None if the query "
            "is purely about metadata (dates, status, auto-renewal)."
        ),
    )
    keyword_query: str | None = Field(
        default=None,
        description=(
            "A keyword/phrase for full-text search. Use when the user wants to find specific "
            "wording in contract text. None if not applicable."
        ),
    )
