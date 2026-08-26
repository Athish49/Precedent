"""Smart search service (T-033).

One LLM call converts a natural language query into structured filters,
then executes faceted DB search and optional vector search, returning
merged results.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import gateway
from app.core.llm.schemas.search import SmartSearchFilters
from app.db.models.contract import Contract
from app.db.repositories.search_repo import faceted_search
from app.services.repository.vector import PrecedentResult, precedent_search

# ---------------------------------------------------------------------------
# Prompt — loaded once at import time
# ---------------------------------------------------------------------------

_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "core" / "llm" / "prompts" / "smart_search_filters.md"
)
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class SmartSearchResult(BaseModel):
    contracts: list[dict]
    clause_hits: list[PrecedentResult]
    filters_used: SmartSearchFilters
    total_contracts: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contract_to_dict(c: Contract) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "source_format": c.source_format,
        "paper_origin": c.paper_origin,
        "status": c.status,
        "contract_type": c.contract_type,
        "counterparty_id": str(c.counterparty_id) if c.counterparty_id else None,
        "created_at": c.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def smart_search(
    query: str,
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> SmartSearchResult:
    """Convert a natural language query into filters, run DB + optional vector search.

    Guarantees exactly one LLM call per invocation.

    Args:
        query: Natural language search query from the user.
        session: Async SQLAlchemy session.
        limit: Maximum number of contract rows to return.
        offset: Pagination offset for contract rows.

    Returns:
        SmartSearchResult with contracts, clause hits, filters used, and total count.
    """
    # Step 1 — single LLM call to extract structured filters
    filters: SmartSearchFilters = gateway.call_structured(
        task="search.nl_to_filter",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        response_model=SmartSearchFilters,
    )

    # Step 2 — faceted DB search (includes effective_date range if extracted)
    contracts, total = await faceted_search(
        session,
        contract_type=filters.contract_type,
        status=filters.status,
        effective_date_from=filters.effective_date_from,
        effective_date_to=filters.effective_date_to,
        q=filters.keyword_query,
        limit=limit,
        offset=offset,
    )

    # Step 3 — optional vector search
    clause_hits: list[PrecedentResult] = (
        await precedent_search(filters.semantic_query, session, limit=limit)
        if filters.semantic_query is not None
        else []
    )

    # Step 4 — serialize and return
    return SmartSearchResult(
        contracts=[_contract_to_dict(c) for c in contracts],
        clause_hits=clause_hits,
        filters_used=filters,
        total_contracts=total,
    )
