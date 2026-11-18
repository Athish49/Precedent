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
    # New columns (task 1.3; plan section 4). Nullable; nothing populates
    # them yet — the resolution engine and zone evaluator (phase 4) do.
    rule_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rule_position.id", name="fk_flag_rule_position"),
        nullable=True,
    )
    red_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("red_line.id", name="fk_flag_red_line"),
        nullable=True,
    )
    zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameter_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
    # New column (task 1.3; plan section 4). Nullable; the three-zone gate
    # (task 4.5) is what sets it. `score` being normalised to 0-1 and
    # `weights_version` moving to "v2" are value changes the scoring code
    # makes later, not schema changes — both columns already accept any
    # float / text value.
    max_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
