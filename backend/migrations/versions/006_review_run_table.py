"""review_run table — gate decision persistence

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_review_run_contract"),
            nullable=False,
        ),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("gate_decision", sa.Text, nullable=True),
        sa.Column("gate_reason", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "trigger IN ('manual','upload_event')",
            name="ck_review_run_trigger",
        ),
        sa.CheckConstraint(
            "gate_decision IN ('auto_applied','escalated')",
            name="ck_review_run_gate_decision",
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_review_run_status",
        ),
    )
    op.create_index("ix_review_run_contract_id", "review_run", ["contract_id"])


def downgrade() -> None:
    op.drop_index("ix_review_run_contract_id", table_name="review_run")
    op.drop_table("review_run")
