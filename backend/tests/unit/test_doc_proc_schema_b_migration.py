"""Tests for migration 017 (doc_proc task 1.2): new tables and metadata
columns.

Follows the pattern in ``test_playbook_lookups_migration.py``: ``upgrade()``
and ``downgrade()`` are run against a mocked ``alembic.op`` so most checks
need no database connection, plus one end-to-end offline render via
``alembic upgrade head --sql`` / ``downgrade --sql`` as a subprocess.
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

_HEAD_REVISION = "p6q7r8s9t0u1"
_BACKEND = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    return importlib.import_module("migrations.versions.017_doc_proc_schema_b")


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


def test_upgrade_creates_the_four_new_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    # ingest_run must be created before contract_field: contract_field's
    # ingest_run_id column has a foreign key to it. Creating contract_field
    # first failed against a real database with "relation ingest_run does
    # not exist" (an offline --sql render never catches this).
    op = _run_upgrade(monkeypatch)
    created = [call.args[0] for call in op.create_table.call_args_list]
    assert created == ["ingest_run", "contract_field", "contract_party", "contract_signatory"]
    # Migrations never name the project schema in a DDL call (ground rule).
    for call in op.create_table.call_args_list:
        for arg in call.args:
            assert "precedent" not in str(arg)


def test_downgrade_drops_the_four_new_tables_in_reverse(monkeypatch: pytest.MonkeyPatch) -> None:
    # contract_field must be dropped before ingest_run (the reverse of
    # upgrade's order): contract_field's FK to ingest_run is still live
    # until contract_field itself is gone.
    op = _run_downgrade(monkeypatch)
    dropped = [call.args[0] for call in op.drop_table.call_args_list]
    assert dropped == ["contract_signatory", "contract_party", "contract_field", "ingest_run"]


def _column_names(call) -> set[str]:
    import sqlalchemy as sa

    return {arg.name for arg in call.args if isinstance(arg, sa.Column)}


def test_contract_field_columns_and_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy as sa

    op = _run_upgrade(monkeypatch)
    call = next(c for c in op.create_table.call_args_list if c.args[0] == "contract_field")
    columns = _column_names(call)
    assert columns == {
        "id",
        "contract_id",
        "contract_version_id",
        "field_key",
        "value",
        "source",
        "confidence",
        "quote",
        "page",
        "char_start",
        "char_end",
        "clause_id",
        "ingest_run_id",
        "created_at",
    }
    checks = [arg for arg in call.args if isinstance(arg, sa.CheckConstraint)]
    check_names = {c.name for c in checks}
    assert check_names == {"ck_contract_field_source", "ck_contract_field_confidence"}
    uniques = [arg for arg in call.args if isinstance(arg, sa.UniqueConstraint)]
    assert any(u.name == "uq_contract_field_version_key_source" for u in uniques)

    index_call = next(
        c for c in op.create_index.call_args_list if c.args[0] == "ix_contract_field_key_contract"
    )
    assert index_call.args[1] == "contract_field"
    assert index_call.args[2] == ["field_key", "contract_id"]


def test_contract_party_columns_and_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy as sa

    op = _run_upgrade(monkeypatch)
    call = next(c for c in op.create_table.call_args_list if c.args[0] == "contract_party")
    columns = _column_names(call)
    assert columns == {
        "id",
        "contract_id",
        "party_id",
        "role",
        "role_label",
        "entity_type",
        "jurisdiction",
        "address",
        "ordinal",
        "created_at",
    }
    checks = [arg for arg in call.args if isinstance(arg, sa.CheckConstraint)]
    assert any(c.name == "ck_contract_party_role" for c in checks)
    uniques = [arg for arg in call.args if isinstance(arg, sa.UniqueConstraint)]
    assert any(u.name == "uq_contract_party_contract_party" for u in uniques)


def test_contract_signatory_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    call = next(c for c in op.create_table.call_args_list if c.args[0] == "contract_signatory")
    columns = _column_names(call)
    assert columns == {
        "id",
        "contract_version_id",
        "contract_party_id",
        "printed_name",
        "title",
        "is_signed",
        "signed_date",
        "created_at",
    }


def test_ingest_run_columns_and_status_check(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy as sa

    op = _run_upgrade(monkeypatch)
    call = next(c for c in op.create_table.call_args_list if c.args[0] == "ingest_run")
    columns = _column_names(call)
    assert columns == {
        "id",
        "contract_version_id",
        "provider",
        "processor",
        "processor_version",
        "parse_engine_version",
        "extend_file_id",
        "extend_extract_run_id",
        "extend_parse_run_id",
        "status",
        "failure_reason",
        "warnings",
        "credits_used",
        "raw_extract_key",
        "raw_parse_key",
        "started_at",
        "finished_at",
    }
    checks = [arg for arg in call.args if isinstance(arg, sa.CheckConstraint)]
    assert any(c.name == "ck_ingest_run_status" for c in checks)


def test_upgrade_adds_party_is_own_org_column(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    add_column_calls = [c for c in op.add_column.call_args_list if c.args[0] == "party"]
    assert len(add_column_calls) == 1
    assert add_column_calls[0].args[1].name == "is_own_org"


def test_upgrade_adds_clause_embedding_unique_and_model_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_upgrade(monkeypatch)
    unique_calls = [
        c for c in op.create_unique_constraint.call_args_list if c.args[1] == "clause_embedding"
    ]
    assert any(c.args[0] == "uq_clause_embedding_clause_id" for c in unique_calls)
    add_column_calls = [
        c for c in op.add_column.call_args_list if c.args[0] == "clause_embedding"
    ]
    assert any(c.args[1].name == "model" for c in add_column_calls)


def test_upgrade_adds_contract_metadata_projection_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = _run_upgrade(monkeypatch)
    added = {
        c.args[1].name for c in op.add_column.call_args_list if c.args[0] == "contract_metadata"
    }
    assert added == {
        "contract_version_id",
        "expiry_is_derived",
        "initial_term_months",
        "renewal_term_months",
        "renewal_notice_days",
        "dispute_resolution",
        "total_value_amount",
        "currency",
        "liability_cap_amount",
        "liability_cap_basis",
        "payment_terms_days",
        "termination_for_convenience",
        "termination_notice_days",
    }
    # The old untyped columns are not touched by this migration (task 5.2
    # drops them later).
    assert not any(
        c.args[0] == "contract_metadata"
        for c in op.drop_column.call_args_list
    )


def test_offline_sql_upgrade_and_downgrade_render() -> None:
    """End-to-end regression test: run ``alembic upgrade head --sql`` and the
    matching ``downgrade --sql`` as subprocesses (no database connection
    made), exactly as the deploy runbook's dry-run would.
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
    assert "CREATE TABLE contract_field" in sql
    assert "CREATE TABLE contract_party" in sql
    assert "CREATE TABLE contract_signatory" in sql
    assert "CREATE TABLE ingest_run" in sql
    assert "ALTER TABLE party ADD COLUMN is_own_org" in sql
    assert "ALTER TABLE clause_embedding ADD CONSTRAINT uq_clause_embedding_clause_id" in sql

    downgrade_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "q7r8s9t0u1v2:p6q7r8s9t0u1",
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
    assert "DROP TABLE ingest_run" in down_sql
    assert "DROP TABLE contract_signatory" in down_sql
    assert "DROP TABLE contract_party" in down_sql
    assert "DROP TABLE contract_field" in down_sql
