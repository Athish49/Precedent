from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.drafting.service import (
    DraftResult,
    draft_clause,
    draft_document,
    draft_memo,
    draft_precedent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# draft_clause tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_clause_playbook_hit() -> None:
    """preferred_language set → source='playbook', no frequency/LLM call."""
    session = _mock_session()
    with (
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            preferred_language="Liability is limited to fees paid in the prior 12 months.",
        )

    assert result.source == "playbook"
    assert result.text == "Liability is limited to fees paid in the prior 12 months."
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_frequency_hit() -> None:
    """Playbook miss, frequency hit → source='frequency', no LLM call."""
    from app.services.drafting.frequency_tracker import FrequencyResult

    session = _mock_session()
    freq_result = FrequencyResult(text="Standard liability cap clause.", frequency=5, scoped=True)

    with (
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=freq_result),
        ),
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            context={"contract_type": "SaaS"},
        )

    assert result.source == "frequency"
    assert result.text == "Standard liability cap clause."
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_llm_fallback() -> None:
    """Playbook miss, frequency miss → LLM called → source='llm'."""
    session = _mock_session()

    with (
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="LLM drafted clause text.",
        ) as llm_mock,
    ):
        result = await draft_clause(
            session,
            "indemnification",
            context={"contract_type": "Services"},
            instruction="Mutual indemnification only.",
        )

    assert result.source == "llm"
    assert result.text == "LLM drafted clause text."
    llm_mock.assert_called_once()
    call_args = llm_mock.call_args
    assert call_args[0][0] == "drafting_clause"


# ---------------------------------------------------------------------------
# draft_document tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_document_no_polish() -> None:
    """No polish → source='template', variables substituted, no LLM."""
    session = _mock_session()

    with patch("app.services.drafting.service.gateway.call_text") as llm_mock:
        result = await draft_document(
            session,
            template="This agreement is between $party_a and $party_b.",
            variables={"party_a": "Acme Corp", "party_b": "Beta LLC"},
        )

    assert result.source == "template"
    assert result.text == "This agreement is between Acme Corp and Beta LLC."
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_document_polish() -> None:
    """polish=True → LLM called → source='llm'."""
    session = _mock_session()

    with patch(
        "app.services.drafting.service.gateway.call_text",
        return_value="Polished document text.",
    ) as llm_mock:
        result = await draft_document(
            session,
            template="This agreement is between $party_a and $party_b.",
            variables={"party_a": "Acme Corp", "party_b": "Beta LLC"},
            polish=True,
        )

    assert result.source == "llm"
    assert result.text == "Polished document text."
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_document_polish"


# ---------------------------------------------------------------------------
# draft_precedent tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_precedent_vector_then_llm() -> None:
    """Vector search called, then LLM → source='llm'."""
    from app.services.repository.vector import PrecedentResult

    session = _mock_session()
    precedents = [
        PrecedentResult(
            clause_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            clause_type="governing_law",
            text="Precedent clause one.",
            distance=0.1,
        ),
        PrecedentResult(
            clause_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            clause_type="governing_law",
            text="Precedent clause two.",
            distance=0.2,
        ),
    ]

    with (
        patch(
            "app.services.drafting.service.vector.precedent_search",
            new=AsyncMock(return_value=precedents),
        ) as search_mock,
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="Precedent-style drafted clause.",
        ) as llm_mock,
    ):
        result = await draft_precedent(
            session,
            "governing_law",
            context={"contract_type": "SaaS"},
        )

    assert result.source == "llm"
    assert result.text == "Precedent-style drafted clause."
    search_mock.assert_called_once()
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_precedent"


# ---------------------------------------------------------------------------
# draft_memo tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_memo_llm_called() -> None:
    """LLM called → source='llm'."""
    context = {"to": "Client", "re": "Contract Review", "issues": ["liability cap"]}

    with patch(
        "app.services.drafting.service.gateway.call_text",
        return_value="Drafted memo text.",
    ) as llm_mock:
        result = await draft_memo(context)

    assert result.source == "llm"
    assert result.text == "Drafted memo text."
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_memo"
