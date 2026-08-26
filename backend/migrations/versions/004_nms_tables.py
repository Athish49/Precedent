"""NMS tables — decision_event and counterparty_pattern view

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# counterparty_pattern view SQL (Data_Model §7)
_VIEW_SQL = """
CREATE VIEW counterparty_pattern AS
SELECT counterparty_id, clause_type,
       count(*) FILTER (WHERE outcome='accepted')::float / NULLIF(count(*),0) AS accept_rate,
       (array_agg(final_text ORDER BY created_at DESC) FILTER (WHERE final_text IS NOT NULL))[1] AS last_closed_text
FROM decision_event
GROUP BY counterparty_id, clause_type
"""

_DROP_VIEW_SQL = "DROP VIEW IF EXISTS counterparty_pattern"


def upgrade() -> None:
    op.create_table(
        "decision_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_decision_event_contract"),
            nullable=False,
        ),
        sa.Column(
            "counterparty_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("party.id", name="fk_decision_event_party"),
            nullable=False,
        ),
        sa.Column("clause_type", sa.Text, nullable=False),
        sa.Column("position_offered", sa.Text, nullable=False),
        sa.Column("recommended_stance", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("final_text", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('pending','accepted','rejected','countered')",
            name="ck_decision_event_outcome",
        ),
    )
    op.create_index(
        "ix_decision_event_counterparty_clause",
        "decision_event",
        ["counterparty_id", "clause_type"],
    )
    op.create_index("ix_decision_event_contract_id", "decision_event", ["contract_id"])

    # View must be created after the table it references.
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    # Drop view before table — the view depends on decision_event.
    op.execute(_DROP_VIEW_SQL)
    op.drop_index("ix_decision_event_contract_id", table_name="decision_event")
    op.drop_index("ix_decision_event_counterparty_clause", table_name="decision_event")
    op.drop_table("decision_event")
