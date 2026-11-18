"""Repository for ``playbook_exception`` (task 1.3 model; task 4.6 writer).

Full CRUD for this table, including the ``requested`` -> ``approved`` /
``rejected`` / ``expired`` status transitions, belongs to task 4.8's
playbook API work. This module only provides what task 4.6 needs: creating
the ``requested`` row when a yellow-zone rung is accepted
(``playbook_plan.md`` section 5.4), plus a plain lookup.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exception import PlaybookException


async def create_exception(
    session: AsyncSession, exception: PlaybookException
) -> PlaybookException:
    """Persist a new ``PlaybookException`` row and return it after flush."""
    session.add(exception)
    await session.flush()
    return exception


async def get_exception(
    session: AsyncSession, exception_id: uuid.UUID
) -> PlaybookException | None:
    """Return a single exception by primary key, or None if not found."""
    result = await session.execute(
        select(PlaybookException).where(PlaybookException.id == exception_id)
    )
    return result.scalar_one_or_none()


async def list_exceptions_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[PlaybookException]:
    """Return all exceptions for a contract, oldest first."""
    result = await session.execute(
        select(PlaybookException)
        .where(PlaybookException.contract_id == contract_id)
        .order_by(PlaybookException.created_at)
    )
    return list(result.scalars().all())
