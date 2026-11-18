"""Repository for the clause taxonomy and context lookup tables (task 1.1):
``agreement_type``, ``clause_family``, ``clause_issue`` and
``context_dimension``.

``agreement_type`` and ``clause_family`` are application reference data
inserted by migration 010, not by the seed loader
(``playbook_implementation.md`` section 3.0 rule 5); this repository still
provides full CRUD for them because the service layer, admin tooling and
tests all need a way to read and adjust them without touching SQL directly.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.taxonomy import AgreementType, ClauseFamily, ClauseIssue, ContextDimension

# ---------------------------------------------------------------------------
# AgreementType
# ---------------------------------------------------------------------------


async def create_agreement_type(
    session: AsyncSession, key: str, name: str, kind: str
) -> AgreementType:
    agreement_type = AgreementType(key=key, name=name, kind=kind)
    session.add(agreement_type)
    await session.flush()
    return agreement_type


async def get_agreement_type(session: AsyncSession, key: str) -> AgreementType | None:
    result = await session.execute(select(AgreementType).where(AgreementType.key == key))
    return result.scalar_one_or_none()


async def list_agreement_types(session: AsyncSession) -> list[AgreementType]:
    result = await session.execute(select(AgreementType))
    return list(result.scalars().all())


async def update_agreement_type(
    session: AsyncSession, key: str, **kwargs: object
) -> AgreementType | None:
    agreement_type = await get_agreement_type(session, key)
    if agreement_type is None:
        return None
    for field, value in kwargs.items():
        setattr(agreement_type, field, value)
    await session.flush()
    return agreement_type


async def delete_agreement_type(session: AsyncSession, key: str) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(AgreementType).where(AgreementType.key == key)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# ClauseFamily
# ---------------------------------------------------------------------------


async def create_clause_family(
    session: AsyncSession,
    key: str,
    name: str,
    category: str,
    description: str,
    **kwargs: object,
) -> ClauseFamily:
    """kwargs: synonyms, external_refs, sort_order."""
    family = ClauseFamily(
        key=key, name=name, category=category, description=description, **kwargs
    )
    session.add(family)
    await session.flush()
    return family


async def get_clause_family(session: AsyncSession, key: str) -> ClauseFamily | None:
    result = await session.execute(select(ClauseFamily).where(ClauseFamily.key == key))
    return result.scalar_one_or_none()


async def list_clause_families(session: AsyncSession) -> list[ClauseFamily]:
    result = await session.execute(select(ClauseFamily).order_by(ClauseFamily.sort_order.asc()))
    return list(result.scalars().all())


async def update_clause_family(
    session: AsyncSession, key: str, **kwargs: object
) -> ClauseFamily | None:
    family = await get_clause_family(session, key)
    if family is None:
        return None
    for field, value in kwargs.items():
        setattr(family, field, value)
    await session.flush()
    return family


async def delete_clause_family(session: AsyncSession, key: str) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(ClauseFamily).where(ClauseFamily.key == key)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# ClauseIssue
# ---------------------------------------------------------------------------


async def create_clause_issue(
    session: AsyncSession,
    family_key: str,
    key: str,
    name: str,
    description: str,
    **kwargs: object,
) -> ClauseIssue:
    """kwargs: detection_hints."""
    issue = ClauseIssue(
        family_key=family_key, key=key, name=name, description=description, **kwargs
    )
    session.add(issue)
    await session.flush()
    return issue


async def get_clause_issue(session: AsyncSession, issue_id: uuid.UUID) -> ClauseIssue | None:
    result = await session.execute(select(ClauseIssue).where(ClauseIssue.id == issue_id))
    return result.scalar_one_or_none()


async def get_clause_issue_by_key(
    session: AsyncSession, family_key: str, key: str
) -> ClauseIssue | None:
    result = await session.execute(
        select(ClauseIssue).where(
            ClauseIssue.family_key == family_key, ClauseIssue.key == key
        )
    )
    return result.scalar_one_or_none()


async def list_clause_issues(
    session: AsyncSession, family_key: str | None = None
) -> list[ClauseIssue]:
    """Return all clause issues, or only those for *family_key* when given."""
    stmt = select(ClauseIssue)
    if family_key is not None:
        stmt = stmt.where(ClauseIssue.family_key == family_key)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_clause_issue(
    session: AsyncSession, issue_id: uuid.UUID, **kwargs: object
) -> ClauseIssue | None:
    issue = await get_clause_issue(session, issue_id)
    if issue is None:
        return None
    for field, value in kwargs.items():
        setattr(issue, field, value)
    await session.flush()
    return issue


async def delete_clause_issue(session: AsyncSession, issue_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(ClauseIssue).where(ClauseIssue.id == issue_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# ContextDimension
# ---------------------------------------------------------------------------


async def create_context_dimension(
    session: AsyncSession,
    key: str,
    name: str,
    value_type: str,
    source: str,
    **kwargs: object,
) -> ContextDimension:
    """kwargs: values."""
    dimension = ContextDimension(
        key=key, name=name, value_type=value_type, source=source, **kwargs
    )
    session.add(dimension)
    await session.flush()
    return dimension


async def get_context_dimension(session: AsyncSession, key: str) -> ContextDimension | None:
    result = await session.execute(select(ContextDimension).where(ContextDimension.key == key))
    return result.scalar_one_or_none()


async def list_context_dimensions(session: AsyncSession) -> list[ContextDimension]:
    result = await session.execute(select(ContextDimension))
    return list(result.scalars().all())


async def update_context_dimension(
    session: AsyncSession, key: str, **kwargs: object
) -> ContextDimension | None:
    dimension = await get_context_dimension(session, key)
    if dimension is None:
        return None
    for field, value in kwargs.items():
        setattr(dimension, field, value)
    await session.flush()
    return dimension


async def delete_context_dimension(session: AsyncSession, key: str) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(ContextDimension).where(ContextDimension.key == key)
    ))
    return cursor.rowcount > 0
