"""Tests for the hand-written view SQL in migrations 004, 009 and 018
(T-084; doc_proc task 3.6).

The views live in the project schema. The schema name comes from settings and
is written into every statement; nothing relies on the search path.

Migration 009 created the five analytics views against the original, untyped
``contract_metadata`` columns. Migration 018 (doc_proc task 3.6)
``CREATE OR REPLACE``s the same views to read the typed projection columns
added by migration 017 instead. ``db/views.sql`` is kept in step with 018,
the current state of the views, not 009.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings

_BACKEND = Path(__file__).resolve().parents[2]
_VIEWS_SQL = _BACKEND / "db" / "views.sql"

_TABLES = (
    "alert",
    "contract",
    "contract_metadata",
    "decision_event",
    "flag",
    "obligation",
    "party",
    "redline",
    "risk_score",
)
# A bare table name directly after FROM / JOIN, i.e. not schema-qualified.
_UNQUALIFIED_TABLE = re.compile(rf"\b(?:FROM|JOIN)\s+(?:{'|'.join(_TABLES)})\b")


def _m009() -> ModuleType:
    return importlib.import_module("migrations.versions.009_analytics_views")


def _m004() -> ModuleType:
    return importlib.import_module("migrations.versions.004_nms_tables")


def _m018() -> ModuleType:
    return importlib.import_module("migrations.versions.018_doc_proc_analytics_views")


def _normalise(sql: str) -> str:
    return " ".join(sql.split()).rstrip(";").strip()


def _executed(module: ModuleType, direction: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Run upgrade/downgrade against a mocked ``op`` and return the raw SQL."""
    op = MagicMock()
    monkeypatch.setattr(module, "op", op)
    getattr(module, direction)()
    return [call.args[0] for call in op.execute.call_args_list]


def test_revision() -> None:
    m = _m009()
    assert m.revision == "i9j0k1l2m3n4"
    assert m.down_revision == "h8i9j0k1l2m3"


def test_revision_004_unchanged() -> None:
    m = _m004()
    assert m.revision == "d4e5f6a7b8c9"
    assert m.down_revision == "c3d4e5f6a7b8"


def test_upgrade_and_downgrade_are_callable() -> None:
    m = _m009()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_branch_labels_and_depends_on_are_none() -> None:
    m = _m009()
    assert m.branch_labels is None
    assert m.depends_on is None


def test_009_upgrade_creates_views_in_the_project_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _m009()
    schema = get_settings().db_schema
    statements = _executed(m, "upgrade", monkeypatch)

    assert len(statements) == len(m.VIEW_NAMES) == 5
    for sql, view in zip(statements, m.VIEW_NAMES, strict=True):
        assert _normalise(sql).startswith(f"CREATE OR REPLACE VIEW {schema}.{view} AS")
        assert not _UNQUALIFIED_TABLE.search(sql), sql
        assert f"{schema}." in sql
        assert "public" not in sql


def test_009_downgrade_drops_views_in_the_project_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _m009()
    schema = get_settings().db_schema
    statements = _executed(m, "downgrade", monkeypatch)
    assert statements == [
        f"DROP VIEW IF EXISTS {schema}.{view}" for view in reversed(m.VIEW_NAMES)
    ]


def test_009_follows_the_schema_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SCHEMA", "other_ns")
    get_settings.cache_clear()
    m = _m009()
    statements = _executed(m, "upgrade", monkeypatch) + _executed(m, "downgrade", monkeypatch)
    assert len(statements) == 10
    for sql in statements:
        assert "other_ns.v_" in sql
        assert not _UNQUALIFIED_TABLE.search(sql), sql


def test_004_view_sql_is_schema_qualified() -> None:
    m = _m004()
    # Module-level SQL: built from the settings in force when the migration
    # module was first imported.
    schema = m._SCHEMA
    assert schema != "public"
    assert _normalise(m._VIEW_SQL).startswith(f"CREATE VIEW {schema}.counterparty_pattern AS")
    assert f"FROM {schema}.decision_event" in m._VIEW_SQL
    assert not _UNQUALIFIED_TABLE.search(m._VIEW_SQL)
    assert m._DROP_VIEW_SQL == f"DROP VIEW IF EXISTS {schema}.counterparty_pattern"


def test_018_revision() -> None:
    m = _m018()
    assert m.revision == "r8s9t0u1v2w3"
    assert m.down_revision == "q7r8s9t0u1v2"


def test_018_upgrade_and_downgrade_are_callable() -> None:
    m = _m018()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_018_branch_labels_and_depends_on_are_none() -> None:
    m = _m018()
    assert m.branch_labels is None
    assert m.depends_on is None


def test_018_upgrade_creates_views_in_the_project_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """018 drops then creates each view (not CREATE OR REPLACE): Postgres
    rejects CREATE OR REPLACE VIEW whenever it renames/retypes a column,
    which four of these five views do. Each view therefore produces two
    statements, in order: DROP VIEW IF EXISTS, then CREATE VIEW."""
    m = _m018()
    schema = get_settings().db_schema
    statements = _executed(m, "upgrade", monkeypatch)

    assert len(statements) == len(m.VIEW_NAMES) * 2 == 10
    for i, view in enumerate(m.VIEW_NAMES):
        drop_sql, create_sql = statements[2 * i], statements[2 * i + 1]
        assert _normalise(drop_sql) == f"DROP VIEW IF EXISTS {schema}.{view}"
        assert _normalise(create_sql).startswith(f"CREATE VIEW {schema}.{view} AS")
        assert not _UNQUALIFIED_TABLE.search(create_sql), create_sql
        assert f"{schema}." in create_sql
        assert "public" not in create_sql


def test_018_upgrade_reads_typed_metadata_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of 018: no more financial_fields / liability_cap (JSON) /
    notice_period_days / payment_terms — only the typed projection columns.
    """
    m = _m018()
    statements = _executed(m, "upgrade", monkeypatch)
    combined = "\n".join(statements)
    assert "financial_fields" not in combined
    assert "milestone_dates" not in combined
    assert "cm.liability_cap," not in combined
    assert "cm.notice_period_days" not in combined
    assert "cm.payment_terms," not in combined
    assert "cm.renewal_notice_days" in combined
    assert "cm.liability_cap_amount" in combined
    assert "cm.payment_terms_days" in combined
    assert "cm.total_value_amount" in combined


def test_018_downgrade_restores_the_old_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Downgrade puts the views back onto the old untyped columns, which
    still exist (task 5.2 drops them)."""
    m = _m018()
    statements = _executed(m, "downgrade", monkeypatch)
    combined = "\n".join(statements)
    assert "cm.financial_fields" in combined
    assert "cm.notice_period_days" in combined
    assert "cm.liability_cap" in combined
    assert "cm.payment_terms" in combined


def test_018_follows_the_schema_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SCHEMA", "other_ns")
    get_settings.cache_clear()
    m = _m018()
    statements = _executed(m, "upgrade", monkeypatch) + _executed(m, "downgrade", monkeypatch)
    assert len(statements) == 20
    for sql in statements:
        assert "other_ns.v_" in sql
        assert not _UNQUALIFIED_TABLE.search(sql), sql


def test_views_sql_reference_file_matches_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    """db/views.sql is the readable copy of the views' current definition,
    migration 018 (which supersedes 009's original, untyped SQL)."""
    m = _m018()
    schema = get_settings().db_schema

    def squash(sql: str) -> str:
        # Layout differs between the two copies; compare ignoring whitespace.
        return "".join(sql.split()).rstrip(";")

    from_migration = [squash(sql) for sql in _executed(m, "upgrade", monkeypatch)]

    text = _VIEWS_SQL.read_text(encoding="utf-8")
    # The file never names the schema; it uses the psql variable :"schema".
    assert f"{schema}." not in text
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    from_file = [
        squash(stmt.replace(':"schema"', schema)) for stmt in code.split(";") if stmt.strip()
    ]
    assert from_file == from_migration
