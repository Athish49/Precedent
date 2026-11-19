from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.clause import Clause
from app.db.models.contract import Contract

if TYPE_CHECKING:
    from app.services.document_processing.types import ClauseDraft


async def get_clauses_for_contracts(
    session: AsyncSession, contract_ids: list[uuid.UUID], *, level: str = "top"
) -> list[Clause]:
    """Return clauses for multiple contracts, grouped by clause_type.

    Reading rule (doc_proc plan section 7.3): defaults to each contract's
    current version. A clause with a null ``contract_version_id`` (written
    by the old pipeline, before task 5.2 makes the column not null) is
    treated as belonging to the current version, so existing behaviour is
    unchanged until every clause carries a real version id.
    """
    if not contract_ids:
        return []
    stmt = (
        select(Clause)
        .join(Contract, Contract.id == Clause.contract_id)
        .where(
            and_(
                Clause.contract_id.in_(contract_ids),
                or_(
                    Clause.contract_version_id == Contract.current_version_id,
                    Clause.contract_version_id.is_(None),
                ),
            )
        )
    )
    if level != "all":
        stmt = stmt.where(Clause.level == 1)
    stmt = stmt.order_by(Clause.clause_type, Clause.contract_id, Clause.ordinal)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_clauses_for_contract(
    session: AsyncSession,
    contract_id: uuid.UUID,
    *,
    level: str = "top",
    version_id: uuid.UUID | None = None,
) -> list[Clause]:
    """Return clauses for a contract, ordered by ordinal.

    Reading rule (doc_proc plan section 7.3): **current version, level 1**,
    unless asked otherwise. ``level="all"`` returns every level.
    ``version_id`` overrides the default of the contract's current version.
    A null ``contract_version_id`` on a clause is treated as belonging to
    the current version, so callers written against the old pipeline (which
    never set the column) keep seeing exactly what they see today.
    """
    version_clause = (
        version_id
        if version_id is not None
        else select(Contract.current_version_id).where(Contract.id == contract_id).scalar_subquery()
    )
    conditions = [
        Clause.contract_id == contract_id,
        or_(Clause.contract_version_id == version_clause, Clause.contract_version_id.is_(None)),
    ]
    if level != "all":
        conditions.append(Clause.level == 1)
    stmt = select(Clause).where(and_(*conditions)).order_by(Clause.ordinal)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_clause(session: AsyncSession, clause_id: uuid.UUID) -> Clause | None:
    """Fetch a single Clause by its UUID primary key."""
    result = await session.execute(select(Clause).where(Clause.id == clause_id))
    return result.scalar_one_or_none()


async def replace_clauses(
    session: AsyncSession,
    contract_id: uuid.UUID,
    version_id: uuid.UUID,
    drafts: Sequence["ClauseDraft"],
) -> list[Clause]:
    """Delete a version's clauses and insert *drafts* in their place.

    ``parent_ordinal`` on each draft is resolved to the inserted row's
    ``parent_id``: rows are inserted first (parents necessarily come before
    children in ``ordinal`` order, per the draft contract), then parent ids
    are back-filled in a second pass once every row has a primary key.
    ``text_sha256`` is computed here, per plan section 7.3 (D4).
    """
    await session.execute(delete(Clause).where(Clause.contract_version_id == version_id))

    ordered = sorted(drafts, key=lambda d: d.ordinal)
    by_ordinal: dict[int, Clause] = {}
    rows: list[Clause] = []
    for draft in ordered:
        row = Clause(
            id=uuid.uuid4(),
            contract_id=contract_id,
            contract_version_id=version_id,
            ordinal=draft.ordinal,
            clause_type=draft.clause_type,
            heading_text=draft.heading_text,
            text=draft.text,
            char_start=draft.char_start,
            char_end=draft.char_end,
            issue_keys=list(draft.issue_keys) if draft.issue_keys else None,
            clause_key=uuid.uuid4(),
            level=draft.level,
            section_number=draft.section_number,
            title=draft.title,
            page_start=draft.page_start,
            page_end=draft.page_end,
            type_source=draft.type_source,
            text_sha256=hashlib.sha256(draft.text.encode("utf-8")).hexdigest(),
        )
        session.add(row)
        rows.append(row)
        by_ordinal[draft.ordinal] = row

    await session.flush()

    for draft in ordered:
        if draft.parent_ordinal is not None:
            parent = by_ordinal.get(draft.parent_ordinal)
            if parent is not None:
                by_ordinal[draft.ordinal].parent_id = parent.id

    await session.flush()
    return rows
