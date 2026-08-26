"""Unit tests for app.services.repository.vector (T-031).

All tests mock `embed` and `AsyncSession` — no real DB or embedding model required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models.clause import ClauseEmbedding
from app.services.repository.vector import (
    PrecedentResult,
    embed_and_store_clauses,
    precedent_search,
)

FAKE_VEC = [0.1] * 384


async def fake_embed(texts: list[str]) -> list[list[float]]:
    return [[0.1] * 384 for _ in texts]


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_clause(clause_type: str = "indemnification") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.text = f"Some {clause_type} text."
    c.clause_type = clause_type
    return c


# ── embed_and_store_clauses ───────────────────────────────────────────────────


async def test_embed_and_store_inserts_embeddings() -> None:
    """session.add should be called once per clause with a ClauseEmbedding."""
    contract_id = uuid.uuid4()
    clauses = [
        _make_clause("indemnification"),
        _make_clause("termination"),
        _make_clause("payment"),
    ]
    session = MagicMock()

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(contract_id, clauses, session)

    assert session.add.call_count == len(clauses)

    added_objects = [call.args[0] for call in session.add.call_args_list]
    for obj, clause in zip(added_objects, clauses, strict=True):
        assert isinstance(obj, ClauseEmbedding)
        assert obj.clause_id == clause.id
        assert obj.contract_id == contract_id
        assert obj.clause_type == clause.clause_type
        assert obj.embedding == FAKE_VEC


async def test_embed_and_store_empty_clauses() -> None:
    """Zero clauses should produce zero session.add calls and no error."""
    session = MagicMock()

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(uuid.uuid4(), [], session)

    session.add.assert_not_called()


# ── precedent_search ──────────────────────────────────────────────────────────


def _make_fake_row(clause_type: str = "indemnification") -> tuple:
    """Return a fake (ClauseEmbedding, Clause, distance) tuple."""
    emb = MagicMock(spec=ClauseEmbedding)
    emb.clause_id = uuid.uuid4()
    emb.contract_id = uuid.uuid4()
    emb.clause_type = clause_type

    clause = MagicMock()
    clause.text = f"Clause text for {clause_type}."

    dist = 0.05
    return (emb, clause, dist)


async def test_precedent_search_returns_results() -> None:
    """Should return a list of PrecedentResult with correct field mappings."""
    fake_rows = [_make_fake_row("indemnification"), _make_fake_row("termination")]

    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.all.return_value = fake_rows
    session.execute.return_value = execute_result

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        results = await precedent_search("What is the indemnification scope?", session)

    assert len(results) == 2
    for result, (emb, clause, dist) in zip(results, fake_rows, strict=True):
        assert isinstance(result, PrecedentResult)
        assert result.clause_id == emb.clause_id
        assert result.contract_id == emb.contract_id
        assert result.clause_type == emb.clause_type
        assert result.text == clause.text
        assert result.distance == dist


async def test_precedent_search_with_clause_type_filter() -> None:
    """When clause_type is provided, session.execute should still be called (filter applied)."""
    fake_rows = [_make_fake_row("termination")]

    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.all.return_value = fake_rows
    session.execute.return_value = execute_result

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        results = await precedent_search(
            "termination conditions", session, clause_type="termination"
        )

    session.execute.assert_called_once()
    assert len(results) == 1
    assert results[0].clause_type == "termination"
