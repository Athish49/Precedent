"""playbook structure: versions, rules and children (task 1.2)

Extends ``playbook`` and ``playbook_rule`` and creates the rest of the
playbook data model (``playbook_plan.md`` sections 3.2 to 3.10):
``playbook_version``, ``playbook_change_log``, ``rule_position``,
``rule_parameter``, ``red_line``, ``rule_objection``, ``rule_dependency`` and
``rule_test_case``.

Backfill, in order:

1. ``playbook.key`` from a slug of ``name``; ``layer``, ``party_role``,
   ``paper_scope``, ``jurisdiction`` and ``status`` to fixed values. Pure SQL
   (an ``UPDATE`` built from the row's own ``name`` column) — it needs no row
   read into Python, so it is correct for zero rows, for many rows, and when
   rendered offline by ``alembic upgrade head --sql``.
2. One ``1.0`` / ``published`` ``playbook_version`` per existing playbook,
   pinned as ``playbook.current_version_id``.
3. ``playbook_rule.rule_key`` (``clause_type || '.general'``, pure SQL) and
   ``playbook_rule.playbook_version_id`` (pointed at the version from step 2).
4. ``rule_position`` and ``red_line`` rows built from the legacy
   ``preferred_language``, ``acceptable_variations``, ``fallback_language``
   and ``prohibited_terms`` columns, via the pure helper functions below
   (``build_position_rows`` / ``build_red_line_rows``). These two need an
   actual row to iterate and a UUID per child row, so they run through
   Python — but the functions themselves take plain data and are covered by
   a unit test against ``tests/fixtures/legacy_playbook_rows.py`` with no
   database at all.

Steps 2 to 4 above read existing rows, which an offline ``--sql`` render
cannot do (there is no connection to read from — see the Alembic docs on
offline mode). They are skipped when ``context.is_offline_mode()`` is true;
the live database has 0 rows in ``playbook`` and ``playbook_rule`` today, so
skipping them changes nothing there, and the DDL around them still renders
and applies correctly with zero legacy rows.

Like every migration, this one does not name the project schema in
``op.create_table`` / ``op.alter_table`` etc.: ``migrations/env.py`` puts the
project schema first on the search path for the duration of the migration
transaction, so unqualified names resolve there.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-11-16
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Pure backfill helpers (task 1.2 done-when: unit-tested against the 29-row
# fixture in tests/fixtures/legacy_playbook_rows.py). Each takes plain data —
# a rule id and a dict of the legacy columns — and returns plain dict rows
# ready to insert. Neither function touches a connection, a session or the
# ``op`` module, so the same logic runs identically inside a unit test and
# inside the migration (see ``_backfill_rule_children`` below).
# ---------------------------------------------------------------------------


def build_position_rows(rule_id: uuid.UUID, rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Backfill ``rule_position`` rows from one legacy ``playbook_rule`` row.

    One ``preferred`` position from ``preferred_language``; one
    ``acceptable_variant`` per entry of ``acceptable_variations``; one rung-1
    ``fallback`` (zone yellow, no approver) when ``fallback_language`` is a
    non-null, non-empty string (task 1.2 item 6).
    """
    rows: list[dict[str, Any]] = [
        {
            "id": uuid.uuid4(),
            "rule_id": rule_id,
            "kind": "preferred",
            "rung": 0,
            "label": "Preferred position (migrated)",
            "language": rule.get("preferred_language") or "",
            "summary": None,
            "zone": "green",
            "approver_role_id": None,
            "conditions": None,
            "give_get": None,
            "internal_note": "Backfilled from legacy preferred_language.",
        }
    ]

    for index, variant in enumerate(rule.get("acceptable_variations") or [], start=1):
        rows.append(
            {
                "id": uuid.uuid4(),
                "rule_id": rule_id,
                "kind": "acceptable_variant",
                "rung": None,
                "label": f"Acceptable variant {index} (migrated)",
                "language": variant,
                "summary": None,
                "zone": "green",
                "approver_role_id": None,
                "conditions": None,
                "give_get": None,
                "internal_note": "Backfilled from legacy acceptable_variations.",
            }
        )

    fallback_language = rule.get("fallback_language")
    if fallback_language:
        rows.append(
            {
                "id": uuid.uuid4(),
                "rule_id": rule_id,
                "kind": "fallback",
                "rung": 1,
                "label": "Fallback 1 (migrated)",
                "language": fallback_language,
                "summary": None,
                "zone": "yellow",
                "approver_role_id": None,
                "conditions": None,
                "give_get": None,
                "internal_note": "Backfilled from legacy fallback_language.",
            }
        )

    return rows


def build_red_line_rows(rule_id: uuid.UUID, rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Backfill rule-scoped ``red_line`` rows from legacy ``prohibited_terms``.

    One ``phrase`` red line per entry, with ``negation_guard: true`` and
    action ``block`` (task 1.2 item 6).
    """
    rows: list[dict[str, Any]] = []
    for index, term in enumerate(rule.get("prohibited_terms") or [], start=1):
        rows.append(
            {
                "id": uuid.uuid4(),
                "scope": "rule",
                "rule_id": rule_id,
                "playbook_id": None,
                "key": f"legacy-{rule_id}-{index}",
                "description": f"Prohibited term: {term!r}.",
                "condition_type": "phrase",
                "condition": {"any": [term], "negation_guard": True},
                "action": "block",
                "approver_role_id": None,
                "rationale": "Backfilled from legacy prohibited_terms.",
            }
        )
    return rows


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Connection-backed glue. Only called when there is a real connection to read
# from (see the module docstring and ``upgrade()`` below).
# ---------------------------------------------------------------------------


def _backfill_playbook_versions(bind: sa.engine.Connection) -> None:
    """Insert a ``1.0`` / ``published`` version for every playbook that has
    none yet, and point ``playbook.current_version_id`` at it (item 3)."""
    rows = bind.execute(
        sa.text("SELECT id FROM playbook WHERE current_version_id IS NULL")
    ).fetchall()
    now = _now()
    for (playbook_id,) in rows:
        version_id = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO playbook_version "
                "(id, playbook_id, version, status, effective_from, change_summary, "
                "created_by, approved_by, published_at, created_at, updated_at) "
                "VALUES (:id, :playbook_id, '1.0', 'published', :now, "
                "'Initial published version, backfilled from the legacy playbook_rule "
                "rows.', 'migration', 'migration', :now, :now, :now)"
            ),
            {"id": version_id, "playbook_id": playbook_id, "now": now},
        )
        bind.execute(
            sa.text(
                "UPDATE playbook SET current_version_id = :version_id WHERE id = :playbook_id"
            ),
            {"version_id": version_id, "playbook_id": playbook_id},
        )


def _backfill_rule_version_ids(bind: sa.engine.Connection) -> None:
    """Point every ``playbook_rule`` row at its playbook's ``1.0`` version."""
    bind.execute(
        sa.text(
            "UPDATE playbook_rule SET playbook_version_id = "
            "(SELECT current_version_id FROM playbook WHERE playbook.id = playbook_rule.playbook_id) "
            "WHERE playbook_version_id IS NULL"
        )
    )


def _backfill_rule_children(bind: sa.engine.Connection) -> None:
    """Backfill ``rule_position`` and ``red_line`` rows from the legacy
    ``playbook_rule`` columns (item 6), using the pure helpers above."""
    rows = bind.execute(
        sa.text(
            "SELECT id, clause_type, preferred_language, acceptable_variations, "
            "fallback_language, prohibited_terms FROM playbook_rule"
        )
    ).fetchall()

    for rule_id, clause_type, preferred_language, acceptable_variations, fallback_language, prohibited_terms in rows:
        rule = {
            "clause_type": clause_type,
            "preferred_language": preferred_language,
            "acceptable_variations": acceptable_variations,
            "fallback_language": fallback_language,
            "prohibited_terms": prohibited_terms,
        }

        for position in build_position_rows(rule_id, rule):
            bind.execute(
                sa.text(
                    "INSERT INTO rule_position "
                    "(id, rule_id, kind, rung, label, language, summary, zone, "
                    "approver_role_id, conditions, give_get, internal_note) "
                    "VALUES (:id, :rule_id, :kind, :rung, :label, :language, :summary, "
                    ":zone, :approver_role_id, :conditions, :give_get, :internal_note)"
                ),
                {
                    **position,
                    "conditions": (
                        json.dumps(position["conditions"])
                        if position["conditions"] is not None
                        else None
                    ),
                },
            )

        for red_line in build_red_line_rows(rule_id, rule):
            bind.execute(
                sa.text(
                    "INSERT INTO red_line "
                    "(id, scope, rule_id, playbook_id, key, description, condition_type, "
                    "condition, action, approver_role_id, rationale) "
                    "VALUES (:id, :scope, :rule_id, :playbook_id, :key, :description, "
                    ":condition_type, :condition, :action, :approver_role_id, :rationale)"
                ),
                {**red_line, "condition": json.dumps(red_line["condition"])},
            )


def upgrade() -> None:
    # Offline (`--sql`) rendering has no connection to read existing rows
    # from, so the data-dependent backfill steps below are skipped in that
    # mode (see the module docstring). Every DDL statement still renders.
    bind = None if context.is_offline_mode() else op.get_bind()

    # ---- 1. Extend `playbook` (plan 3.2) -----------------------------------
    op.drop_constraint("ck_playbook_practice_area", "playbook", type_="check")

    op.add_column("playbook", sa.Column("key", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("layer", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("party_role", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("paper_scope", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("jurisdiction", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("business_unit", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("owner_role_id", sa.UUID(), nullable=True))
    op.add_column("playbook", sa.Column("parent_playbook_id", sa.UUID(), nullable=True))
    op.add_column("playbook", sa.Column("applies_when", postgresql.JSONB(), nullable=True))
    op.add_column("playbook", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("status", sa.Text(), nullable=True))
    op.add_column("playbook", sa.Column("current_version_id", sa.UUID(), nullable=True))
    op.add_column("playbook", sa.Column("review_cadence_days", sa.Integer(), nullable=True))
    op.add_column("playbook", sa.Column("next_review_at", sa.Date(), nullable=True))

    op.create_foreign_key(
        "fk_playbook_agreement_type", "playbook", "agreement_type", ["practice_area"], ["key"]
    )
    op.create_foreign_key(
        "fk_playbook_owner_role", "playbook", "approver_role", ["owner_role_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_playbook_parent", "playbook", "playbook", ["parent_playbook_id"], ["id"]
    )

    # Backfill `key` from a slug of `name`, and the rest to fixed values.
    # Pure SQL: no row needs to be read into Python, so this is correct for
    # zero rows (the live database today) and for N rows alike, and it
    # renders fine for an offline `--sql` dry run.
    op.execute(
        sa.text(
            "UPDATE playbook SET key = lower(regexp_replace(trim(name), "
            "'[^a-zA-Z0-9]+', '-', 'g')) WHERE key IS NULL"
        )
    )
    op.execute(sa.text("UPDATE playbook SET layer = 'agreement' WHERE layer IS NULL"))
    op.execute(sa.text("UPDATE playbook SET party_role = 'vendor' WHERE party_role IS NULL"))
    op.execute(sa.text("UPDATE playbook SET paper_scope = 'both' WHERE paper_scope IS NULL"))
    op.execute(sa.text("UPDATE playbook SET jurisdiction = 'global' WHERE jurisdiction IS NULL"))
    op.execute(sa.text("UPDATE playbook SET status = 'active' WHERE status IS NULL"))

    op.alter_column("playbook", "layer", nullable=False, server_default="agreement")
    op.alter_column("playbook", "party_role", nullable=False, server_default="vendor")
    op.alter_column("playbook", "paper_scope", nullable=False, server_default="both")
    op.alter_column("playbook", "jurisdiction", nullable=False, server_default="global")
    op.alter_column("playbook", "status", nullable=False, server_default="active")

    # Unique constraint on `key` added AFTER the backfill, so it never has to
    # validate against pre-backfill NULLs (task 1.2 item 1).
    op.create_unique_constraint("uq_playbook_key", "playbook", ["key"])

    # ---- 2. `playbook_version` / `playbook_change_log` (plan 3.3) ---------
    op.create_table(
        "playbook_version",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["playbook_id"], ["playbook.id"], name="fk_playbook_version_playbook", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_version"),
        sa.UniqueConstraint("playbook_id", "version", name="uq_playbook_version_playbook_version"),
    )

    op.create_table(
        "playbook_change_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_version_id", sa.UUID(), nullable=False),
        sa.Column("rule_key", sa.Text(), nullable=False),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["playbook_version_id"],
            ["playbook_version.id"],
            name="fk_playbook_change_log_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_change_log"),
    )

    op.create_foreign_key(
        "fk_playbook_current_version", "playbook", "playbook_version", ["current_version_id"], ["id"]
    )

    # ---- 3. One `1.0` version per existing playbook (item 3) ---------------
    if bind is not None:
        _backfill_playbook_versions(bind)

    # ---- 4. Extend `playbook_rule` (plan 3.4) ------------------------------
    op.add_column("playbook_rule", sa.Column("playbook_version_id", sa.UUID(), nullable=True))
    op.add_column("playbook_rule", sa.Column("issue_id", sa.UUID(), nullable=True))
    op.add_column("playbook_rule", sa.Column("rule_key", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("position_summary", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("risk_rationale", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("negotiable", sa.Boolean(), nullable=True))
    op.add_column("playbook_rule", sa.Column("default_zone", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("needs_human_judgment", sa.Boolean(), nullable=True))
    op.add_column("playbook_rule", sa.Column("judgment_note", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("applies_when", postgresql.JSONB(), nullable=True))
    op.add_column("playbook_rule", sa.Column("detection_guidance", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("source_ref", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("authored_by", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("approved_by", sa.Text(), nullable=True))
    op.add_column("playbook_rule", sa.Column("last_reviewed_at", sa.Date(), nullable=True))

    op.create_foreign_key(
        "fk_playbook_rule_version", "playbook_rule", "playbook_version", ["playbook_version_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_playbook_rule_issue", "playbook_rule", "clause_issue", ["issue_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_playbook_rule_clause_family", "playbook_rule", "clause_family", ["clause_type"], ["key"]
    )

    # Backfill `rule_key` — pure SQL, no row needs to be read into Python.
    op.execute(
        sa.text(
            "UPDATE playbook_rule SET rule_key = clause_type || '.general' WHERE rule_key IS NULL"
        )
    )

    # Backfill `playbook_version_id`: point every rule at its playbook's new
    # `1.0` version (step 3 above). Needs real rows, so online-only.
    if bind is not None:
        _backfill_rule_version_ids(bind)

    # FK to `playbook` gains cascade delete (drop and recreate).
    op.drop_constraint("fk_playbook_rule_playbook", "playbook_rule", type_="foreignkey")
    op.create_foreign_key(
        "fk_playbook_rule_playbook",
        "playbook_rule",
        "playbook",
        ["playbook_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ---- 5. Child tables, cascading from `playbook_rule` -------------------
    op.create_table(
        "rule_position",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("rung", sa.Integer(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column("approver_role_id", sa.UUID(), nullable=True),
        sa.Column("conditions", postgresql.JSONB(), nullable=True),
        sa.Column("give_get", sa.Text(), nullable=True),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_rule_position_rule", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["approver_role_id"], ["approver_role.id"], name="fk_rule_position_approver_role"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_position"),
    )

    op.create_table(
        "rule_parameter",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("preferred_value", postgresql.JSONB(), nullable=True),
        sa.Column("green_limit", postgresql.JSONB(), nullable=True),
        sa.Column("yellow_limit", postgresql.JSONB(), nullable=True),
        sa.Column("allowed_values", postgresql.JSONB(), nullable=True),
        sa.Column("extraction_hint", sa.Text(), nullable=True),
        sa.Column("context_overrides", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_rule_parameter_rule", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_parameter"),
        sa.UniqueConstraint("rule_id", "key", name="uq_rule_parameter_rule_key"),
    )

    op.create_table(
        "red_line",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("playbook_id", sa.UUID(), nullable=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("condition_type", sa.Text(), nullable=False),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("approver_role_id", sa.UUID(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_red_line_rule", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbook.id"], name="fk_red_line_playbook"),
        sa.ForeignKeyConstraint(
            ["approver_role_id"], ["approver_role.id"], name="fk_red_line_approver_role"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_red_line"),
    )

    op.create_table(
        "rule_objection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("objection", sa.Text(), nullable=False),
        sa.Column("their_rationale", sa.Text(), nullable=True),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("talking_points", postgresql.JSONB(), nullable=True),
        sa.Column("recommended_position_id", sa.UUID(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("counterparty_profile", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_rule_objection_rule", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_objection"),
    )
    op.create_foreign_key(
        "fk_rule_objection_recommended_position",
        "rule_objection",
        "rule_position",
        ["recommended_position_id"],
        ["id"],
    )

    op.create_table(
        "rule_dependency",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("related_rule_key", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_rule_dependency_rule", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_dependency"),
    )

    op.create_table(
        "rule_test_case",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sample_text", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("expected_zone", sa.Text(), nullable=True),
        sa.Column("expected_position_rung", sa.Integer(), nullable=True),
        sa.Column("expected_red_line_key", sa.Text(), nullable=True),
        sa.Column("is_trap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["playbook_rule.id"], name="fk_rule_test_case_rule", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_test_case"),
    )

    # ---- 6. Backfill children from legacy columns (item 6) -----------------
    if bind is not None:
        _backfill_rule_children(bind)

    # ---- 7. Uniqueness (item 7) ---------------------------------------------
    # `playbook_version(playbook_id, version)` is already unique from table
    # creation above. This one is added last, after both of its columns have
    # been backfilled.
    op.create_unique_constraint(
        "uq_playbook_rule_version_rule_key", "playbook_rule", ["playbook_version_id", "rule_key"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_playbook_rule_version_rule_key", "playbook_rule", type_="unique"
    )

    op.drop_table("rule_test_case")
    op.drop_table("rule_dependency")
    op.drop_constraint(
        "fk_rule_objection_recommended_position", "rule_objection", type_="foreignkey"
    )
    op.drop_table("rule_objection")
    op.drop_table("red_line")
    op.drop_table("rule_parameter")
    op.drop_table("rule_position")

    op.drop_constraint("fk_playbook_rule_playbook", "playbook_rule", type_="foreignkey")
    op.create_foreign_key(
        "fk_playbook_rule_playbook", "playbook_rule", "playbook", ["playbook_id"], ["id"]
    )

    op.drop_constraint("fk_playbook_rule_clause_family", "playbook_rule", type_="foreignkey")
    op.drop_constraint("fk_playbook_rule_issue", "playbook_rule", type_="foreignkey")
    op.drop_constraint("fk_playbook_rule_version", "playbook_rule", type_="foreignkey")

    for column in (
        "last_reviewed_at",
        "approved_by",
        "authored_by",
        "source_ref",
        "detection_guidance",
        "applies_when",
        "judgment_note",
        "needs_human_judgment",
        "default_zone",
        "negotiable",
        "risk_rationale",
        "position_summary",
        "title",
        "rule_key",
        "issue_id",
        "playbook_version_id",
    ):
        op.drop_column("playbook_rule", column)

    op.drop_constraint("fk_playbook_current_version", "playbook", type_="foreignkey")
    op.drop_table("playbook_change_log")
    op.drop_table("playbook_version")

    op.drop_constraint("uq_playbook_key", "playbook", type_="unique")

    op.alter_column("playbook", "status", nullable=True, server_default=None)
    op.alter_column("playbook", "jurisdiction", nullable=True, server_default=None)
    op.alter_column("playbook", "paper_scope", nullable=True, server_default=None)
    op.alter_column("playbook", "party_role", nullable=True, server_default=None)
    op.alter_column("playbook", "layer", nullable=True, server_default=None)

    op.drop_constraint("fk_playbook_parent", "playbook", type_="foreignkey")
    op.drop_constraint("fk_playbook_owner_role", "playbook", type_="foreignkey")
    op.drop_constraint("fk_playbook_agreement_type", "playbook", type_="foreignkey")

    for column in (
        "next_review_at",
        "review_cadence_days",
        "current_version_id",
        "status",
        "description",
        "applies_when",
        "parent_playbook_id",
        "owner_role_id",
        "business_unit",
        "jurisdiction",
        "paper_scope",
        "party_role",
        "layer",
        "key",
    ):
        op.drop_column("playbook", column)

    op.create_check_constraint(
        "ck_playbook_practice_area",
        "playbook",
        "practice_area IN ('hipaa', 'gdpr', 'saas_msa', 'nda', 'dpa')",
    )
