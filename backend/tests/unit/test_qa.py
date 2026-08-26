"""Tests for T-075 S5 Q&A — answer_question service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.core.llm.schemas.qa import Citation, QAAnswerOut
from app.services.intelligence import qa as qa_module
from app.services.intelligence.qa import QAResult, answer_question


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clause(ordinal: int, clause_type: str = "liability") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.ordinal = ordinal
    c.clause_type = clause_type
    c.text = f"Clause {ordinal} text about {clause_type}."
    c.char_start = (ordinal - 1) * 100
    c.char_end = ordinal * 100
    return c


def _make_cached(answer: str = "Cached answer.", citations: list | None = None) -> MagicMock:
    entry = MagicMock()
    entry.answer = answer
    entry.citations = citations or []
    return entry


def _make_qa_out(answer: str, citation_ordinals: list[int] | None = None) -> QAAnswerOut:
    citations = [Citation(clause_ordinal=o, excerpt=f"excerpt from clause {o}") for o in (citation_ordinals or [])]
    return QAAnswerOut(answer=answer, citations=citations)


# ---------------------------------------------------------------------------
# Test 1: Cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_result_without_llm_call() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()
    question = "What is the liability cap?"
    cached = _make_cached(answer="Liability is capped at 12 months.")

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=cached)),
        patch.object(qa_module.qa_cache_repo, "create_cached_answer", AsyncMock()) as mock_create,
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock()) as mock_contract,
        patch.object(qa_module.clause_repo, "get_clauses_for_contract", AsyncMock()) as mock_clauses,
        patch.object(qa_module.gateway, "call_structured", MagicMock()) as mock_llm,
    ):
        result = await answer_question(session, contract_id, question)

    assert isinstance(result, QAResult)
    assert result.cached is True
    assert result.answer == "Liability is capped at 12 months."
    mock_llm.assert_not_called()
    mock_create.assert_not_called()
    mock_contract.assert_not_called()
    mock_clauses.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: Cache miss, contract found — LLM called, result persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_calls_llm_and_persists_result() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()
    question = "What are the payment terms?"
    clauses = [_make_clause(1, "payment"), _make_clause(2, "term")]
    llm_out = _make_qa_out("Payment is due net 30.", citation_ordinals=[1])

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=None)),
        patch.object(qa_module.qa_cache_repo, "create_cached_answer", AsyncMock()) as mock_create,
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock(return_value=MagicMock())),
        patch.object(qa_module.clause_repo, "get_clauses_for_contract", AsyncMock(return_value=clauses)),
        patch.object(qa_module.gateway, "call_structured", MagicMock(return_value=llm_out)) as mock_llm,
    ):
        result = await answer_question(session, contract_id, question)

    assert result.cached is False
    assert result.answer == "Payment is due net 30."
    mock_llm.assert_called_once()
    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Contract not found raises AppError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_not_found_raises_app_error() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=None)),
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock(return_value=None)),
    ):
        with pytest.raises(AppError) as exc_info:
            await answer_question(session, contract_id, "Any question?")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


# ---------------------------------------------------------------------------
# Test 4: Citation resolution maps ordinal to char offsets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_citation_resolution_maps_ordinal_to_char_offsets() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause1 = _make_clause(1, "payment")
    clause2 = _make_clause(2, "liability")
    llm_out = _make_qa_out("Liability clause applies.", citation_ordinals=[2])

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=None)),
        patch.object(qa_module.qa_cache_repo, "create_cached_answer", AsyncMock()),
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock(return_value=MagicMock())),
        patch.object(qa_module.clause_repo, "get_clauses_for_contract", AsyncMock(return_value=[clause1, clause2])),
        patch.object(qa_module.gateway, "call_structured", MagicMock(return_value=llm_out)),
    ):
        result = await answer_question(session, contract_id, "What is the liability?")

    assert len(result.citations) == 1
    cit = result.citations[0]
    assert cit["clause_id"] == str(clause2.id)
    assert cit["char_start"] == clause2.char_start
    assert cit["char_end"] == clause2.char_end
    assert cit["excerpt"] == "excerpt from clause 2"


# ---------------------------------------------------------------------------
# Test 5: Unresolved ordinal is silently skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolved_ordinal_silently_skipped() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clauses = [_make_clause(1, "payment")]
    # LLM returns ordinal 99 which does not exist
    llm_out = _make_qa_out("Answer.", citation_ordinals=[99])

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=None)),
        patch.object(qa_module.qa_cache_repo, "create_cached_answer", AsyncMock()),
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock(return_value=MagicMock())),
        patch.object(qa_module.clause_repo, "get_clauses_for_contract", AsyncMock(return_value=clauses)),
        patch.object(qa_module.gateway, "call_structured", MagicMock(return_value=llm_out)),
    ):
        result = await answer_question(session, contract_id, "Question?")

    assert result.citations == []
    assert result.answer == "Answer."


# ---------------------------------------------------------------------------
# Test 6: Empty clauses — LLM called, empty citations returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_clauses_calls_llm_and_returns_empty_citations() -> None:
    session = AsyncMock()
    contract_id = uuid.uuid4()
    llm_out = _make_qa_out("The contract does not address this.", citation_ordinals=[])

    with (
        patch.object(qa_module.qa_cache_repo, "get_cached_answer", AsyncMock(return_value=None)),
        patch.object(qa_module.qa_cache_repo, "create_cached_answer", AsyncMock()),
        patch.object(qa_module.contract_repo, "get_contract", AsyncMock(return_value=MagicMock())),
        patch.object(qa_module.clause_repo, "get_clauses_for_contract", AsyncMock(return_value=[])),
        patch.object(qa_module.gateway, "call_structured", MagicMock(return_value=llm_out)) as mock_llm,
    ):
        result = await answer_question(session, contract_id, "Any question?")

    mock_llm.assert_called_once()
    assert result.citations == []
    assert result.answer == "The contract does not address this."
