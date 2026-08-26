"""analysis tables — flag and risk_score

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flag",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_flag_contract"),
            nullable=False,
        ),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), nullable=True),
        # review_run_id: no FK — review_run table is created in a later migration
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("flag_type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=True),
        sa.Column("char_end", sa.Integer, nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("matched_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "flag_type IN ('missing','prohibited','non_standard','high_risk','vague','inconsistent','deviation')",
            name="ck_flag_flag_type",
        ),
        sa.CheckConstraint("severity IN ('low','medium','high')", name="ck_flag_severity"),
        sa.CheckConstraint("source IN ('deterministic','llm')", name="ck_flag_source"),
    )
    op.create_index("ix_flag_contract_id", "flag", ["contract_id"])
    op.create_index("ix_flag_clause_id", "flag", ["clause_id"])

    op.create_table(
        "risk_score",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_risk_score_contract"),
            nullable=False,
        ),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("max_clause_severity", sa.Text, nullable=True),
        sa.Column("weights_version", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_clause_severity IN ('low','medium','high')",
            name="ck_risk_score_max_severity",
        ),
    )
    op.create_index("ix_risk_score_contract_id", "risk_score", ["contract_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_score_contract_id", table_name="risk_score")
    op.drop_table("risk_score")
    op.drop_index("ix_flag_clause_id", table_name="flag")
    op.drop_index("ix_flag_contract_id", table_name="flag")
    op.drop_table("flag")
