"""playbook tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playbook",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("practice_area", sa.Text(), nullable=False),
        sa.Column("precedence", sa.Integer(), nullable=False, server_default="0"),
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
        sa.CheckConstraint(
            "practice_area IN ('hipaa', 'gdpr', 'saas_msa', 'nda', 'dpa')",
            name="ck_playbook_practice_area",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook"),
    )
    op.create_table(
        "playbook_rule",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("clause_type", sa.Text(), nullable=False),
        sa.Column("preferred_language", sa.Text(), nullable=False, server_default=""),
        sa.Column("acceptable_variations", postgresql.JSONB(), nullable=True),
        sa.Column("prohibited_terms", postgresql.JSONB(), nullable=True),
        sa.Column("fallback_language", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("risk_weight", sa.Numeric(), nullable=False, server_default="1.0"),
        sa.Column("escalation_threshold", sa.Numeric(), nullable=True),
        sa.ForeignKeyConstraint(
            ["playbook_id"], ["playbook.id"], name="fk_playbook_rule_playbook"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_rule"),
    )
    op.create_index(
        "ix_playbook_rule_playbook_clause",
        "playbook_rule",
        ["playbook_id", "clause_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_playbook_rule_playbook_clause", table_name="playbook_rule")
    op.drop_table("playbook_rule")
    op.drop_table("playbook")
