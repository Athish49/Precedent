"""Approval authority tables (task 1.1).

Both tables are created here, but their content rows (the 9 approver roles
and 36+ escalation policies) are loaded later by the seed loader (task 2.1)
from ``authority.yaml`` — they are company content, not application
reference data (``playbook_implementation.md`` section 3.0 rule 5).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApproverRole(Base):
    """A role that can approve a yellow or red escalation."""

    __tablename__ = "approver_role"
    __table_args__ = (UniqueConstraint("key", name="uq_approver_role_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    function: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    default_sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EscalationPolicy(Base):
    """The approval matrix: who decides and who is consulted for a deviation.

    A position's own ``approver_role_id`` takes precedence over this matrix.
    The matrix covers deviations that match no position, and red lines with
    ``action = escalate``.
    """

    __tablename__ = "escalation_policy"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_escalation_policy_playbook"),
        nullable=True,
    )
    clause_type: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("clause_family.key", name="fk_escalation_policy_clause_family"),
        nullable=True,
    )
    zone: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approver_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approver_role.id", name="fk_escalation_policy_approver_role"),
        nullable=False,
    )
    consult_role_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    required_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
