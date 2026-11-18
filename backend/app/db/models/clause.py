import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Clause(Base):
    __tablename__ = "clause"
    __table_args__ = (
        Index("ix_clause_contract_ordinal", "contract_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract.id", name="fk_clause_contract"), nullable=False
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
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clause.id", name="fk_clause_embedding_clause"),
        nullable=False,
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_clause_embedding_contract"),
        nullable=False,
    )
    clause_type: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
