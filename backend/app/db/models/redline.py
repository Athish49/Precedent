from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Redline(Base):
    """A single clause redline proposal with tracked changes and NMS rationale."""

    __tablename__ = "redline"
    __table_args__ = (
        CheckConstraint(
            "stance_mode IN ('light','balanced','firm')",
            name="ck_redline_stance_mode",
        ),
        CheckConstraint(
            "position IN ('preferred','fallback')",
            name="ck_redline_position",
        ),
        CheckConstraint(
            "status IN ('proposed','accepted','rejected','auto_applied','escalated')",
            name="ck_redline_status",
        ),
        Index("ix_redline_contract_id", "contract_id"),
        Index("ix_redline_flag_id", "flag_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_redline_contract"),
        nullable=False,
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # review_run_id has no FK — review_run table is created in a later task
    review_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stance_mode: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_text: Mapped[str] = mapped_column(Text, nullable=False)
    tracked_changes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    alternatives: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    counterparty_comment: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
