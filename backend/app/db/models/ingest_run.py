"""``ingest_run`` (doc_proc task 1.2).

Plan section 7.3 (fixes D17): a record of which service and processor
version produced a version's data, when, and what failed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ck_ingest_run_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_version.id", name="fk_ingest_run_contract_version", ondelete="CASCADE"
        ),
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    processor: Mapped[str | None] = mapped_column(Text, nullable=True)
    processor_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    extend_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    extend_extract_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    extend_parse_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    credits_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_extract_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_parse_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
