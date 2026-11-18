"""playbook_rule: drop the five legacy flat language columns (task 5.5)

Drops ``preferred_language``, ``acceptable_variations``, ``prohibited_terms``,
``fallback_language`` and ``escalation_threshold`` from ``playbook_rule``.
Every production read and write of them has moved to the child tables
(``rule_position`` / ``red_line``), using the same mapping migration 011's
backfill defined:

- ``preferred_language`` → ``rule_position`` kind ``preferred``, rung 0,
  zone green
- ``acceptable_variations[i]`` → ``rule_position`` kind
  ``acceptable_variant``, rung null, zone green
- ``fallback_language`` → ``rule_position`` kind ``fallback``, rung 1,
  zone yellow
- ``prohibited_terms[i]`` → rule-scoped ``red_line``, condition_type
  ``phrase``, condition ``{"any": [term], "negation_guard": true}``,
  action ``block``
- ``escalation_threshold`` → no equivalent. Migration 011 never backfilled
  it and no code path ever read it. Its values are discarded.

Upgrade, before the drop: a catch-up backfill
-----------------------------------------------
Between migration 011 and this one, the rule CRUD API
(``POST /playbooks/{id}/rules``, ``PATCH /playbooks/rules/{id}``) still
wrote only the legacy columns. A rule created that way has legacy language
but no child rows. So the upgrade first re-runs 011's mapping in pure SQL:

- positions only for rules that have *no* ``rule_position`` rows at all
- red lines only for rules that have *no* rule-scoped ``red_line`` rows

Each target set is one ``INSERT ... SELECT``, so ``NOT EXISTS`` is evaluated
against the snapshot from before that statement's own inserts. That makes
the backfill idempotent. Unlike 011's Python backfill, it also renders
under ``alembic upgrade --sql``.

Two cases are not reconciled, so their legacy values are lost:

- A rule that already has child rows *and* had its legacy columns edited
  later through the old PATCH. Positions were already authoritative for
  redline generation.
- Every ``escalation_threshold``.

The preferred position is backfilled only when ``preferred_language`` is
non-empty. 011 always made one, but an empty rung-0 position carries
nothing.

Downgrade
---------
Recreates the five columns with their original types. ``preferred_language``
is ``Text NOT NULL DEFAULT ''`` (as migration 002 created it) and the other
four are nullable. Then it repopulates four of them, best effort, from the
child rows, reversing the mapping above:

- rung-0 / ``preferred`` language
- ``acceptable_variant`` languages, in label order
- the lowest-rung ``fallback``
- the ``any`` phrases of rule-scoped ``phrase`` red lines

``escalation_threshold`` comes back all NULL. Data loss on downgrade is
expected and accepted. That covers any second and later fallback rungs,
non-phrase red lines, and every column the child tables carry that the flat
shape cannot.

Like every migration, this one does not name the project schema in ``op.*``
calls. ``migrations/env.py`` puts the project schema first on the search
path for the duration of the migration.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o5p6q7r8s9t0"
down_revision: str | None = "n4o5p6q7r8s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_COLUMNS = (
    "preferred_language",
    "acceptable_variations",
    "prohibited_terms",
    "fallback_language",
    "escalation_threshold",
)

# Same labels / notes / keys as migration 011's build_position_rows and
# build_red_line_rows, so catch-up rows are indistinguishable from 011's.
_BACKFILL_POSITIONS = """
INSERT INTO rule_position (id, rule_id, kind, rung, label, language, zone, internal_note)
SELECT gen_random_uuid(), src.rule_id, src.kind, src.rung, src.label, src.language,
       src.zone, src.internal_note
FROM (
    SELECT r.id AS rule_id, 'preferred' AS kind, 0 AS rung,
           'Preferred position (migrated)' AS label, r.preferred_language AS language,
           'green' AS zone, 'Backfilled from legacy preferred_language.' AS internal_note
    FROM playbook_rule r
    WHERE COALESCE(r.preferred_language, '') <> ''
    UNION ALL
    SELECT r.id, 'acceptable_variant', NULL,
           'Acceptable variant ' || v.ord || ' (migrated)', v.value,
           'green', 'Backfilled from legacy acceptable_variations.'
    FROM playbook_rule r
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(r.acceptable_variations) = 'array'
             THEN r.acceptable_variations ELSE '[]'::jsonb END
    ) WITH ORDINALITY AS v(value, ord)
    UNION ALL
    SELECT r.id, 'fallback', 1, 'Fallback 1 (migrated)', r.fallback_language,
           'yellow', 'Backfilled from legacy fallback_language.'
    FROM playbook_rule r
    WHERE COALESCE(r.fallback_language, '') <> ''
) AS src
WHERE NOT EXISTS (SELECT 1 FROM rule_position p WHERE p.rule_id = src.rule_id)
"""

_BACKFILL_RED_LINES = """
INSERT INTO red_line (id, scope, rule_id, playbook_id, key, description, condition_type,
                      condition, action, rationale)
SELECT gen_random_uuid(), 'rule', r.id, NULL,
       'legacy-' || r.id::text || '-' || t.ord,
       'Prohibited term: ''' || t.value || '''.',
       'phrase',
       jsonb_build_object('any', jsonb_build_array(t.value), 'negation_guard', true),
       'block',
       'Backfilled from legacy prohibited_terms.'
FROM playbook_rule r
CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE WHEN jsonb_typeof(r.prohibited_terms) = 'array'
         THEN r.prohibited_terms ELSE '[]'::jsonb END
) WITH ORDINALITY AS t(value, ord)
WHERE NOT EXISTS (SELECT 1 FROM red_line x WHERE x.rule_id = r.id)
"""

# Best-effort reverse mapping for downgrade (see module docstring).
_REPOPULATE_LEGACY = """
UPDATE playbook_rule r SET
    preferred_language = COALESCE((
        SELECT p.language FROM rule_position p
        WHERE p.rule_id = r.id AND (p.kind = 'preferred' OR p.rung = 0)
        ORDER BY (p.kind = 'preferred') DESC, p.created_at, p.id
        LIMIT 1
    ), ''),
    acceptable_variations = (
        SELECT jsonb_agg(p.language ORDER BY p.label, p.id) FROM rule_position p
        WHERE p.rule_id = r.id AND p.kind = 'acceptable_variant'
    ),
    fallback_language = (
        SELECT p.language FROM rule_position p
        WHERE p.rule_id = r.id AND p.kind = 'fallback'
        ORDER BY p.rung NULLS LAST, p.created_at, p.id
        LIMIT 1
    ),
    prohibited_terms = (
        SELECT jsonb_agg(phrase.value ORDER BY x.key, phrase.ord)
        FROM red_line x
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(x.condition -> 'any') = 'array'
                 THEN x.condition -> 'any' ELSE '[]'::jsonb END
        ) WITH ORDINALITY AS phrase(value, ord)
        WHERE x.rule_id = r.id AND x.scope = 'rule' AND x.condition_type = 'phrase'
    )
"""


def upgrade() -> None:
    op.execute(sa.text(_BACKFILL_POSITIONS))
    op.execute(sa.text(_BACKFILL_RED_LINES))
    for column in _LEGACY_COLUMNS:
        op.drop_column("playbook_rule", column)


def downgrade() -> None:
    op.add_column(
        "playbook_rule",
        sa.Column("preferred_language", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "playbook_rule", sa.Column("acceptable_variations", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "playbook_rule", sa.Column("prohibited_terms", postgresql.JSONB(), nullable=True)
    )
    op.add_column("playbook_rule", sa.Column("fallback_language", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("escalation_threshold", sa.Numeric(), nullable=True))
    op.execute(sa.text(_REPOPULATE_LEGACY))
