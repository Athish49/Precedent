"""Unit tests for research service (T-076)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.services.intelligence.research import ResearchResult, synthesize_research


def _mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_synthesize_research_success() -> None:
    """Contract found, search_results provided → LLM called once → ResearchResult with answer + sources."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    contract = MagicMock()
    contract.title = "SaaS Agreement"
    contract.contract_type = "saas"

    search_results = [
        {"title": "Article 1", "snippet": "Relevant snippet 1", "url": "https://example.com/1"},
        {"title": "Article 2", "snippet": "Relevant snippet 2", "url": "https://example.com/2"},
    ]

    with (
        patch(
            "app.services.intelligence.research.contract_repo.get_contract",
            new=AsyncMock(return_value=contract),
        ),
        patch(
            "app.services.intelligence.research.gateway.call_text",
            return_value="Synthesized answer citing [1] and [2].",
        ) as llm_mock,
    ):
        result = await synthesize_research(
            session, contract_id, "What is standard indemnification?", search_results
        )

    assert isinstance(result, ResearchResult)
    assert result.answer == "Synthesized answer citing [1] and [2]."
    assert result.sources == search_results
    llm_mock.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_research_contract_not_found() -> None:
    """Contract not found → AppError raised."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    with patch(
        "app.services.intelligence.research.contract_repo.get_contract",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(AppError) as exc_info:
            await synthesize_research(session, contract_id, "question", [])

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


@pytest.mark.asyncio
async def test_synthesize_research_empty_search_results() -> None:
    """Empty search_results → LLM still called → answer returned."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    contract = MagicMock()
    contract.title = "NDA"
    contract.contract_type = "nda"

    with (
        patch(
            "app.services.intelligence.research.contract_repo.get_contract",
            new=AsyncMock(return_value=contract),
        ),
        patch(
            "app.services.intelligence.research.gateway.call_text",
            return_value="Answer based on general legal knowledge.",
        ) as llm_mock,
    ):
        result = await synthesize_research(session, contract_id, "general question", [])

    assert result.answer == "Answer based on general legal knowledge."
    assert result.sources == []
    llm_mock.assert_called_once()
