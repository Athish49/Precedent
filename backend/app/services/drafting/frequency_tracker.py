from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FrequencyResult:
    text: str
    frequency: int  # how many times this text appeared
    scoped: bool    # True if from scoped (context-matched) pass


async def _fetch_clause_texts(
    session: AsyncSession,
    clause_type: str,
    contract_type: str | None,
    counterparty_id: uuid.UUID | None,
    last_n: int,
) -> list[str]:
    from sqlalchemy import desc, select

    from app.db.models.clause import Clause
    from app.db.models.contract import Contract

    stmt = (
        select(Clause.text)
        .join(Contract, Clause.contract_id == Contract.id)
        .where(Clause.clause_type == clause_type)
    )
    if contract_type is not None:
        stmt = stmt.where(Contract.contract_type == contract_type)
    if counterparty_id is not None:
        stmt = stmt.where(Contract.counterparty_id == counterparty_id)
    stmt = stmt.order_by(desc(Contract.created_at)).limit(last_n)

    result = await session.execute(stmt)
    return list(result.scalars().all())


def _pick_best(texts: list[str], min_frequency: int) -> tuple[str, int] | None:
    """Return (most_common_text, count) if count >= min_frequency, else None.
    Tie-break by text alphabetically for determinism.
    """
    if not texts:
        return None
    counts = Counter(texts)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    top_text, top_count = ranked[0]
    if top_count >= min_frequency:
        return top_text, top_count
    return None


async def most_common_clause(
    session: AsyncSession,
    clause_type: str,
    *,
    contract_type: str | None = None,
    counterparty_id: uuid.UUID | None = None,
    last_n: int = 50,
    min_frequency: int = 2,
) -> FrequencyResult | None:
    """Return the most common clause text for the given type and context.

    Tries a scoped query first (filtered by contract_type and/or counterparty_id).
    Falls back to unscoped if scoped result doesn't meet min_frequency threshold.
    Returns None if no clauses found in either pass.
    """
    if contract_type is not None or counterparty_id is not None:
        texts = await _fetch_clause_texts(
            session, clause_type, contract_type, counterparty_id, last_n
        )
        best = _pick_best(texts, min_frequency)
        if best is not None:
            return FrequencyResult(text=best[0], frequency=best[1], scoped=True)

    texts = await _fetch_clause_texts(session, clause_type, None, None, last_n)
    best = _pick_best(texts, min_frequency)
    if best is not None:
        return FrequencyResult(text=best[0], frequency=best[1], scoped=False)

    return None
