from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.qa_cache import QACache


async def get_cached_answer(
    session: AsyncSession,
    contract_id: uuid.UUID,
    question: str,
) -> QACache | None:
    """Return cached answer for (contract_id, question), or None."""
    result = await session.execute(
        select(QACache).where(
            QACache.contract_id == contract_id,
            QACache.question == question,
        )
    )
    return result.scalar_one_or_none()


async def create_cached_answer(
    session: AsyncSession,
    entry: QACache,
) -> QACache:
    """Persist a new QACache row. Caller must ensure no duplicate exists."""
    session.add(entry)
    await session.flush()
    return entry
