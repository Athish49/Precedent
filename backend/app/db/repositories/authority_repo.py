"""Repository for the approval authority tables (task 1.1): ``approver_role``
and ``escalation_policy`` (``playbook_plan.md`` section 3.12).
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.authority import ApproverRole, EscalationPolicy

# ---------------------------------------------------------------------------
# ApproverRole
# ---------------------------------------------------------------------------


async def create_approver_role(
    session: AsyncSession,
    key: str,
    name: str,
    function: str,
    level: int,
    default_sla_hours: int,
) -> ApproverRole:
    role = ApproverRole(
        key=key, name=name, function=function, level=level, default_sla_hours=default_sla_hours
    )
    session.add(role)
    await session.flush()
    return role


async def get_approver_role(session: AsyncSession, role_id: uuid.UUID) -> ApproverRole | None:
    result = await session.execute(select(ApproverRole).where(ApproverRole.id == role_id))
    return result.scalar_one_or_none()


async def get_approver_role_by_key(session: AsyncSession, key: str) -> ApproverRole | None:
    result = await session.execute(select(ApproverRole).where(ApproverRole.key == key))
    return result.scalar_one_or_none()


async def list_approver_roles(session: AsyncSession) -> list[ApproverRole]:
    result = await session.execute(select(ApproverRole).order_by(ApproverRole.level.asc()))
    return list(result.scalars().all())


async def update_approver_role(
    session: AsyncSession, role_id: uuid.UUID, **kwargs: object
) -> ApproverRole | None:
    role = await get_approver_role(session, role_id)
    if role is None:
        return None
    for field, value in kwargs.items():
        setattr(role, field, value)
    await session.flush()
    return role


async def delete_approver_role(session: AsyncSession, role_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(ApproverRole).where(ApproverRole.id == role_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# EscalationPolicy
# ---------------------------------------------------------------------------


async def create_escalation_policy(
    session: AsyncSession,
    zone: str,
    approver_role_id: uuid.UUID,
    sla_hours: int,
    **kwargs: object,
) -> EscalationPolicy:
    """kwargs: playbook_id, clause_type, conditions, consult_role_ids,
    required_info, priority."""
    policy = EscalationPolicy(
        zone=zone, approver_role_id=approver_role_id, sla_hours=sla_hours, **kwargs
    )
    session.add(policy)
    await session.flush()
    return policy


async def get_escalation_policy(
    session: AsyncSession, policy_id: uuid.UUID
) -> EscalationPolicy | None:
    result = await session.execute(select(EscalationPolicy).where(EscalationPolicy.id == policy_id))
    return result.scalar_one_or_none()


async def list_escalation_policies(
    session: AsyncSession,
    playbook_id: uuid.UUID | None = None,
    clause_type: str | None = None,
    zone: str | None = None,
) -> list[EscalationPolicy]:
    """Return escalation policies, optionally filtered, most specific first.

    Ordering is by ``priority`` descending, matching
    ``playbook_plan.md`` section 3.12: "Most specific match wins; ties broken
    by priority." Filtering by exact ``playbook_id``/``clause_type`` values
    does not by itself implement the "null means all" fallback matching the
    resolution engine will need (task 4.2) — callers wanting that behaviour
    today should query with each filter unset in turn.
    """
    stmt = select(EscalationPolicy)
    if playbook_id is not None:
        stmt = stmt.where(EscalationPolicy.playbook_id == playbook_id)
    if clause_type is not None:
        stmt = stmt.where(EscalationPolicy.clause_type == clause_type)
    if zone is not None:
        stmt = stmt.where(EscalationPolicy.zone == zone)
    stmt = stmt.order_by(EscalationPolicy.priority.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_escalation_policy(
    session: AsyncSession, policy_id: uuid.UUID, **kwargs: object
) -> EscalationPolicy | None:
    policy = await get_escalation_policy(session, policy_id)
    if policy is None:
        return None
    for field, value in kwargs.items():
        setattr(policy, field, value)
    await session.flush()
    return policy


async def delete_escalation_policy(session: AsyncSession, policy_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(EscalationPolicy).where(EscalationPolicy.id == policy_id)
    ))
    return cursor.rowcount > 0
