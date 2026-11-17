"""obligation and alert tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h8i9j0k1l2m3"
down_revision: str | None = "g7h8i9j0k1l2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "obligation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_obligation_contract"),
            nullable=False,
        ),
        sa.Column("commitment", sa.Text, nullable=False),
        sa.Column("owner", sa.Text, nullable=False),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column("deliverable", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=True),
        sa.Column("char_end", sa.Integer, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('open','met','overdue')", name="ck_obligation_status"),
    )
    op.create_index("ix_obligation_contract_id", "obligation", ["contract_id"])

    op.create_table(
        "alert",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_alert_contract"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default="false"),
        sa.CheckConstraint(
            "alert_type IN ('deadline','renewal','compliance_pass','compliance_fail')",
            name="ck_alert_type",
        ),
    )
    op.create_index("ix_alert_contract_id", "alert", ["contract_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_contract_id", table_name="alert")
    op.drop_table("alert")
    op.drop_index("ix_obligation_contract_id", table_name="obligation")
    op.drop_table("obligation")
