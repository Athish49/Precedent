"""Unit tests for app.services.repository.smart_search (T-033).

All tests patch `gateway.call_structured`, `faceted_search`, and `precedent_search`
so no real LLM, DB, or embedding calls are made.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm.schemas.search import SmartSearchFilters
from app.services.repository.smart_search import SmartSearchResult, smart_search
from app.services.repository.vector import PrecedentResult

# ---------------------------------------------------------------------------
# Fixtures / shared constants
# ---------------------------------------------------------------------------

FAKE_FILTERS_METADATA = SmartSearchFilters(auto_renewal=True, notice_period_days=30)
FAKE_FILTERS_SEMANTIC = SmartSearchFilters(semantic_query="IP indemnification")

FAKE_CONTRACT_ID = uuid.uuid4()


def _make_fake_contract() -> MagicMock:
    """Return a MagicMock that looks like a Contract ORM row."""
    c = MagicMock()
    c.id = FAKE_CONTRACT_ID
    c.title = "Test Contract"
    c.source_format = "pdf"
    c.paper_origin = "own"
    c.status = "analyzed"
    c.contract_type = "nda"
    c.counterparty_id = None
    c.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return c


def _make_fake_clause_hit() -> PrecedentResult:
    return PrecedentResult(
        clause_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_type="indemnification",
        text="The party shall indemnify for IP infringement.",
        distance=0.12,
    )


# ---------------------------------------------------------------------------
# Helpers for common patch targets
# ---------------------------------------------------------------------------

_GATEWAY_PATCH = "app.services.repository.smart_search.gateway.call_structured"
_FACETED_PATCH = "app.services.repository.smart_search.faceted_search"
_VECTOR_PATCH = "app.services.repository.smart_search.precedent_search"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_smart_search_metadata_query() -> None:
    """Metadata-only filters: faceted_search called, precedent_search NOT called,
    clause_hits is empty."""
    fake_contract = _make_fake_contract()
    session = MagicMock()

    faceted_rv = ([fake_contract], 1)
    with (
        patch(_GATEWAY_PATCH, return_value=FAKE_FILTERS_METADATA),
        patch(_FACETED_PATCH, new_callable=AsyncMock, return_value=faceted_rv) as mock_faceted,
        patch(_VECTOR_PATCH, new_callable=AsyncMock) as mock_vector,
    ):
        result = await smart_search("auto-renew with 30-day notice", session)

    mock_faceted.assert_called_once()
    mock_vector.assert_not_called()

    assert isinstance(result, SmartSearchResult)
    assert result.clause_hits == []
    assert result.total_contracts == 1
    assert len(result.contracts) == 1


async def test_smart_search_semantic_query() -> None:
    """Semantic filters: both faceted_search AND precedent_search called."""
    fake_contract = _make_fake_contract()
    fake_hit = _make_fake_clause_hit()
    session = MagicMock()

    faceted_rv = ([fake_contract], 1)
    with (
        patch(_GATEWAY_PATCH, return_value=FAKE_FILTERS_SEMANTIC),
        patch(_FACETED_PATCH, new_callable=AsyncMock, return_value=faceted_rv) as mock_faceted,
        patch(_VECTOR_PATCH, new_callable=AsyncMock, return_value=[fake_hit]) as mock_vector,
    ):
        result = await smart_search("contracts about IP indemnification", session)

    mock_faceted.assert_called_once()
    mock_vector.assert_called_once_with("IP indemnification", session, limit=20)

    assert isinstance(result, SmartSearchResult)
    assert len(result.clause_hits) == 1
    assert result.clause_hits[0].clause_type == "indemnification"


async def test_smart_search_single_llm_call() -> None:
    """Exactly one call to gateway.call_structured per smart_search invocation."""
    session = MagicMock()

    with (
        patch(_GATEWAY_PATCH, return_value=FAKE_FILTERS_METADATA) as mock_llm,
        patch(_FACETED_PATCH, new_callable=AsyncMock, return_value=([], 0)),
        patch(_VECTOR_PATCH, new_callable=AsyncMock, return_value=[]),
    ):
        await smart_search("any query", session)

    assert mock_llm.call_count == 1


async def test_smart_search_returns_filters_used() -> None:
    """`result.filters_used` must equal what the LLM returned."""
    session = MagicMock()

    with (
        patch(_GATEWAY_PATCH, return_value=FAKE_FILTERS_METADATA),
        patch(_FACETED_PATCH, new_callable=AsyncMock, return_value=([], 0)),
        patch(_VECTOR_PATCH, new_callable=AsyncMock, return_value=[]),
    ):
        result = await smart_search("auto-renew with 30-day notice", session)

    assert result.filters_used == FAKE_FILTERS_METADATA
    assert result.filters_used.auto_renewal is True
    assert result.filters_used.notice_period_days == 30
