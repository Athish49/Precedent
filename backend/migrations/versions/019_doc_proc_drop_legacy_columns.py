"""document processing: drop the old pipeline's untyped columns (task 5.2)

**This migration deletes data. It is destructive and one-way: the rows it
deletes and the column data it drops cannot be recovered by downgrading.**

The old document-processing pipeline (deleted in task 5.1) is the only code
that ever wrote ``contract_metadata.parties``, ``financial_fields``,
``milestone_dates``, ``liability_cap``, ``notice_period_days``,
``payment_terms`` and ``extracted``. Task 1.2 (migration 017) added the
typed replacement columns without dropping these; task 3.6 (migration 018)
repointed every analytics view off them. Nothing reads them any more, so
this migration drops them outright.

Per plan section 7.4, existing contracts in the remote database are seed
data and are meant to be **re-ingested, not back-filled**: there is no
migration path from the old pipeline's untyped shape to the new typed one.
Consistent with that, this migration also **permanently deletes every row**
in ``clause``, ``clause_embedding`` and ``contract_metadata`` that has no
``contract_version_id`` — such a row predates the new pipeline entirely and
is superseded by re-ingesting the source file through the new upload flow,
not migrated forward. Once those orphaned rows are gone, every remaining
``clause`` row has a real ``contract_version_id``, so the column is made
``NOT NULL`` (task 1.1 left it nullable only so the old pipeline could keep
writing clauses without one; the old pipeline no longer exists).

Upgrade order: delete orphaned rows first (so the NOT NULL constraint can be
added without violation), then drop the seven old columns.

Downgrade: recreates the seven ``contract_metadata`` columns, empty
(nullable, with their original types) — **no data is restored**, since the
original values were never captured anywhere else. ``clause.contract_version_id``
is relaxed back to nullable. The rows deleted by the upgrade are gone for
good; downgrading this migration does not bring them back.

Like every migration, this one does not name the project schema in ``op.*``
calls; ``migrations/env.py`` puts it first on the search path for the
duration of the migration transaction.

**This migration must never be applied to the real database by an agent.**
It is rendered offline only, with ``alembic upgrade head --sql`` /
``downgrade ... --sql``. Applying it for real is a separate step that
requires the user's own explicit go-ahead at that moment.

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s9t0u1v2w3x4"
down_revision: str | None = "r8s9t0u1v2w3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_COLUMNS = (
    "parties",
    "financial_fields",
    "milestone_dates",
    "liability_cap",
    "notice_period_days",
    "payment_terms",
    "extracted",
)


def upgrade() -> None:
    # ── 1. Delete orphaned rows (plan section 7.4): any row with no
    # contract_version_id predates the new pipeline and is superseded by
    # re-ingestion, not migrated forward. Order matters only for clarity;
    # none of these three tables has a foreign key onto another in this
    # list, so there is no ordering constraint between them.
    op.execute(sa.text("DELETE FROM clause WHERE contract_version_id IS NULL"))
    op.execute(sa.text("DELETE FROM clause_embedding WHERE clause_id NOT IN (SELECT id FROM clause)"))
    op.execute(sa.text("DELETE FROM contract_metadata WHERE contract_version_id IS NULL"))

    # ── 2. Tighten clause.contract_version_id to NOT NULL now that every
    # remaining row has one (task 1.1 left it nullable only for the old
    # pipeline, which is now deleted).
    op.alter_column("clause", "contract_version_id", nullable=False)

    # ── 3. Drop the old pipeline's untyped contract_metadata columns.
    for column in _OLD_COLUMNS:
        op.drop_column("contract_metadata", column)


def downgrade() -> None:
    # ── 3. Recreate the seven columns, empty. No data is restored: the
    # values dropped by the upgrade were never captured anywhere else.
    op.add_column(
        "contract_metadata",
        sa.Column("parties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contract_metadata",
        sa.Column("liability_cap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contract_metadata", sa.Column("notice_period_days", sa.Integer(), nullable=True)
    )
    op.add_column("contract_metadata", sa.Column("payment_terms", sa.Text(), nullable=True))
    op.add_column(
        "contract_metadata",
        sa.Column("financial_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contract_metadata",
        sa.Column("milestone_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contract_metadata",
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── 2. Relax clause.contract_version_id back to nullable.
    op.alter_column("clause", "contract_version_id", nullable=True)

    # ── 1. The rows deleted by the upgrade are gone for good; this
    # downgrade does not and cannot bring them back.
