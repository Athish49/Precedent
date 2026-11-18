"""Tests for migration 011 (task 1.2): playbook, versions, rules and children.

The migration's ``upgrade()``/``downgrade()`` are run against a mocked
``alembic.op`` (and ``alembic.context`` forced into offline mode, so the
data-dependent backfill helpers are not invoked with a real connection) so
these tests never touch a database. They check: the revision chains onto
migration 010's head; the new tables and constraints are created and dropped
in the right order; the legacy FK to ``playbook`` gains cascade delete; and —
the main point of task 1.2 — that the pure backfill helper functions produce
the right data when run over a static copy of the 29 legacy rules
(``tests/fixtures/legacy_playbook_rows.py``), with no database involved at
all.
"""

from __future__ import annotations

import importlib
import uuid
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from tests.fixtures.legacy_playbook_rows import LEGACY_PLAYBOOK_RULES

_HEAD_REVISION = "j0k1l2m3n4o5"


def _module() -> ModuleType:
    return importlib.import_module("migrations.versions.011_playbook_structure")


def _run_upgrade(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Run upgrade() with a mocked `op` and `context` forced offline.

    Offline means no connection to read existing rows from, so the
    data-dependent backfill steps (playbook_version / rule-children backfill)
    are skipped — exactly what a real `alembic upgrade head --sql` run does.
    This isolates the DDL assertions below from needing a fake connection.
    """
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    monkeypatch.setattr(m.context, "is_offline_mode", lambda: True)
    m.upgrade()
    return op


def _run_downgrade(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    m.downgrade()
    return op


# ---------------------------------------------------------------------------
# Revision chain
# ---------------------------------------------------------------------------


def test_revision_chains_onto_migration_010_head() -> None:
    m = _module()
    assert m.down_revision == _HEAD_REVISION
    assert m.revision != _HEAD_REVISION
    assert m.branch_labels is None
    assert m.depends_on is None


def test_upgrade_and_downgrade_are_callable() -> None:
    m = _module()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


# ---------------------------------------------------------------------------
# DDL: zero legacy rows (offline dry-check proxy)
# ---------------------------------------------------------------------------


def test_upgrade_handles_zero_legacy_rows_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline mode has no data to read, which is exactly the live database's
    actual state today (0 rows in playbook and playbook_rule). Either way,
    upgrade() must not raise."""
    _run_upgrade(monkeypatch)  # raises on failure


def test_upgrade_creates_the_new_tables_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    created = [call.args[0] for call in op.create_table.call_args_list]
    assert created == [
        "playbook_version",
        "playbook_change_log",
        "rule_position",
        "rule_parameter",
        "red_line",
        "rule_objection",
        "rule_dependency",
        "rule_test_case",
    ]
    # Migrations never name the project schema in a DDL call (ground rule).
    for call in op.create_table.call_args_list:
        for arg in call.args:
            assert "precedent" not in str(arg)


def test_downgrade_drops_the_new_tables_in_reverse(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_downgrade(monkeypatch)
    dropped = [call.args[0] for call in op.drop_table.call_args_list]
    assert dropped == [
        "rule_test_case",
        "rule_dependency",
        "rule_objection",
        "red_line",
        "rule_parameter",
        "rule_position",
        "playbook_change_log",
        "playbook_version",
    ]


def test_upgrade_drops_old_check_and_adds_cascade_fk(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)

    dropped_constraints = [call.args[0] for call in op.drop_constraint.call_args_list]
    assert "ck_playbook_practice_area" in dropped_constraints
    assert "fk_playbook_rule_playbook" in dropped_constraints

    cascade_calls = [
        call
        for call in op.create_foreign_key.call_args_list
        if call.args[0] == "fk_playbook_rule_playbook"
    ]
    assert len(cascade_calls) == 1
    assert cascade_calls[0].kwargs.get("ondelete") == "CASCADE"


def test_upgrade_adds_the_two_unique_constraints_after_backfill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_upgrade(monkeypatch)
    unique_calls = {
        call.args[0]: call.args for call in op.create_unique_constraint.call_args_list
    }
    assert "uq_playbook_key" in unique_calls
    assert unique_calls["uq_playbook_key"][1:] == ("playbook", ["key"])
    assert "uq_playbook_rule_version_rule_key" in unique_calls
    assert unique_calls["uq_playbook_rule_version_rule_key"][1:] == (
        "playbook_rule",
        ["playbook_version_id", "rule_key"],
    )

    # `playbook_version(playbook_id, version)` is declared on the table
    # itself at create time, not as a separate call.
    playbook_version_call = next(
        call for call in op.create_table.call_args_list if call.args[0] == "playbook_version"
    )
    table_level_uniques = [
        arg
        for arg in playbook_version_call.args
        if hasattr(arg, "name") and arg.name == "uq_playbook_version_playbook_version"
    ]
    assert len(table_level_uniques) == 1


def test_downgrade_restores_check_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_downgrade(monkeypatch)
    op.create_check_constraint.assert_called_once()
    args = op.create_check_constraint.call_args.args
    assert args[0] == "ck_playbook_practice_area"
    assert args[1] == "playbook"


# ---------------------------------------------------------------------------
# Models import and register
# ---------------------------------------------------------------------------


def test_models_import_cleanly_and_register_on_metadata() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base
    from app.db.models.playbook import (
        Playbook,
        PlaybookChangeLog,
        PlaybookRule,
        PlaybookVersion,
        RedLine,
        RuleDependency,
        RuleObjection,
        RuleParameter,
        RulePosition,
        RuleTestCase,
    )

    schema = Base.metadata.schema
    expected_tables = {
        "playbook",
        "playbook_rule",
        "playbook_version",
        "playbook_change_log",
        "rule_position",
        "rule_parameter",
        "red_line",
        "rule_objection",
        "rule_dependency",
        "rule_test_case",
    }
    assert {f"{schema}.{name}" for name in expected_tables}.issubset(Base.metadata.tables.keys())

    for cls in (
        Playbook,
        PlaybookRule,
        PlaybookVersion,
        PlaybookChangeLog,
        RulePosition,
        RuleParameter,
        RedLine,
        RuleObjection,
        RuleDependency,
        RuleTestCase,
    ):
        assert cls.__table__.schema == schema

    # The five legacy flat columns were dropped by migration 015 (task 5.5);
    # their content now lives only in ``rule_position`` / ``red_line`` rows.
    for legacy_column in (
        "preferred_language",
        "acceptable_variations",
        "prohibited_terms",
        "fallback_language",
        "escalation_threshold",
    ):
        assert legacy_column not in PlaybookRule.__table__.columns

    # `updated_at` gets a model-level `onupdate` (task 1.2 item 8).
    assert Playbook.__table__.columns["updated_at"].onupdate is not None


# ---------------------------------------------------------------------------
# Backfill helpers — the main point of task 1.2. No database anywhere here.
# ---------------------------------------------------------------------------


def test_fixture_has_29_legacy_rows() -> None:
    assert len(LEGACY_PLAYBOOK_RULES) == 29


def test_backfill_helpers_produce_29_preferred_46_variants_65_red_lines() -> None:
    m = _module()

    preferred_count = 0
    variant_count = 0
    fallback_count = 0
    red_line_count = 0

    for rule in LEGACY_PLAYBOOK_RULES:
        rule_id = uuid.uuid4()
        positions = m.build_position_rows(rule_id, rule)
        red_lines = m.build_red_line_rows(rule_id, rule)

        preferred_count += sum(1 for p in positions if p["kind"] == "preferred")
        variant_count += sum(1 for p in positions if p["kind"] == "acceptable_variant")
        fallback_count += sum(1 for p in positions if p["kind"] == "fallback")
        red_line_count += len(red_lines)

    assert preferred_count == 29
    assert variant_count == 46
    assert red_line_count == 65
    # None of the 29 legacy rows carried fallback_language.
    assert fallback_count == 0


def test_build_position_rows_exactly_one_preferred_per_rule() -> None:
    m = _module()
    for rule in LEGACY_PLAYBOOK_RULES:
        positions = m.build_position_rows(uuid.uuid4(), rule)
        preferred = [p for p in positions if p["kind"] == "preferred"]
        assert len(preferred) == 1
        assert preferred[0]["rung"] == 0
        assert preferred[0]["zone"] == "green"
        assert preferred[0]["language"] == rule["preferred_language"]


def test_build_position_rows_adds_fallback_only_when_language_present() -> None:
    m = _module()
    rule_id = uuid.uuid4()

    without_fallback = {
        "preferred_language": "Preferred text.",
        "acceptable_variations": [],
        "fallback_language": None,
        "prohibited_terms": [],
    }
    assert not any(p["kind"] == "fallback" for p in m.build_position_rows(rule_id, without_fallback))

    with_fallback = dict(without_fallback, fallback_language="Fallback text.")
    fallback_rows = [
        p for p in m.build_position_rows(rule_id, with_fallback) if p["kind"] == "fallback"
    ]
    assert len(fallback_rows) == 1
    assert fallback_rows[0]["rung"] == 1
    assert fallback_rows[0]["zone"] == "yellow"
    assert fallback_rows[0]["approver_role_id"] is None
    assert fallback_rows[0]["language"] == "Fallback text."


def test_build_red_line_rows_are_phrase_with_negation_guard_and_block() -> None:
    m = _module()
    rule = {
        "preferred_language": "x",
        "acceptable_variations": [],
        "fallback_language": None,
        "prohibited_terms": ["unlimited liability", "no cap"],
    }
    rows = m.build_red_line_rows(uuid.uuid4(), rule)
    assert len(rows) == 2
    for row, term in zip(rows, rule["prohibited_terms"], strict=True):
        assert row["scope"] == "rule"
        assert row["condition_type"] == "phrase"
        assert row["condition"] == {"any": [term], "negation_guard": True}
        assert row["action"] == "block"
