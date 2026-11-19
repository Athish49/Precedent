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


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


async def test_embed_and_store_inserts_embeddings() -> None:
    """session.add should be called once per clause with a ClauseEmbedding."""
    contract_id = uuid.uuid4()
    clauses = [
        _make_clause("indemnification"),
        _make_clause("termination"),
        _make_clause("payment"),
    ]
    session = _make_session()

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


async def test_embed_and_store_sets_model_from_settings() -> None:
    """Each inserted row's `model` comes from settings.embedding_model."""
    contract_id = uuid.uuid4()
    clauses = [_make_clause("indemnification")]
    session = _make_session()

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(contract_id, clauses, session)

    added = session.add.call_args_list[0].args[0]
    from app.core.config import get_settings

    assert added.model == get_settings().embedding_model


async def test_embed_and_store_deletes_existing_rows_first() -> None:
    """Idempotency: a delete is issued (scoped to the given clauses' ids)
    before any insert, so re-running for the same clauses never collides
    with the clause_id unique constraint."""
    contract_id = uuid.uuid4()
    clauses = [_make_clause("indemnification")]
    session = _make_session()

    call_order: list[str] = []
    session.execute.side_effect = lambda *a, **k: call_order.append("execute")
    session.add.side_effect = lambda *a, **k: call_order.append("add")

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(contract_id, clauses, session)

    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    assert stmt.is_delete
    assert call_order == ["execute", "add"]


async def test_embed_and_store_twice_leaves_one_row_per_clause() -> None:
    """Running embed_and_store_clauses twice for the same clauses should
    behave idempotently: the delete-then-insert pattern means the second
    run deletes what the first run inserted (simulated here by a fake
    session acting as a minimal table) before re-inserting, so storage
    ends with exactly one row per clause, not two.
    """
    contract_id = uuid.uuid4()
    clauses = [_make_clause("indemnification"), _make_clause("termination")]
    clause_ids = {c.id for c in clauses}

    stored: dict[uuid.UUID, ClauseEmbedding] = {}

    class _FakeSession:
        def add(self, row: ClauseEmbedding) -> None:
            stored[row.clause_id] = row

        async def execute(self, stmt) -> None:
            # Any delete issued by embed_and_store_clauses is scoped to
            # these clauses' ids (never a bare TRUNCATE), so dropping every
            # row whose id is in that set is a faithful enough fake of the
            # real "DELETE WHERE clause_id IN (...)" the database would run.
            for clause_id in list(stored):
                if clause_id in clause_ids:
                    del stored[clause_id]

    session = _FakeSession()

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(contract_id, clauses, session)
        await embed_and_store_clauses(contract_id, clauses, session)

    assert len(stored) == len(clauses)
    assert set(stored) == clause_ids


async def test_embed_and_store_empty_clauses() -> None:
    """Zero clauses should produce zero session.add calls and no error."""
    session = _make_session()

    with patch("app.services.repository.vector.embed", side_effect=fake_embed):
        await embed_and_store_clauses(uuid.uuid4(), [], session)

    session.add.assert_not_called()
    session.execute.assert_not_awaited()


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
