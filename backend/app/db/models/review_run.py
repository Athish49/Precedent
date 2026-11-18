from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewRun(Base):
    """A single gate evaluation run tracking the decision for a contract review."""

    __tablename__ = "review_run"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('manual','upload_event')",
            name="ck_review_run_trigger",
        ),
        # Gains 'needs_approval' by migration 012 (task 1.3; plan section 4)
        # for the yellow-zone routing outcome (plan section 5.3).
        CheckConstraint(
            "gate_decision IN ('auto_applied','escalated','needs_approval')",
            name="ck_review_run_gate_decision",
        ),
        CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_review_run_status",
        ),
        Index("ix_review_run_contract_id", "contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_review_run_contract"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    gate_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # New column (task 1.3; plan section 4). Nullable; the playbooks pinned
    # for reproducibility (plan section 5.1 step 4) are recorded here once
    # the resolution engine (task 4.2) runs.
    playbook_version_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
