"""Tests for migration 019 (doc_proc task 5.2): drop the old pipeline's
untyped ``contract_metadata`` columns, delete orphaned rows, and tighten
``clause.contract_version_id`` to NOT NULL.

Follows the pattern in ``test_doc_proc_schema_b_migration.py``: ``upgrade()``
and ``downgrade()`` are run against a mocked ``alembic.op`` so most checks
need no database connection, plus one end-to-end offline render via
``alembic upgrade head --sql`` / ``downgrade --sql`` as a subprocess. This
migration is destructive (drops columns, deletes rows) and this test never
applies it to a real database — only ``--sql`` rendering is exercised.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_HEAD_REVISION = "r8s9t0u1v2w3"
_BACKEND = Path(__file__).resolve().parents[2]

_OLD_COLUMNS = (
    "parties",
    "financial_fields",
    "milestone_dates",
    "liability_cap",
    "notice_period_days",
    "payment_terms",
    "extracted",
)


def _module() -> ModuleType:
    return importlib.import_module("migrations.versions.019_doc_proc_drop_legacy_columns")


def _run_upgrade(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
    return op


def _run_downgrade(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    m.downgrade()
    return op


def test_revision_chains_onto_current_head() -> None:
    m = _module()
    assert m.down_revision == _HEAD_REVISION
    assert m.revision != _HEAD_REVISION
    assert m.branch_labels is None
    assert m.depends_on is None


def test_upgrade_and_downgrade_are_callable() -> None:
    m = _module()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_migration_docstring_states_data_is_deleted() -> None:
    """Done-when: the docstring must say, in plain language, that this
    migration deletes data — not buried."""
    m = _module()
    doc = (m.__doc__ or "").lower()
    assert "deletes data" in doc or "delete" in doc.splitlines()[2].lower()
    assert "destructive" in doc
    assert "never" in doc and "real database" in doc


def test_upgrade_deletes_orphaned_rows_before_dropping_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_upgrade(monkeypatch)
    executed_sql = [str(call.args[0]) for call in op.execute.call_args_list]
    assert any("DELETE FROM clause" in s and "contract_version_id IS NULL" in s for s in executed_sql)
    assert any("DELETE FROM clause_embedding" in s for s in executed_sql)
    assert any(
        "DELETE FROM contract_metadata" in s and "contract_version_id IS NULL" in s
        for s in executed_sql
    )
    # Migrations never name the project schema in an op.* call.
    for s in executed_sql:
        assert "precedent" not in s


def test_upgrade_makes_clause_contract_version_id_not_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_upgrade(monkeypatch)
    alter_calls = [
        c for c in op.alter_column.call_args_list if c.args[0] == "clause"
    ]
    assert any(
        c.args[1] == "contract_version_id" and c.kwargs.get("nullable") is False
        for c in alter_calls
    )


def test_upgrade_drops_the_seven_old_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    dropped = [
        c.args[1]
        for c in op.drop_column.call_args_list
        if c.args[0] == "contract_metadata"
    ]
    assert set(dropped) == set(_OLD_COLUMNS)


def test_downgrade_recreates_the_seven_columns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_downgrade(monkeypatch)
    added = {
        c.args[1].name
        for c in op.add_column.call_args_list
        if c.args[0] == "contract_metadata"
    }
    assert added == set(_OLD_COLUMNS)
    # No data is restored: downgrade never issues a raw SQL write.
    assert op.execute.call_count == 0


def test_downgrade_relaxes_clause_contract_version_id_to_nullable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_downgrade(monkeypatch)
    alter_calls = [c for c in op.alter_column.call_args_list if c.args[0] == "clause"]
    assert any(
        c.args[1] == "contract_version_id" and c.kwargs.get("nullable") is True
        for c in alter_calls
    )


def test_offline_sql_upgrade_and_downgrade_render() -> None:
    """End-to-end regression test: run ``alembic upgrade head --sql`` and the
    matching ``downgrade --sql`` as subprocesses (no database connection
    made, nothing ever applied for real).
    """
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+psycopg://user:pass@db.invalid/testdb",
    }
    upgrade_proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert upgrade_proc.returncode == 0, upgrade_proc.stderr
    sql = upgrade_proc.stdout
    assert "DELETE FROM clause WHERE contract_version_id IS NULL" in sql
    assert "DELETE FROM clause_embedding" in sql
    assert "DELETE FROM contract_metadata WHERE contract_version_id IS NULL" in sql
    assert "ALTER TABLE clause ALTER COLUMN contract_version_id SET NOT NULL" in sql
    for column in _OLD_COLUMNS:
        assert f"ALTER TABLE contract_metadata DROP COLUMN {column}" in sql

    downgrade_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "s9t0u1v2w3x4:r8s9t0u1v2w3",
            "--sql",
        ],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert downgrade_proc.returncode == 0, downgrade_proc.stderr
    down_sql = downgrade_proc.stdout
    assert "ALTER TABLE contract_metadata ADD COLUMN parties JSONB" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN financial_fields JSONB" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN milestone_dates JSONB" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN liability_cap JSONB" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN notice_period_days INTEGER" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN payment_terms TEXT" in down_sql
    assert "ALTER TABLE contract_metadata ADD COLUMN extracted JSONB" in down_sql
    assert "ALTER TABLE clause ALTER COLUMN contract_version_id DROP NOT NULL" in down_sql
