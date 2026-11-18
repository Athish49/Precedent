"""Tests for migration 010 (task 1.1): lookups and authority tables.

The migration's ``upgrade()`` is run against a mocked ``alembic.op`` so most
of these tests do not touch a real database. They check: the literal
reference data (7 agreement types, 29 clause families) is inserted with no
duplicate synonym across families; the new models import cleanly and are
registered on ``Base.metadata``; and the revision chains onto the current
head.

``clause_family.synonyms`` is JSONB. A previous version of this migration
inserted it via ``op.bulk_insert`` with a ``sa.Text()``-typed shadow column,
which rendered fine offline (``alembic upgrade head --sql``, where bind
values become untyped SQL literals) but failed against a real connection
with ``psycopg.errors.DatatypeMismatch``: online, SQLAlchemy sends an
explicit varchar-typed bind parameter, and Postgres will not implicitly
cast that to jsonb. The mocked-``op`` tests below never exercised this —
``op`` is a ``MagicMock``, so no SQL is ever compiled or typed — which is
why the bug shipped past them. ``test_clause_family_insert_casts_synonyms_
to_jsonb`` and ``test_offline_sql_renders_clause_family_insert_with_cast``
close that gap: the first inspects the actual SQL text for the explicit
``CAST``, the second renders the real migration chain offline end-to-end
via a subprocess, exactly as ``alembic upgrade head --sql`` would.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_HEAD_REVISION = "i9j0k1l2m3n4"
_BACKEND = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    return importlib.import_module("migrations.versions.010_playbook_lookups")


def _run_upgrade(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
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


def test_upgrade_creates_the_six_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    created = [call.args[0] for call in op.create_table.call_args_list]
    assert created == [
        "agreement_type",
        "clause_family",
        "clause_issue",
        "context_dimension",
        "approver_role",
        "escalation_policy",
    ]
    # Migrations never name the project schema in a DDL call (ground rule).
    for call in op.create_table.call_args_list:
        for arg in call.args:
            assert "precedent" not in str(arg)


def test_downgrade_drops_the_six_tables_in_reverse(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _module()
    op = MagicMock()
    monkeypatch.setattr(m, "op", op)
    m.downgrade()
    dropped = [call.args[0] for call in op.drop_table.call_args_list]
    assert dropped == [
        "escalation_policy",
        "approver_role",
        "context_dimension",
        "clause_issue",
        "clause_family",
        "agreement_type",
    ]


def _bulk_insert_rows(op: MagicMock, table_name: str) -> list[dict]:
    for call in op.bulk_insert.call_args_list:
        table = call.args[0]
        if table.name == table_name:
            return call.args[1]
    raise AssertionError(f"no bulk_insert call for {table_name!r}")


def _clause_family_execute_rows(op: MagicMock) -> list[dict]:
    """Recover the per-row data from the ``op.execute(text(...))`` calls.

    ``clause_family`` rows are inserted one statement per row via a bound
    ``sqlalchemy.text()`` clause (not ``op.bulk_insert``), so this reads the
    bound parameter values back off each compiled ``TextClause`` rather
    than a plain list of dicts.
    """
    rows: list[dict] = []
    for call in op.execute.call_args_list:
        stmt = call.args[0]
        text = getattr(stmt, "text", "")
        if "INSERT INTO clause_family" not in text:
            continue
        bound = getattr(stmt, "_bindparams", {})
        rows.append({name: param.value for name, param in bound.items()})
    if not rows:
        raise AssertionError("no op.execute call inserted into clause_family")
    return rows


def test_seven_agreement_types_inserted(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    rows = _bulk_insert_rows(op, "agreement_type")
    assert len(rows) == 7
    keys = {row["key"] for row in rows}
    assert keys == {"baseline", "nda", "saas_msa", "dpa", "vendor_msa", "hipaa", "gdpr"}
    for row in rows:
        assert row["name"]
        assert row["kind"] in {"agreement", "regime", "baseline"}


def test_twenty_nine_clause_families_inserted(monkeypatch: pytest.MonkeyPatch) -> None:
    op = _run_upgrade(monkeypatch)
    rows = _clause_family_execute_rows(op)
    assert len(rows) == 29

    keys = [row["key"] for row in rows]
    assert len(set(keys)) == 29, "duplicate clause_family key"

    canonical_20 = {
        "indemnification",
        "limitation_of_liability",
        "termination",
        "confidentiality",
        "intellectual_property",
        "governing_law",
        "dispute_resolution",
        "payment",
        "warranties",
        "force_majeure",
        "assignment",
        "entire_agreement",
        "amendment",
        "notices",
        "definitions",
        "term",
        "compliance",
        "data_protection",
        "audit",
        "insurance",
    }
    new_8 = {
        "service_levels",
        "security",
        "subprocessors",
        "breach_notification",
        "data_transfers",
        "publicity",
        "non_solicitation",
        "suspension",
    }
    assert set(keys) == canonical_20 | new_8 | {"other"}

    seen_synonyms: dict[str, str] = {}
    for row in rows:
        assert row["name"]
        assert row["category"] in {
            "commercial",
            "risk_allocation",
            "data_and_security",
            "term_and_exit",
            "boilerplate",
        }
        assert row["description"]
        assert len(row["description"].split(".")) >= 2, "description should be two sentences"

        synonyms = json.loads(row["synonyms"])
        assert isinstance(synonyms, list)
        assert len(synonyms) >= 4, f"{row['key']} has fewer than 4 synonyms"

        for synonym in synonyms:
            owner = seen_synonyms.get(synonym)
            assert owner is None, f"synonym {synonym!r} used by both {owner!r} and {row['key']!r}"
            seen_synonyms[synonym] = row["key"]


def test_clause_issue_context_dimension_approver_role_escalation_policy_get_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only agreement_type and clause_family are migration-inserted reference
    data; the other four tables are created here but populated later by the
    seed loader (task 2.1), per playbook_implementation.md section 3.0 rule 5.
    """
    op = _run_upgrade(monkeypatch)
    bulk_inserted_tables = {call.args[0].name for call in op.bulk_insert.call_args_list}
    assert bulk_inserted_tables == {"agreement_type"}

    # clause_family is inserted via op.execute, not op.bulk_insert (see
    # test_clause_family_insert_casts_synonyms_to_jsonb below); confirm no
    # other table gets any op.execute-based insert either.
    executed_tables = set()
    for call in op.execute.call_args_list:
        text = getattr(call.args[0], "text", str(call.args[0]))
        if "INSERT INTO" in text:
            executed_tables.add(text.split("INSERT INTO", 1)[1].split()[0])
    assert executed_tables == {"clause_family"}


def test_clause_family_insert_casts_synonyms_to_jsonb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the online ``DatatypeMismatch`` bug.

    ``clause_family.synonyms`` is JSONB, but the insert binds a Python
    string (``json.dumps(...)``). Without an explicit ``CAST(... AS
    jsonb)`` in the SQL text, a real connection sends that bind as an
    explicit varchar-typed parameter and Postgres refuses to implicitly
    cast it to jsonb — a failure that only reproduces online, since
    offline/literal rendering coerces untyped literals freely regardless.
    This test does not need a database: it inspects the actual SQL text of
    every clause_family insert statement the migration issues.
    """
    op = _run_upgrade(monkeypatch)
    rows = _clause_family_execute_rows(op)
    assert len(rows) == 29

    for call in op.execute.call_args_list:
        stmt = call.args[0]
        text = getattr(stmt, "text", "")
        if "INSERT INTO clause_family" not in text:
            continue
        assert "CAST(:synonyms AS jsonb)" in text, (
            "clause_family insert must explicitly cast the synonyms bind to "
            f"jsonb or it will fail online with DatatypeMismatch: {text!r}"
        )
        # The value bound for synonyms must itself be a JSON string (what
        # the CAST expects), not a raw Python list.
        bound = stmt._bindparams["synonyms"].value
        assert isinstance(bound, str)
        assert json.loads(bound)  # round-trips as valid JSON


def test_offline_sql_renders_clause_family_insert_with_cast() -> None:
    """End-to-end regression test: actually run ``alembic upgrade head
    --sql`` as a subprocess (no database connection made) and confirm the
    rendered SQL contains 29 ``CAST(... AS jsonb)``-wrapped clause_family
    inserts. This is the exact command the deploy runbook uses to dry-run
    migrations, and it must keep succeeding after this fix.
    """
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+psycopg://user:pass@db.invalid/testdb",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    sql = proc.stdout
    assert sql.count("INSERT INTO clause_family") == 29
    assert sql.count("CAST(") >= 29
    # Every clause_family insert carries its own cast, not just some of them.
    for line in sql.splitlines():
        if "INSERT INTO clause_family" in line:
            assert "CAST(" in line and "AS jsonb)" in line, line


def test_models_import_cleanly_and_register_on_metadata() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base
    from app.db.models.authority import ApproverRole, EscalationPolicy
    from app.db.models.taxonomy import (
        AgreementType,
        ClauseFamily,
        ClauseIssue,
        ContextDimension,
    )

    schema = Base.metadata.schema
    expected_tables = {
        "agreement_type",
        "clause_family",
        "clause_issue",
        "context_dimension",
        "approver_role",
        "escalation_policy",
    }
    assert {f"{schema}.{name}" for name in expected_tables}.issubset(Base.metadata.tables.keys())

    # Every new model class is importable and mapped.
    model_classes = (
        AgreementType,
        ClauseFamily,
        ClauseIssue,
        ContextDimension,
        ApproverRole,
        EscalationPolicy,
    )
    for cls in model_classes:
        assert cls.__table__.schema == schema
