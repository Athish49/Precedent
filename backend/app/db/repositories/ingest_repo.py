from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ingest_run import IngestRun


async def start_run(
    session: AsyncSession,
    version_id: uuid.UUID,
    *,
    provider: str | None = None,
    processor: str | None = None,
    processor_version: str | None = None,
    parse_engine_version: str | None = None,
) -> IngestRun:
    """Insert a ``running`` ingest_run row for *version_id*."""
    run = IngestRun(
        id=uuid.uuid4(),
        contract_version_id=version_id,
        provider=provider,
        processor=processor,
        processor_version=processor_version,
        parse_engine_version=parse_engine_version,
        status="running",
    )
    session.add(run)
    await session.flush()
    return run


async def _get_run(session: AsyncSession, run_id: uuid.UUID) -> IngestRun | None:
    result = await session.execute(select(IngestRun).where(IngestRun.id == run_id))
    return result.scalar_one_or_none()


async def finish_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    warnings: list[str] | None = None,
    credits_used: float | None = None,
    extend_file_id: str | None = None,
    extend_extract_run_id: str | None = None,
    extend_parse_run_id: str | None = None,
    raw_extract_key: str | None = None,
    raw_parse_key: str | None = None,
) -> IngestRun | None:
    """Mark the run ``succeeded`` and record what it produced. Returns None
    if the run row does not exist.
    """
    run = await _get_run(session, run_id)
    if run is None:
        return None
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    if warnings is not None:
        run.warnings = list(warnings)
    if credits_used is not None:
        run.credits_used = credits_used
    if extend_file_id is not None:
        run.extend_file_id = extend_file_id
    if extend_extract_run_id is not None:
        run.extend_extract_run_id = extend_extract_run_id
    if extend_parse_run_id is not None:
        run.extend_parse_run_id = extend_parse_run_id
    if raw_extract_key is not None:
        run.raw_extract_key = raw_extract_key
    if raw_parse_key is not None:
        run.raw_parse_key = raw_parse_key
    await session.flush()
    return run


async def fail_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    failure_reason: str,
    *,
    warnings: list[str] | None = None,
) -> IngestRun | None:
    """Mark the run ``failed`` with *failure_reason*. Returns None if the
    run row does not exist.
    """
    run = await _get_run(session, run_id)
    if run is None:
        return None
    run.status = "failed"
    run.failure_reason = failure_reason
    run.finished_at = datetime.now(UTC)
    if warnings is not None:
        run.warnings = list(warnings)
    await session.flush()
    return run


async def latest_run(session: AsyncSession, version_id: uuid.UUID) -> IngestRun | None:
    """Return the most recently started run for *version_id*, or None."""
    result = await session.execute(
        select(IngestRun)
        .where(IngestRun.contract_version_id == version_id)
        .order_by(IngestRun.started_at.desc())
    )
    return result.scalars().first()
