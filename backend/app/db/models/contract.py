import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
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
    # New column (doc_proc task 1.2; migration 017; plan section 7.3, fixes
    # D16): set from the ``OWN_ORG_NAMES`` setting by the parties module
    # (task 2.6). Nothing writes it yet.
    is_own_org: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (
        CheckConstraint("source_format IN ('pdf', 'docx')", name="ck_contract_source_format"),
        CheckConstraint("paper_origin IN ('own', 'counterparty')", name="ck_contract_paper_origin"),
        CheckConstraint(
            "status IN ('processing', 'failed', 'ready', 'analyzed', 'redlined', 'executed')",
            name="ck_contract_status",
        ),
        CheckConstraint(
            "contract_type_source IN ('user', 'extracted')",
            name="ck_contract_contract_type_source",
        ),
        Index(
            "ix_contract_fts",
            func.to_tsvector("english", "canonical_text"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    paper_origin: Mapped[str] = mapped_column(Text, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("agreement_type.key", name="fk_contract_contract_type"),
        nullable=True,
        index=True,
    )
    contract_type_source: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # New columns (task 1.3; plan section 4). Nullable; `contract_type`
    # already existed and is populated at upload by a later task — not a
    # schema change here. `party_role` is `vendor` / `customer` / `mutual`;
    # `context` carries deal_value_band, counterparty_tier, data_sensitivity,
    # region and regimes.
    party_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ContractMetadata(Base):
    __tablename__ = "contract_metadata"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_metadata_contract", ondelete="CASCADE"),
        primary_key=True,
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    governing_law: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_renewal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # ``parties``, ``liability_cap``, ``notice_period_days``, ``payment_terms``,
    # ``financial_fields``, ``milestone_dates`` and ``extracted`` (the old
    # pipeline's untyped JSONB/ad-hoc columns) were removed from this model
    # in doc_proc task 5.1. The underlying database columns are dropped by
    # migration 019 (doc_proc task 5.2), a separate, destructive migration
    # that is never applied here without the user's explicit go-ahead.
    # New columns (doc_proc task 1.2; migration 017; plan section 7.3).
    # Task 3.1's ``write_metadata_projection`` writes these, from
    # ``contract_field`` values in force.
    contract_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_version.id",
            name="fk_contract_metadata_contract_version",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    expiry_is_derived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    initial_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renewal_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renewal_notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dispute_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_value_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    liability_cap_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    liability_cap_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    termination_for_convenience: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    termination_notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ContractVersion(Base):
    __tablename__ = "contract_version"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('version', 'amendment', 'addendum')", name="ck_contract_version_relation"
        ),
        # Migration 016: replaced non-unique index with a unique constraint.
        UniqueConstraint(
            "contract_id",
            "version_number",
            name="uq_contract_version_contract_version_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_version_contract", ondelete="CASCADE"),
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
    # New columns (doc_proc task 1.1; migration 016).
    file_sha256: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
