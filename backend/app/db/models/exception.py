"""Playbook exceptions: approved departures from the playbook (task 1.3).

``PlaybookException`` is bucket 13 ("Outcomes") of ``playbook_plan.md``
section 2, defined fully in section 3.13. It records what was conceded, to
whom, under which rule and rung, with the approval that authorised it. A
yellow rung creates one of these in ``requested`` status (plan section 5.4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlaybookException(Base):
    """An approved departure from the playbook (``playbook_plan.md`` section 3.13).

    ``status`` moves through ``requested`` -> ``approved`` / ``rejected`` /
    ``expired``, so this table carries ``updated_at`` with ``onupdate`` like
    the other mutable playbook tables, in addition to ``created_at``.
    """

    __tablename__ = "playbook_exception"
    __table_args__ = (
        Index("ix_playbook_exception_contract_id", "contract_id"),
        Index("ix_playbook_exception_rule_key", "rule_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_playbook_exception_contract", ondelete="CASCADE"),
        nullable=False,
    )
    review_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_run.id", name="fk_playbook_exception_review_run"),
        nullable=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_playbook_exception_rule"),
        nullable=False,
    )
    rule_key: Mapped[str] = mapped_column(Text, nullable=False)
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rule_position.id", name="fk_playbook_exception_position"),
        nullable=True,
    )
    zone: Mapped[str] = mapped_column(Text, nullable=False)
    agreed_text: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    approver_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approver_role.id", name="fk_playbook_exception_approver_role"),
        nullable=False,
    )
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    give_get_obtained: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
