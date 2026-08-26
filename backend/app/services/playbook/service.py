"""S6 Playbook service — CRUD over playbooks and rules.

Thin orchestration layer: validates inputs, delegates to the repo, and
translates missing-row (None/False) into AppError(404).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.models.playbook import Playbook, PlaybookRule
from app.db.repositories import playbook_repo
from app.schemas.playbook import (
    _VALID_PRACTICE_AREAS,
    PlaybookCreate,
    PlaybookUpdate,
    RuleCreate,
    RuleUpdate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_practice_area(practice_area: str) -> None:
    if practice_area not in _VALID_PRACTICE_AREAS:
        raise AppError(
            400,
            "invalid_practice_area",
            f"practice_area must be one of {sorted(_VALID_PRACTICE_AREAS)!r}, "
            f"got {practice_area!r}",
        )


# ---------------------------------------------------------------------------
# Playbook CRUD
# ---------------------------------------------------------------------------


async def create_playbook(session: AsyncSession, body: PlaybookCreate) -> Playbook:
    _validate_practice_area(body.practice_area)
    pb = await playbook_repo.create_playbook(
        session,
        name=body.name,
        practice_area=body.practice_area,
        precedence=body.precedence,
    )
    await session.commit()
    await session.refresh(pb)
    return pb


async def list_playbooks(session: AsyncSession) -> list[Playbook]:
    return await playbook_repo.list_playbooks(session)


async def get_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> Playbook:
    pb = await playbook_repo.get_playbook(session, playbook_id)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    return pb


async def update_playbook(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    body: PlaybookUpdate,
) -> Playbook:
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    if "practice_area" in kwargs:
        _validate_practice_area(kwargs["practice_area"])
    pb = await playbook_repo.update_playbook(session, playbook_id, **kwargs)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    await session.commit()
    await session.refresh(pb)
    return pb


async def delete_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> None:
    deleted = await playbook_repo.delete_playbook(session, playbook_id)
    if not deleted:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    await session.commit()


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


async def create_rule(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    body: RuleCreate,
) -> PlaybookRule:
    # Verify parent exists.
    await get_playbook(session, playbook_id)
    rule = await playbook_repo.create_rule(
        session,
        playbook_id=playbook_id,
        clause_type=body.clause_type,
        preferred_language=body.preferred_language,
        acceptable_variations=body.acceptable_variations,
        prohibited_terms=body.prohibited_terms,
        fallback_language=body.fallback_language,
        required=body.required,
        risk_weight=body.risk_weight,
        escalation_threshold=body.escalation_threshold,
    )
    await session.commit()
    await session.refresh(rule)
    return rule


async def list_rules(
    session: AsyncSession,
    playbook_id: uuid.UUID,
) -> list[PlaybookRule]:
    # Verify parent exists so missing playbook → 404, not empty list.
    await get_playbook(session, playbook_id)
    return await playbook_repo.list_rules(session, playbook_id)


async def update_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    body: RuleUpdate,
) -> PlaybookRule:
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    rule = await playbook_repo.update_rule(session, rule_id, **kwargs)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID) -> None:
    deleted = await playbook_repo.delete_rule(session, rule_id)
    if not deleted:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    await session.commit()
