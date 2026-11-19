"""``contract_field``: one row per extracted value (doc_proc task 1.2).

Plan section 7.3. This is the source of truth for field values; ``
ContractMetadata`` is a typed projection written from it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContractField(Base):
    __tablename__ = "contract_field"
    __table_args__ = (
        CheckConstraint(
            "source IN ('extract', 'derived', 'user')", name="ck_contract_field_source"
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'low')",
            name="ck_contract_field_confidence",
        ),
        UniqueConstraint(
            "contract_version_id", "field_key", "source", name="uq_contract_field_version_key_source"
        ),
        Index("ix_contract_field_key_contract", "field_key", "contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_field_contract", ondelete="CASCADE"),
        nullable=False,
    )
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_version.id", name="fk_contract_field_contract_version", ondelete="CASCADE"
        ),
        nullable=False,
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clause_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clause.id", name="fk_contract_field_clause", ondelete="SET NULL"),
        nullable=True,
    )
    ingest_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingest_run.id", name="fk_contract_field_ingest_run", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
