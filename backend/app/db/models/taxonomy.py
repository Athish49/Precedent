"""Clause taxonomy and context lookups (task 1.1).

``AgreementType`` and ``ClauseFamily`` are application reference data: the
document pipeline depends on them, so their rows are inserted as literals by
migration ``010`` rather than by the seed loader (``playbook_plan.md``
section 11.3; ``playbook_implementation.md`` section 3.0 rule 5).
``ClauseIssue`` and ``ContextDimension`` tables are created here too, but
their content rows are loaded later by the seed loader (task 2.1) from
``taxonomy.yaml``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgreementType(Base):
    """Lookup replacing the five-value check constraint on ``playbook.practice_area``."""

    __tablename__ = "agreement_type"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ClauseFamily(Base):
    """The canonical clause type. Replaces the hard-coded synonym dictionary
    in ``app/services/document_processing/clause_types.py`` as the source of
    truth (that module is not changed until task 5.5).
    """

    __tablename__ = "clause_family"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    synonyms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    external_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ClauseIssue(Base):
    """A negotiable point inside a clause family. Rules attach here.

    Rows are loaded by the seed loader (task 2.1) from ``taxonomy.yaml``, not
    inserted by this migration.
    """

    __tablename__ = "clause_issue"
    __table_args__ = (
        UniqueConstraint("family_key", "key", name="uq_clause_issue_family_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clause_family.key", name="fk_clause_issue_family"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detection_hints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ContextDimension(Base):
    """A dimension of deal context used to evaluate rules and conditions.

    Rows (``deal_value_band``, ``counterparty_tier``, ``data_sensitivity``,
    ``region``, ``regimes``) are loaded by the seed loader (task 2.1) from
    ``authority.yaml``, not inserted by this migration.
    """

    __tablename__ = "context_dimension"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
