"""Unit tests for the clause-navigation index (T-073)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.intelligence.navigation import (
    ClauseRef,
    NavigationIndex,
    build_navigation_index,
)

PATCH_TARGET = "app.services.intelligence.navigation.clause_repo.get_clauses_for_contract"


def _make_clause(
    ordinal: int,
    clause_type: str,
    heading_text: str | None = None,
    char_start: int = 0,
    char_end: int = 100,
) -> MagicMock:
    clause = MagicMock()
    clause.id = uuid.uuid4()
    clause.ordinal = ordinal
    clause.clause_type = clause_type
    clause.heading_text = heading_text
    clause.char_start = char_start
    clause.char_end = char_end
    return clause


@pytest.mark.asyncio
async def test_empty_contract():
    session = MagicMock()
    contract_id = uuid.uuid4()

    with patch(PATCH_TARGET, new=AsyncMock(return_value=[])):
        result = await build_navigation_index(session, contract_id)

    assert result.index == {}
    assert result.toc == []
    assert result.contract_id == contract_id


@pytest.mark.asyncio
async def test_single_clause_type():
    session = MagicMock()
    contract_id = uuid.uuid4()
    c1 = _make_clause(ordinal=1, clause_type="indemnification")
    c2 = _make_clause(ordinal=2, clause_type="indemnification")

    with patch(PATCH_TARGET, new=AsyncMock(return_value=[c1, c2])):
        result = await build_navigation_index(session, contract_id)

    assert result.toc == ["indemnification"]
    assert len(result.index["indemnification"]) == 2
    assert result.index["indemnification"][0].ordinal == 1
    assert result.index["indemnification"][1].ordinal == 2


@pytest.mark.asyncio
async def test_multiple_clause_types():
    session = MagicMock()
    contract_id = uuid.uuid4()
    c1 = _make_clause(ordinal=1, clause_type="A")
    c2 = _make_clause(ordinal=2, clause_type="B")
    c3 = _make_clause(ordinal=3, clause_type="A")

    with patch(PATCH_TARGET, new=AsyncMock(return_value=[c1, c2, c3])):
        result = await build_navigation_index(session, contract_id)

    assert result.toc == ["A", "B"]
    assert len(result.index["A"]) == 2
    assert len(result.index["B"]) == 1


@pytest.mark.asyncio
async def test_toc_first_appearance_order():
    session = MagicMock()
    contract_id = uuid.uuid4()
    # B appears first by ordinal, then A
    c1 = _make_clause(ordinal=1, clause_type="B")
    c2 = _make_clause(ordinal=2, clause_type="A")

    with patch(PATCH_TARGET, new=AsyncMock(return_value=[c1, c2])):
        result = await build_navigation_index(session, contract_id)

    assert result.toc == ["B", "A"]


@pytest.mark.asyncio
async def test_determinism():
    session = MagicMock()
    contract_id = uuid.uuid4()
    c1 = _make_clause(ordinal=1, clause_type="A", heading_text="Heading A", char_start=0, char_end=50)
    c2 = _make_clause(ordinal=2, clause_type="B", heading_text="Heading B", char_start=51, char_end=100)

    mock_fn = AsyncMock(return_value=[c1, c2])
    with patch(PATCH_TARGET, new=mock_fn):
        result1 = await build_navigation_index(session, contract_id)
        result2 = await build_navigation_index(session, contract_id)

    assert result1.toc == result2.toc
    assert list(result1.index.keys()) == list(result2.index.keys())
    for ct in result1.index:
        for r1, r2 in zip(result1.index[ct], result2.index[ct]):
            assert r1.clause_id == r2.clause_id
            assert r1.ordinal == r2.ordinal


@pytest.mark.asyncio
async def test_clause_ref_fields():
    session = MagicMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    c = _make_clause(ordinal=5, clause_type="governing_law", heading_text="Governing Law", char_start=200, char_end=400)
    c.id = clause_id

    with patch(PATCH_TARGET, new=AsyncMock(return_value=[c])):
        result = await build_navigation_index(session, contract_id)

    ref = result.index["governing_law"][0]
    assert ref.clause_id == clause_id
    assert ref.ordinal == 5
    assert ref.heading_text == "Governing Law"
    assert ref.char_start == 200
    assert ref.char_end == 400
