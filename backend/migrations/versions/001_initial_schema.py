"""initial schema — vector extension + core ingestion tables

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-25 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extension ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── party ────────────────────────────────────────────────────────────────
    op.create_table(
        "party",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_party"),
        sa.UniqueConstraint("normalized_name", name="uq_party_normalized_name"),
    )

    # ── contract (without current_version_id — circular FK resolved below) ──
    op.create_table(
        "contract",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("source_format", sa.Text(), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("paper_origin", sa.Text(), nullable=False),
        sa.Column("contract_type", sa.Text(), nullable=True),
        sa.Column("counterparty_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source_format IN ('pdf', 'docx')", name="ck_contract_source_format"),
        sa.CheckConstraint(
            "paper_origin IN ('own', 'counterparty')", name="ck_contract_paper_origin"
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'analyzed', 'redlined', 'executed')",
            name="ck_contract_status",
        ),
        sa.ForeignKeyConstraint(["counterparty_id"], ["party.id"], name="fk_contract_counterparty"),
        sa.PrimaryKeyConstraint("id", name="pk_contract"),
    )
    op.create_index("ix_contract_contract_type", "contract", ["contract_type"])
    op.create_index("ix_contract_counterparty_id", "contract", ["counterparty_id"])
    op.create_index("ix_contract_status", "contract", ["status"])
    op.execute(
        "CREATE INDEX ix_contract_fts ON contract USING gin(to_tsvector('english', canonical_text))"
    )

    # ── contract_version ─────────────────────────────────────────────────────
    op.create_table(
        "contract_version",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relation IN ('version', 'amendment', 'addendum')", name="ck_contract_version_relation"
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name="fk_contract_version_contract"
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"], ["contract_version.id"], name="fk_contract_version_parent"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_version"),
    )
    op.create_index(
        "ix_contract_version_contract_version",
        "contract_version",
        ["contract_id", "version_number"],
    )

    # ── Resolve circular FK: contract → contract_version ─────────────────────
    op.add_column("contract", sa.Column("current_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_contract_current_version",
        "contract",
        "contract_version",
        ["current_version_id"],
        ["id"],
    )

    # ── contract_metadata ────────────────────────────────────────────────────
    op.create_table(
        "contract_metadata",
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("parties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("governing_law", sa.Text(), nullable=True),
        sa.Column("liability_cap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=True),
        sa.Column("auto_renewal", sa.Boolean(), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("financial_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("milestone_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name="fk_contract_metadata_contract"
        ),
        sa.PrimaryKeyConstraint("contract_id", name="pk_contract_metadata"),
    )

    # ── clause ───────────────────────────────────────────────────────────────
    op.create_table(
        "clause",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("clause_type", sa.Text(), nullable=False),
        sa.Column("heading_text", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"], name="fk_clause_contract"),
        sa.PrimaryKeyConstraint("id", name="pk_clause"),
    )
    op.create_index("ix_clause_contract_ordinal", "clause", ["contract_id", "ordinal"])
    op.create_index("ix_clause_clause_type", "clause", ["clause_type"])

    # ── clause_embedding (vector column via raw DDL after extension is loaded)
    op.create_table(
        "clause_embedding",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clause_id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("clause_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["clause_id"], ["clause.id"], name="fk_clause_embedding_clause"),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name="fk_clause_embedding_contract"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_embedding"),
    )
    op.execute("ALTER TABLE clause_embedding ADD COLUMN embedding vector(384) NOT NULL")
    op.execute(
        "CREATE INDEX ix_clause_embedding_hnsw ON clause_embedding "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clause_embedding_hnsw")
    op.drop_table("clause_embedding")
    op.drop_index("ix_clause_clause_type", table_name="clause")
    op.drop_index("ix_clause_contract_ordinal", table_name="clause")
    op.drop_table("clause")
    op.drop_table("contract_metadata")
    op.drop_constraint("fk_contract_current_version", "contract", type_="foreignkey")
    op.drop_column("contract", "current_version_id")
    op.drop_index("ix_contract_version_contract_version", table_name="contract_version")
    op.drop_table("contract_version")
    op.execute("DROP INDEX IF EXISTS ix_contract_fts")
    op.drop_index("ix_contract_status", table_name="contract")
    op.drop_index("ix_contract_counterparty_id", table_name="contract")
    op.drop_index("ix_contract_contract_type", table_name="contract")
    op.drop_table("contract")
    op.drop_table("party")
    op.execute("DROP EXTENSION IF EXISTS vector")
