"""``contract_party`` and ``contract_signatory`` (doc_proc task 1.2).

Plan section 7.3. ``contract_party`` replaces ``contract_metadata.parties``
(a JSON list with no link to ``party``). ``contract_signatory`` gives
signatories a home (plan finding D18).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContractParty(Base):
    __tablename__ = "contract_party"
    __table_args__ = (
        CheckConstraint(
            "role IN ('own', 'counterparty', 'other')", name="ck_contract_party_role"
        ),
        UniqueConstraint("contract_id", "party_id", name="uq_contract_party_contract_party"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_contract_party_contract", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("party.id", name="fk_contract_party_party", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    role_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContractSignatory(Base):
    __tablename__ = "contract_signatory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_version.id", name="fk_contract_signatory_contract_version", ondelete="CASCADE"
        ),
        nullable=False,
    )
    contract_party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_party.id", name="fk_contract_signatory_contract_party", ondelete="SET NULL"
        ),
        nullable=True,
    )
    printed_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_signed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    signed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
