"""contract, review and outcome tables (task 1.3)

Applies ``playbook_plan.md`` section 4 ("Changes to existing tables") to
``clause``, ``contract``, ``flag``, ``risk_score``, ``redline``,
``decision_event`` and ``review_run``, and creates ``playbook_exception``
per section 3.13. Every new column added here is nullable.

Changes, table by table (section 4):

* ``clause`` — ``clause_type`` gains a FK to ``clause_family.key`` (``other``
  is already a family, from migration ``010``). New nullable ``issue_keys``
  jsonb. The FK is added only after backfilling any distinct existing
  ``clause_type`` value that is missing from ``clause_family`` with a
  minimal row, so the FK never fails to validate in an environment that
  already has clause rows (the live database has 0 rows in ``clause`` today,
  so this backfill has nothing to do there).
* ``contract`` — new nullable ``party_role`` text and ``context`` jsonb.
  (``contract_type`` already exists and is already nullable; the plan's note
  that it "is populated at upload" describes application behaviour wired up
  by a later task, not a schema change.)
* ``flag`` — new nullable ``rule_key``, ``position_id`` (FK →
  ``rule_position.id``), ``red_line_id`` (FK → ``red_line.id``), ``zone``,
  ``parameter_values`` jsonb.
* ``risk_score`` — new nullable ``max_zone``. (``score`` normalised to 0–1
  and ``weights_version`` moving to ``v2`` are value/behaviour changes for
  the scoring code to make, not schema changes: both columns already exist,
  already accept any float / text value, and this migration does not alter
  their type or add a range constraint — see the task report for why.)
* ``redline`` — the ``ck_redline_position`` check is widened from
  ``position IN ('preferred','fallback')`` to ``position = 'preferred' OR
  position ~ '^fallback_[0-9]+$'``. New nullable ``position_id`` (FK →
  ``rule_position.id``) and ``objection_id`` (FK → ``rule_objection.id``).
* ``decision_event`` — new nullable ``rule_id`` (FK → ``playbook_rule.id``),
  ``rule_key``, ``position_id`` (FK → ``rule_position.id``),
  ``playbook_version_id`` (FK → ``playbook_version.id``).
* ``review_run`` — new nullable ``playbook_version_ids`` jsonb. The
  ``ck_review_run_gate_decision`` check gains ``needs_approval``, alongside
  the existing ``auto_applied`` and ``escalated``.
* ``playbook_exception`` (new table, section 3.13) — an approved departure
  from the playbook, FK'd to ``contract``, ``review_run`` (nullable),
  ``playbook_rule``, ``rule_position`` (nullable) and ``approver_role``.
  It carries a ``status`` that transitions (``requested`` → ``approved`` /
  ``rejected`` / ``expired``), so it gets ``updated_at`` with ``onupdate``
  like every other mutable table here, not just ``created_at``.

  The task's "all new columns are nullable" instruction is read as applying
  to columns *added to the seven existing tables* (so an ``ALTER TABLE
  ADD COLUMN`` never fails against a live row); it is not read as
  overriding section 3.13's own nullability for this brand-new table, which
  has no existing rows to violate a constraint. Columns this table's plan
  row marks "nullable" (``review_run_id``, ``position_id``,
  ``give_get_obtained``, ``expires_at``) are nullable here; every other
  column is ``NOT NULL`` as section 3.13 implies by omission, matching how
  migration ``011`` treated new tables such as ``rule_position`` and
  ``red_line``. Flagged for review.

Like every migration, this one does not name the project schema in
``op.create_table`` / ``op.add_column`` etc.: ``migrations/env.py`` puts the
project schema first on the search path for the duration of the migration
transaction, so unqualified names resolve there.

The clause-family backfill (``_backfill_missing_clause_families`` below)
reads existing rows, which an offline ``--sql`` render cannot do (there is
no connection to read from). It is skipped when ``context.is_offline_mode()``
is true, exactly like the data-dependent steps in migration ``011``; the
live database has 0 rows in ``clause`` today, so skipping it changes
nothing there, and the FK still renders and applies correctly against zero
clause rows.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "l2m3n4o5p6q7"
down_revision: str | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backfill_missing_clause_families(bind: sa.engine.Connection) -> None:
    """Insert a minimal ``clause_family`` row for any ``clause.clause_type``
    value that is not already a family key, so the new FK always validates
    (task 1.3 item 5). The live database has 0 rows in ``clause`` today, so
    this is a no-op there; it exists for other environments."""
    missing = bind.execute(
        sa.text(
            "SELECT DISTINCT c.clause_type FROM clause c "
            "WHERE c.clause_type IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM clause_family cf WHERE cf.key = c.clause_type)"
        )
    ).fetchall()
    now = _now()
    for (clause_type,) in missing:
        bind.execute(
            sa.text(
                "INSERT INTO clause_family "
                "(key, name, category, description, synonyms, external_refs, sort_order, "
                "created_at, updated_at) "
                "VALUES (:key, :key, 'boilerplate', :description, '[]'::jsonb, '{}'::jsonb, "
                "999, :now, :now)"
            ),
            {
                "key": clause_type,
                "description": (
                    f"Backfilled family for existing clause_type {clause_type!r}, found in "
                    "clause rows but missing from the taxonomy at migration time."
                ),
                "now": now,
            },
        )


def upgrade() -> None:
    # Offline (`--sql`) rendering has no connection to read existing rows
    # from, so the clause-family backfill below is skipped in that mode (see
    # the module docstring). Every DDL statement still renders.
    bind = None if context.is_offline_mode() else op.get_bind()

    # ---- `clause` (plan section 4) -----------------------------------------
    op.add_column("clause", sa.Column("issue_keys", postgresql.JSONB(), nullable=True))

    if bind is not None:
        _backfill_missing_clause_families(bind)

    op.create_foreign_key(
        "fk_clause_clause_family", "clause", "clause_family", ["clause_type"], ["key"]
    )

    # ---- `contract` ---------------------------------------------------------
    op.add_column("contract", sa.Column("party_role", sa.Text(), nullable=True))
    op.add_column("contract", sa.Column("context", postgresql.JSONB(), nullable=True))

    # ---- `flag` ---------------------------------------------------------------
    op.add_column("flag", sa.Column("rule_key", sa.Text(), nullable=True))
    op.add_column("flag", sa.Column("position_id", sa.UUID(), nullable=True))
    op.add_column("flag", sa.Column("red_line_id", sa.UUID(), nullable=True))
    op.add_column("flag", sa.Column("zone", sa.Text(), nullable=True))
    op.add_column("flag", sa.Column("parameter_values", postgresql.JSONB(), nullable=True))
    op.create_foreign_key(
        "fk_flag_rule_position", "flag", "rule_position", ["position_id"], ["id"]
    )
    op.create_foreign_key("fk_flag_red_line", "flag", "red_line", ["red_line_id"], ["id"])

    # ---- `risk_score` -------------------------------------------------------
    op.add_column("risk_score", sa.Column("max_zone", sa.Text(), nullable=True))

    # ---- `redline` ------------------------------------------------------------
    op.drop_constraint("ck_redline_position", "redline", type_="check")
    op.create_check_constraint(
        "ck_redline_position",
        "redline",
        "position = 'preferred' OR position ~ '^fallback_[0-9]+$'",
    )
    op.add_column("redline", sa.Column("position_id", sa.UUID(), nullable=True))
    op.add_column("redline", sa.Column("objection_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_redline_position", "redline", "rule_position", ["position_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_redline_objection", "redline", "rule_objection", ["objection_id"], ["id"]
    )

    # ---- `decision_event` -----------------------------------------------------
    op.add_column("decision_event", sa.Column("rule_id", sa.UUID(), nullable=True))
    op.add_column("decision_event", sa.Column("rule_key", sa.Text(), nullable=True))
    op.add_column("decision_event", sa.Column("position_id", sa.UUID(), nullable=True))
    op.add_column("decision_event", sa.Column("playbook_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_decision_event_rule", "decision_event", "playbook_rule", ["rule_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_decision_event_position",
        "decision_event",
        "rule_position",
        ["position_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_decision_event_playbook_version",
        "decision_event",
        "playbook_version",
        ["playbook_version_id"],
        ["id"],
    )

    # ---- `review_run` -----------------------------------------------------------
    op.add_column(
        "review_run", sa.Column("playbook_version_ids", postgresql.JSONB(), nullable=True)
    )
    op.drop_constraint("ck_review_run_gate_decision", "review_run", type_="check")
    op.create_check_constraint(
        "ck_review_run_gate_decision",
        "review_run",
        "gate_decision IN ('auto_applied','escalated','needs_approval')",
    )

    # ---- `playbook_exception` (new table, section 3.13) ------------------------
    op.create_table(
        "playbook_exception",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("review_run_id", sa.UUID(), nullable=True),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("rule_key", sa.Text(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=True),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column("agreed_text", sa.Text(), nullable=False),
        sa.Column(
            "parameter_values", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("approver_role_id", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("give_get_obtained", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name="fk_playbook_exception_contract"
        ),
        sa.ForeignKeyConstraint(
            ["review_run_id"], ["review_run.id"], name="fk_playbook_exception_review_run"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_playbook_exception_rule"
        ),
        sa.ForeignKeyConstraint(
            ["position_id"], ["rule_position.id"], name="fk_playbook_exception_position"
        ),
        sa.ForeignKeyConstraint(
            ["approver_role_id"],
            ["approver_role.id"],
            name="fk_playbook_exception_approver_role",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_exception"),
    )
    op.create_index(
        "ix_playbook_exception_contract_id", "playbook_exception", ["contract_id"]
    )
    op.create_index(
        "ix_playbook_exception_rule_key", "playbook_exception", ["rule_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_playbook_exception_rule_key", table_name="playbook_exception")
    op.drop_index("ix_playbook_exception_contract_id", table_name="playbook_exception")
    op.drop_table("playbook_exception")

    op.drop_column("review_run", "playbook_version_ids")
    op.drop_constraint("ck_review_run_gate_decision", "review_run", type_="check")
    op.create_check_constraint(
        "ck_review_run_gate_decision",
        "review_run",
        "gate_decision IN ('auto_applied','escalated')",
    )

    op.drop_constraint("fk_decision_event_playbook_version", "decision_event", type_="foreignkey")
    op.drop_constraint("fk_decision_event_position", "decision_event", type_="foreignkey")
    op.drop_constraint("fk_decision_event_rule", "decision_event", type_="foreignkey")
    op.drop_column("decision_event", "playbook_version_id")
    op.drop_column("decision_event", "position_id")
    op.drop_column("decision_event", "rule_key")
    op.drop_column("decision_event", "rule_id")

    op.drop_constraint("fk_redline_objection", "redline", type_="foreignkey")
    op.drop_constraint("fk_redline_position", "redline", type_="foreignkey")
    op.drop_column("redline", "objection_id")
    op.drop_column("redline", "position_id")
    op.drop_constraint("ck_redline_position", "redline", type_="check")
    op.create_check_constraint(
        "ck_redline_position", "redline", "position IN ('preferred','fallback')"
    )

    op.drop_column("risk_score", "max_zone")

    op.drop_constraint("fk_flag_red_line", "flag", type_="foreignkey")
    op.drop_constraint("fk_flag_rule_position", "flag", type_="foreignkey")
    op.drop_column("flag", "parameter_values")
    op.drop_column("flag", "zone")
    op.drop_column("flag", "red_line_id")
    op.drop_column("flag", "position_id")
    op.drop_column("flag", "rule_key")

    op.drop_column("contract", "context")
    op.drop_column("contract", "party_role")

    op.drop_constraint("fk_clause_clause_family", "clause", type_="foreignkey")
    op.drop_column("clause", "issue_keys")
