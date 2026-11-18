"""clause_family: add missing 'term and survival' synonym for 'term' (task 5.5 prep)

The clause-misclassification fix (section 1 of ``playbook_verification.md``)
added the heading synonym ``"term and survival"`` to the hardcoded
``_SYNONYMS`` dict in ``app/services/document_processing/clause_types.py``
*after* migration ``010`` seeded ``clause_family.synonyms`` from that same
dict. Task 5.5 retires ``_SYNONYMS`` in favor of loading synonyms from
``clause_family`` at startup, so this one synonym must land in the table
first or the classification fix regresses the moment the dict is deleted.

Every other synonym in the current ``_SYNONYMS`` dict is already present in
migration 010's seed data (verified by diffing the dict against every
family's ``synonyms`` list); this is the only gap.

Like every migration, this does not name the project schema in ``op.*``
calls — ``migrations/env.py`` puts the project schema first on the search
path for the duration of the migration.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n4o5p6q7r8s9"
down_revision: str | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYNONYM = "term and survival"
_FAMILY_KEY = "term"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE clause_family "
            "SET synonyms = synonyms || CAST(:synonym_json AS jsonb) "
            "WHERE key = :family_key "
            "AND NOT (synonyms @> CAST(:synonym_json AS jsonb))"
        ).bindparams(
            sa.bindparam("synonym_json", f'["{_SYNONYM}"]'),
            sa.bindparam("family_key", _FAMILY_KEY),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE clause_family "
            "SET synonyms = synonyms - CAST(:synonym AS text) "
            "WHERE key = :family_key"
        ).bindparams(
            sa.bindparam("synonym", _SYNONYM),
            sa.bindparam("family_key", _FAMILY_KEY),
        )
    )
