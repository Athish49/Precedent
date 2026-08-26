from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import clause_repo


@dataclass
class ClauseRef:
    clause_id: uuid.UUID
    ordinal: int
    heading_text: str | None
    char_start: int
    char_end: int


@dataclass
class NavigationIndex:
    contract_id: uuid.UUID
    # clause_type → ordered list of clause references (by ordinal)
    index: dict[str, list[ClauseRef]]
    # flat ordered list of all clause_types (in first-appearance order)
    toc: list[str]


async def build_navigation_index(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> NavigationIndex:
    """Build a deterministic clause-navigation index for a contract.

    Groups clauses by clause_type, preserving ordinal order within each group.
    toc lists clause_types in the order they first appear by ordinal.
    No LLM calls.
    """
    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)
    # clauses are ordered by ordinal (repo guarantees this)

    index: dict[str, list[ClauseRef]] = {}
    toc: list[str] = []  # first-appearance order

    for clause in clauses:
        ct = clause.clause_type
        if ct not in index:
            index[ct] = []
            toc.append(ct)
        index[ct].append(ClauseRef(
            clause_id=clause.id,
            ordinal=clause.ordinal,
            heading_text=clause.heading_text,
            char_start=clause.char_start,
            char_end=clause.char_end,
        ))

    return NavigationIndex(contract_id=contract_id, index=index, toc=toc)
