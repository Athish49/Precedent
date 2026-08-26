from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Flag(Base):
    __tablename__ = "flag"
    __table_args__ = (
        CheckConstraint(
            "flag_type IN ("
            "'missing','prohibited','non_standard','high_risk','vague','inconsistent','deviation'"
            ")",
            name="ck_flag_flag_type",
        ),
        CheckConstraint("severity IN ('low','medium','high')", name="ck_flag_severity"),
        CheckConstraint("source IN ('deterministic','llm')", name="ck_flag_source"),
        Index("ix_flag_contract_id", "contract_id"),
        Index("ix_flag_clause_id", "clause_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_flag_contract"),
        nullable=False,
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # review_run_id has no FK — review_run table is created in a later task
    review_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    flag_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    matched_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RiskScore(Base):
    __tablename__ = "risk_score"
    __table_args__ = (
        CheckConstraint(
            "max_clause_severity IN ('low','medium','high')",
            name="ck_risk_score_max_severity",
        ),
        Index("ix_risk_score_contract_id", "contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_risk_score_contract"),
        nullable=False,
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_clause_severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    weights_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
