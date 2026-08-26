"""redline table — S3 persistence layer

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redline",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_redline_contract"),
            nullable=False,
        ),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("flag_id", postgresql.UUID(as_uuid=True), nullable=True),
        # review_run_id has no FK — review_run table is created in a later task
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stance_mode", sa.Text, nullable=False),
        sa.Column("position", sa.Text, nullable=False),
        sa.Column("replacement_text", sa.Text, nullable=False),
        sa.Column("tracked_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("alternatives", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("counterparty_comment", sa.Text, nullable=False),
        sa.Column("rationale", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stance_mode IN ('light','balanced','firm')",
            name="ck_redline_stance_mode",
        ),
        sa.CheckConstraint(
            "position IN ('preferred','fallback')",
            name="ck_redline_position",
        ),
        sa.CheckConstraint(
            "status IN ('proposed','accepted','rejected','auto_applied','escalated')",
            name="ck_redline_status",
        ),
    )
    op.create_index("ix_redline_contract_id", "redline", ["contract_id"])
    op.create_index("ix_redline_flag_id", "redline", ["flag_id"])


def downgrade() -> None:
    op.drop_index("ix_redline_flag_id", table_name="redline")
    op.drop_index("ix_redline_contract_id", table_name="redline")
    op.drop_table("redline")
