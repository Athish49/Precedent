from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Playbook(Base):
    __tablename__ = "playbook"
    __table_args__ = (
        CheckConstraint(
            "practice_area IN ('hipaa', 'gdpr', 'saas_msa', 'nda', 'dpa')",
            name="ck_playbook_practice_area",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    practice_area: Mapped[str] = mapped_column(Text, nullable=False)
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlaybookRule(Base):
    __tablename__ = "playbook_rule"
    __table_args__ = (
        Index("ix_playbook_rule_playbook_clause", "playbook_id", "clause_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_playbook_rule_playbook"),
        nullable=False,
    )
    clause_type: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acceptable_variations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    prohibited_terms: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    fallback_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_weight: Mapped[float] = mapped_column(Numeric, nullable=False, default=1.0)
    escalation_threshold: Mapped[float | None] = mapped_column(Numeric, nullable=True)
