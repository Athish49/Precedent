"""decision_event.counterparty_id becomes nullable (task 4.6)

``playbook_implementation.md`` task 4.6 item 6: application code was writing
a zero/nil UUID (``uuid.UUID(int=0)``) as a placeholder when a redline or
decision event was recorded for a contract with no known counterparty. The
fix removes that placeholder in application code (``app/workflows/
review_pipeline.py``, ``app/api/routes/redlines.py``) and widens this column
so ``NULL`` can be written instead. ``contract.counterparty_id`` is already
nullable (migration ``001``); this brings ``decision_event`` in line with it.

Like every migration, this does not name the project schema in ``op.*``
calls — ``migrations/env.py`` puts the project schema first on the search
path for the duration of the migration.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("decision_event", "counterparty_id", nullable=True)


def downgrade() -> None:
    op.alter_column("decision_event", "counterparty_id", nullable=False)
