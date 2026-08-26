from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.playbook import Playbook, PlaybookRule

# ---------------------------------------------------------------------------
# Playbook CRUD
# ---------------------------------------------------------------------------


async def create_playbook(
    session: AsyncSession,
    name: str,
    practice_area: str,
    precedence: int = 0,
) -> Playbook:
    """Create and persist a new Playbook."""
    pb = Playbook(name=name, practice_area=practice_area, precedence=precedence)
    session.add(pb)
    await session.flush()
    return pb


async def get_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> Playbook | None:
    """Fetch a Playbook by id, or None if not found."""
    result = await session.execute(select(Playbook).where(Playbook.id == playbook_id))
    return result.scalar_one_or_none()


async def list_playbooks(session: AsyncSession) -> list[Playbook]:
    """Return all playbooks ordered by precedence descending."""
    result = await session.execute(select(Playbook).order_by(Playbook.precedence.desc()))
    return list(result.scalars().all())


async def list_playbooks_by_areas(
    session: AsyncSession,
    practice_areas: list[str],
) -> list[Playbook]:
    """Return playbooks whose practice_area is in *practice_areas*.

    Ordered by precedence DESC, then practice_area ASC for deterministic
    tie-breaking when two playbooks share the same precedence value.
    """
    if not practice_areas:
        return []
    result = await session.execute(
        select(Playbook)
        .where(Playbook.practice_area.in_(practice_areas))
        .order_by(Playbook.precedence.desc(), Playbook.practice_area.asc())
    )
    return list(result.scalars().all())


async def update_playbook(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    **kwargs: object,
) -> Playbook | None:
    """Update fields on a Playbook (name, practice_area, precedence).

    Returns the updated Playbook, or None if not found.
    """
    pb = await get_playbook(session, playbook_id)
    if pb is None:
        return None
    for key, value in kwargs.items():
        setattr(pb, key, value)
    await session.flush()
    return pb


async def delete_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> bool:
    """Delete a Playbook by id. Returns True if a row was deleted."""
    cursor = cast(CursorResult, await session.execute(
        delete(Playbook).where(Playbook.id == playbook_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# PlaybookRule CRUD
# ---------------------------------------------------------------------------


async def create_rule(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    clause_type: str,
    preferred_language: str = "",
    **kwargs: object,
) -> PlaybookRule:
    """Create and persist a new PlaybookRule.

    kwargs: acceptable_variations, prohibited_terms, fallback_language,
            required, risk_weight, escalation_threshold
    """
    rule = PlaybookRule(
        playbook_id=playbook_id,
        clause_type=clause_type,
        preferred_language=preferred_language,
        **kwargs,
    )
    session.add(rule)
    await session.flush()
    return rule


async def get_rule(session: AsyncSession, rule_id: uuid.UUID) -> PlaybookRule | None:
    """Fetch a PlaybookRule by id, or None if not found."""
    result = await session.execute(select(PlaybookRule).where(PlaybookRule.id == rule_id))
    return result.scalar_one_or_none()


async def list_rules(session: AsyncSession, playbook_id: uuid.UUID) -> list[PlaybookRule]:
    """Return all rules for a given playbook."""
    result = await session.execute(
        select(PlaybookRule).where(PlaybookRule.playbook_id == playbook_id)
    )
    return list(result.scalars().all())


async def update_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    **kwargs: object,
) -> PlaybookRule | None:
    """Update fields on a PlaybookRule. Returns the updated rule, or None if not found."""
    rule = await get_rule(session, rule_id)
    if rule is None:
        return None
    for key, value in kwargs.items():
        setattr(rule, key, value)
    await session.flush()
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID) -> bool:
    """Delete a PlaybookRule by id. Returns True if a row was deleted."""
    cursor = cast(CursorResult, await session.execute(
        delete(PlaybookRule).where(PlaybookRule.id == rule_id)
    ))
    return cursor.rowcount > 0


async def get_rules_by_clause_type(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    clause_type: str,
) -> list[PlaybookRule]:
    """Fetch rules for a playbook filtered by clause_type.

    Used by S2 (scoring stage) to retrieve matching rules per clause.
    """
    result = await session.execute(
        select(PlaybookRule).where(
            PlaybookRule.playbook_id == playbook_id,
            PlaybookRule.clause_type == clause_type,
        )
    )
    return list(result.scalars().all())
