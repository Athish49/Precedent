import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Party(Base):
    __tablename__ = "party"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (
        CheckConstraint("source_format IN ('pdf', 'docx')", name="ck_contract_source_format"),
        CheckConstraint("paper_origin IN ('own', 'counterparty')", name="ck_contract_paper_origin"),
        CheckConstraint(
            "status IN ('processing', 'analyzed', 'redlined', 'executed')",
            name="ck_contract_status",
        ),
        Index(
            "ix_contract_fts",
            func.to_tsvector("english", "canonical_text"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    paper_origin: Mapped[str] = mapped_column(Text, nullable=False)
    contract_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("party.id", name="fk_contract_counterparty"),
        nullable=True,
        index=True,
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract_version.id", use_alter=True, name="fk_contract_current_version"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="processing", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContractMetadata(Base):
    __tablename__ = "contract_metadata"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_metadata_contract"),
        primary_key=True,
    )
    parties: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    governing_law: Mapped[str | None] = mapped_column(Text, nullable=True)
    liability_cap: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_renewal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    financial_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    milestone_dates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extracted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ContractVersion(Base):
    __tablename__ = "contract_version"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('version', 'amendment', 'addendum')", name="ck_contract_version_relation"
        ),
        Index("ix_contract_version_contract_version", "contract_id", "version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_version_contract"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract_version.id", name="fk_contract_version_parent"),
        nullable=True,
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
