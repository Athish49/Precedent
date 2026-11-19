import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Clause(Base):
    __tablename__ = "clause"
    __table_args__ = (
        Index("ix_clause_contract_ordinal", "contract_id", "ordinal"),
        # Added by migration 016 (doc_proc task 1.1).
        CheckConstraint("char_end > char_start", name="ck_clause_char_end_gt_start"),
        CheckConstraint("char_start >= 0", name="ck_clause_char_start_gte_zero"),
        CheckConstraint("level >= 1", name="ck_clause_level_gte_one"),
        CheckConstraint(
            "type_source IN ('extract', 'dictionary', 'none')", name="ck_clause_type_source"
        ),
        Index("ix_clause_contract_clause_key", "contract_id", "clause_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_clause_contract", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # FK to `clause_family.key` added by migration 012 (task 1.3; plan
    # section 4). `other` is a family, from migration 010, so any clause
    # whose heading did not match a canonical type still resolves.
    clause_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clause_family.key", name="fk_clause_clause_family"),
        nullable=False,
        index=True,
    )
    heading_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # New column (task 1.3; plan section 4): issues detected inside the
    # clause, keyed by `clause_issue.key`. Nullable; nothing populates it yet.
    issue_keys: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # New columns (doc_proc task 1.1; migration 016). Made NOT NULL by
    # migration 019 (task 5.2): it was left nullable only so the old
    # pipeline (deleted in task 5.1) could keep writing clauses without a
    # version id. That pipeline no longer exists, and migration 019 deletes
    # every row that still has no contract_version_id, so the column can be
    # tightened.
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contract_version.id", name="fk_clause_contract_version", ondelete="CASCADE"
        ),
        nullable=False,
    )
    clause_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clause.id", name="fk_clause_parent", ondelete="CASCADE"),
        nullable=True,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    section_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="none", default="none"
    )
    text_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClauseEmbedding(Base):
    __tablename__ = "clause_embedding"
    __table_args__ = (
        Index(
            "ix_clause_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Added by migration 017 (doc_proc task 1.2; plan section 7.3, fixes
        # D15): re-embedding a clause must update its row, not duplicate it.
        UniqueConstraint("clause_id", name="uq_clause_embedding_clause_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE added by migration 016 (doc_proc task 1.1).
        ForeignKey("clause.id", name="fk_clause_embedding_clause", ondelete="CASCADE"),
        nullable=False,
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_clause_embedding_contract", ondelete="CASCADE"),
        nullable=False,
    )
    clause_type: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    # New column (doc_proc task 1.2; migration 017; plan section 7.3, fixes
    # D15): which embedding model produced the vector. Nullable; nothing
    # writes it yet (task 3.2).
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
