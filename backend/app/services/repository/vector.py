"""Vector embedding and ANN search for contract clauses (T-031).

Provides:
  - embed_and_store_clauses: compute embeddings and persist ClauseEmbedding rows.
  - precedent_search: cosine ANN search via pgvector, optionally filtered by clause_type.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel
from sqlalchemy import cast, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embeddings import embed
from app.db.models.clause import Clause, ClauseEmbedding


class ClauseRow(Protocol):
    """Structural protocol for clause objects passed to embed_and_store_clauses.

    Compatible with both the ORM Clause model and any lightweight test stub.
    """

    id: uuid.UUID
    text: str
    clause_type: str


class PrecedentResult(BaseModel):
    """Result item returned by precedent_search."""

    clause_id: uuid.UUID
    contract_id: uuid.UUID
    clause_type: str
    text: str
    distance: float

    model_config = {"from_attributes": True}


async def embed_and_store_clauses(
    contract_id: uuid.UUID,
    clauses: list[ClauseRow],
    session: AsyncSession,
) -> None:
    """Compute embeddings for *clauses* and persist ``ClauseEmbedding`` rows.

    Idempotent: any existing embedding row for a clause in *clauses* is
    deleted before the new one is inserted, so running this twice for the
    same clauses leaves exactly one row per clause (the unique constraint
    on ``clause_id`` would otherwise raise on the second run). Callers
    control exactly which clauses get embedded -- this function does not
    re-derive the list itself (task 3.2; plan section 5.8).

    Args:
        contract_id: UUID of the parent contract.
        clauses: list of clause objects with .id (uuid), .text (str), .clause_type (str).
        session: Async SQLAlchemy session (caller commits).
    """
    if not clauses:
        return

    clause_ids = [c.id for c in clauses]
    await session.execute(delete(ClauseEmbedding).where(ClauseEmbedding.clause_id.in_(clause_ids)))

    vectors = await embed([c.text for c in clauses])
    model_name = get_settings().embedding_model

    for clause, vector in zip(clauses, vectors, strict=True):
        row = ClauseEmbedding(
            id=uuid.uuid4(),
            clause_id=clause.id,
            contract_id=contract_id,
            clause_type=clause.clause_type,
            embedding=vector,
            model=model_name,
        )
        session.add(row)


async def precedent_search(
    query_text: str,
    session: AsyncSession,
    *,
    clause_type: str | None = None,
    limit: int = 10,
) -> list[PrecedentResult]:
    """ANN cosine search over clause_embedding using pgvector.

    Returns the nearest clauses to query_text, optionally filtered by clause_type.

    Args:
        query_text: Natural language query to embed and search against.
        session: Async SQLAlchemy session.
        clause_type: If provided, restrict results to this clause type.
        limit: Maximum number of results to return (default 10).

    Returns:
        Ranked list of PrecedentResult objects, closest first.
    """
    (query_vec,) = await embed([query_text])

    distance = ClauseEmbedding.embedding.op("<=>")(cast(query_vec, Vector(384)))

    stmt = (
        select(ClauseEmbedding, Clause, distance.label("distance"))
        .join(Clause, ClauseEmbedding.clause_id == Clause.id)
        .order_by(distance)
        .limit(limit)
    )

    if clause_type is not None:
        stmt = stmt.where(ClauseEmbedding.clause_type == clause_type)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        PrecedentResult(
            clause_id=emb.clause_id,
            contract_id=emb.contract_id,
            clause_type=emb.clause_type,
            text=clause.text,
            distance=dist,
        )
        for emb, clause, dist in rows
    ]
