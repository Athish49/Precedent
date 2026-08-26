"""Unit tests for S5 Intelligence API endpoints (T-076).

All DB and service calls are mocked — no real database or LLM.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routes.intelligence import _get_session
from app.main import app
from app.services.intelligence.easy_prompt import EasyPromptResult
from app.services.intelligence.navigation import ClauseRef, NavigationIndex
from app.services.intelligence.qa import QAResult
from app.services.intelligence.research import ResearchResult
from app.services.intelligence.summarize import RedlineSummaryResult, SummaryResult

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

_CONTRACT_ID = uuid.uuid4()


def test_summarize() -> None:
    """POST /intelligence/{id}/summarize → 200, summary returned."""
    with patch(
        "app.api.routes.intelligence.summarize_service.summarize_contract",
        new=AsyncMock(return_value=SummaryResult(summary="This is a summary.")),
    ):
        response = client.post(f"/api/intelligence/{_CONTRACT_ID}/summarize")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "This is a summary."


def test_summarize_redlines() -> None:
    """POST /intelligence/{id}/summarize-redlines → 200."""
    with patch(
        "app.api.routes.intelligence.summarize_service.summarize_redlines",
        new=AsyncMock(
            return_value=RedlineSummaryResult(
                summary="Redline summary.", clause_type="indemnification"
            )
        ),
    ):
        response = client.post(f"/api/intelligence/{_CONTRACT_ID}/summarize-redlines")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Redline summary."
    assert body["clause_type"] == "indemnification"


def test_qa() -> None:
    """POST /intelligence/{id}/qa → 200, answer + citations + cached flag."""
    citations = [{"clause_id": str(uuid.uuid4()), "excerpt": "relevant text"}]
    with patch(
        "app.api.routes.intelligence.qa_service.answer_question",
        new=AsyncMock(
            return_value=QAResult(answer="The answer.", citations=citations, cached=False)
        ),
    ):
        response = client.post(
            f"/api/intelligence/{_CONTRACT_ID}/qa",
            json={"question": "What is the governing law?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The answer."
    assert body["citations"] == citations
    assert body["cached"] is False


def test_easy_prompt() -> None:
    """POST /intelligence/{id}/easy-prompt → 200, structured_prompt and route present."""
    with patch(
        "app.api.routes.intelligence.easy_prompt_service.generate_easy_prompt",
        new=AsyncMock(
            return_value=EasyPromptResult(
                structured_prompt="Review the indemnification clause for one-sidedness.",
                route="s3",
            )
        ),
    ):
        response = client.post(
            f"/api/intelligence/{_CONTRACT_ID}/easy-prompt",
            json={"user_request": "Check the indemnification clause"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["structured_prompt"] == "Review the indemnification clause for one-sidedness."
    assert body["route"] == "s3"


def test_research() -> None:
    """POST /intelligence/{id}/research → 200, answer + sources."""
    sources = [{"title": "Article", "snippet": "Relevant snippet", "url": "https://example.com"}]
    with patch(
        "app.api.routes.intelligence.research_service.synthesize_research",
        new=AsyncMock(
            return_value=ResearchResult(answer="Synthesized answer [1].", sources=sources)
        ),
    ):
        response = client.post(
            f"/api/intelligence/{_CONTRACT_ID}/research",
            json={
                "question": "What is standard indemnification practice?",
                "search_results": sources,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Synthesized answer [1]."
    assert body["sources"] == sources


def test_navigation() -> None:
    """GET /intelligence/{id}/navigation → 200, index + toc present."""
    clause_id = uuid.uuid4()
    nav = NavigationIndex(
        contract_id=_CONTRACT_ID,
        index={
            "indemnification": [
                ClauseRef(
                    clause_id=clause_id,
                    ordinal=1,
                    heading_text="Indemnification",
                    char_start=0,
                    char_end=100,
                )
            ]
        },
        toc=["indemnification"],
    )
    with patch(
        "app.api.routes.intelligence.navigation_service.build_navigation_index",
        new=AsyncMock(return_value=nav),
    ):
        response = client.get(f"/api/intelligence/{_CONTRACT_ID}/navigation")

    assert response.status_code == 200
    body = response.json()
    assert body["toc"] == ["indemnification"]
    assert "indemnification" in body["index"]
    refs = body["index"]["indemnification"]
    assert len(refs) == 1
    assert refs[0]["ordinal"] == 1
    assert refs[0]["heading_text"] == "Indemnification"
