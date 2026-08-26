"""ReviewRun repository — create, query, and complete review run rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.review_run import ReviewRun


async def create_review_run(session: AsyncSession, run: ReviewRun) -> ReviewRun:
    """Persist a new ReviewRun row and return it after flush."""
    session.add(run)
    await session.flush()
    return run


async def get_review_run(session: AsyncSession, run_id: uuid.UUID) -> ReviewRun | None:
    """Return a single ReviewRun by primary key, or None if not found."""
    result = await session.execute(
        select(ReviewRun).where(ReviewRun.id == run_id)
    )
    return result.scalar_one_or_none()


async def complete_review_run(
    session: AsyncSession,
    run: ReviewRun,
    gate_decision: str,
    gate_reason: dict,
) -> ReviewRun:
    """Set gate_decision, gate_reason, status='completed', completed_at=now(). Flush."""
    run.gate_decision = gate_decision
    run.gate_reason = gate_reason
    run.status = "completed"
    run.completed_at = datetime.now(tz=UTC)
    await session.flush()
    return run


async def fail_review_run(session: AsyncSession, run: ReviewRun) -> ReviewRun:
    """Set status='failed', completed_at=now(). Flush."""
    run.status = "failed"
    run.completed_at = datetime.now(tz=UTC)
    await session.flush()
    return run
