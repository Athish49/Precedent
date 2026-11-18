"""Schema partitioning guards (task 0.4).

The database is shared with other projects. Every table and view of this
project lives in the schema named by ``Settings.db_schema``, and nothing at
runtime relies on the session search path. These tests hold that in place:

* every model is schema-qualified through the shared metadata;
* mappers configure and every table compiles, with foreign keys pointing
  inside the project schema;
* no raw SQL in ``app/`` or ``scripts/`` names a project table or view
  without the schema;
* the migration environment creates the schema, keeps Alembic's version table
  there and scopes the search path to the migration transaction.

The schema name is always read from settings; it is never written here.
"""

from __future__ import annotations

import ast
import importlib
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.db.base import DB_SCHEMA, Base, qualified

_BACKEND = Path(__file__).resolve().parents[2]
_SCANNED_DIRS = (_BACKEND / "app", _BACKEND / "scripts")

_EXPECTED_TABLES = {
    "alert",
    "clause",
    "clause_embedding",
    "contract",
    "contract_metadata",
    "contract_version",
    "decision_event",
    "flag",
    "obligation",
    "party",
    "playbook",
    "playbook_rule",
    "qa_cache",
    "redline",
    "review_run",
    "risk_score",
    # Added by migration 010 (task 1.1): lookups and authority tables.
    "agreement_type",
    "clause_family",
    "clause_issue",
    "context_dimension",
    "approver_role",
    "escalation_policy",
    # Added by migration 011 (task 1.2): playbook versions, rules and children.
    "playbook_version",
    "playbook_change_log",
    "rule_position",
    "rule_parameter",
    "red_line",
    "rule_objection",
    "rule_dependency",
    "rule_test_case",
    # Added by migration 012 (task 1.3): contract, review and outcome tables.
    "playbook_exception",
}

# Views are created by hand-written SQL in migrations 004 and 009.
_VIEW_NAMES = (
    "counterparty_pattern",
    *importlib.import_module("migrations.versions.009_analytics_views").VIEW_NAMES,
)


# ── Models ────────────────────────────────────────────────────────────────────


def test_metadata_schema_comes_from_settings() -> None:
    assert Base.metadata.schema == get_settings().db_schema == DB_SCHEMA
    assert DB_SCHEMA != "public"


def test_every_table_is_in_the_project_schema() -> None:
    tables = Base.metadata.tables
    assert tables, "no models registered"
    wrong = {key: t.schema for key, t in tables.items() if t.schema != DB_SCHEMA}
    assert not wrong, f"tables outside the project schema: {wrong}"
    # Table keys are schema-qualified too: metadata.tables["<schema>.contract"].
    assert set(tables) == {f"{DB_SCHEMA}.{t.name}" for t in tables.values()}


def test_the_sixteen_existing_tables_are_registered() -> None:
    names = {t.name for t in Base.metadata.tables.values()}
    assert _EXPECTED_TABLES.issubset(names)


def test_mappers_configure() -> None:
    # Fails if a relationship or string foreign key no longer resolves now
    # that the metadata carries a schema.
    configure_mappers()


def test_foreign_keys_resolve_inside_the_project_schema() -> None:
    checked = 0
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            # ``fk.column`` raises NoReferencedTableError if an unqualified
            # string such as "contract.id" did not resolve.
            # ``fk.target_fullname`` is the string as written ("contract.id");
            # the resolved column is what matters.
            target = fk.column.table
            assert target.schema == DB_SCHEMA, f"{table.name}: {fk.target_fullname}"
            assert target is Base.metadata.tables[f"{DB_SCHEMA}.{target.name}"]
            checked += 1
    assert checked >= 15


@pytest.mark.parametrize("table_name", sorted(_EXPECTED_TABLES))
def test_create_table_compiles_schema_qualified(table_name: str) -> None:
    table = Base.metadata.tables[f"{DB_SCHEMA}.{table_name}"]
    dialect = postgresql.dialect()

    ddl = str(CreateTable(table).compile(dialect=dialect))
    assert f"CREATE TABLE {DB_SCHEMA}.{table_name} (" in ddl
    for target in re.findall(r"REFERENCES (\S+)", ddl):
        assert target.startswith(f"{DB_SCHEMA}."), f"unqualified reference in:\n{ddl}"

    for index in table.indexes:
        assert index.table.schema == DB_SCHEMA
        try:
            index_ddl = str(CreateIndex(index).compile(dialect=dialect))
        except CompileError:
            # ``ix_contract_fts`` is an expression index whose 'english'
            # literal has no offline renderer. Unrelated to the schema; the
            # migration creates that index with hand-written SQL.
            assert index.name == "ix_contract_fts"
            continue
        assert f" ON {DB_SCHEMA}.{table_name} " in index_ddl, index_ddl


def test_every_table_compiles() -> None:
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {DB_SCHEMA}.{table.name} (" in ddl


def test_vector_column_type_still_resolves() -> None:
    table = Base.metadata.tables[f"{DB_SCHEMA}.clause_embedding"]
    column = table.c.embedding
    assert isinstance(column.type, Vector)
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    # The type is left unqualified on purpose: the shared ``vector`` extension
    # lives in ``public``, which is on every connection's default search path.
    assert "embedding VECTOR(384) NOT NULL" in ddl


def test_orm_select_is_schema_qualified() -> None:
    from sqlalchemy import select

    from app.db.models.contract import Contract, ContractMetadata

    stmt = select(Contract).outerjoin(
        ContractMetadata, Contract.id == ContractMetadata.contract_id
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert f"FROM {DB_SCHEMA}.contract " in sql
    assert f"JOIN {DB_SCHEMA}.contract_metadata " in sql


def test_qualified_helper() -> None:
    assert qualified("v_portfolio_risk") == f"{DB_SCHEMA}.v_portfolio_risk"
    with pytest.raises(ValueError):
        qualified("contract; DROP TABLE x")
    with pytest.raises(ValueError):
        qualified("public.contract")


# ── Raw SQL guard ─────────────────────────────────────────────────────────────


def _project_object_names() -> list[str]:
    names = {t.name for t in Base.metadata.tables.values()} | set(_VIEW_NAMES)
    # Longest first so "contract_metadata" is tried before "contract".
    return sorted(names, key=lambda n: (-len(n), n))


def _unqualified_pattern() -> re.Pattern[str]:
    """Match a SQL keyword followed directly by a bare project object name.

    A schema-qualified reference (``FROM <schema>.contract`` or, in an
    f-string, ``FROM {schema}.contract``) does not match, because the name is
    then not the first token after the keyword.
    """
    names = "|".join(re.escape(n) for n in _project_object_names())
    keywords = r"FROM|JOIN|INTO|UPDATE|TABLE|VIEW|ON"
    return re.compile(rf"\b({keywords})\s+(?:ONLY\s+|IF\s+(?:NOT\s+)?EXISTS\s+)?({names})\b")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _string_literals(source: str) -> Iterator[tuple[int, str]]:
    """Yield (line, text) for every string literal that is not a docstring.

    An f-string is yielded once, with each ``{expression}`` replaced by
    ``{}``, so ``f"FROM {view}"`` reads as ``FROM {}`` (no bare name) and
    ``f"FROM {schema}.contract"`` as ``FROM {}.contract`` (qualified).
    """
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    inside_fstring: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                inside_fstring.add(id(value))
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    parts.append("{}")
            yield node.lineno, "".join(parts)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and id(node) not in inside_fstring
        ):
            yield node.lineno, node.value


def _find_unqualified_sql(source: str) -> list[tuple[int, str]]:
    pattern = _unqualified_pattern()
    hits = []
    for line, literal in _string_literals(source):
        for match in pattern.finditer(literal):
            hits.append((line, match.group(0)))
    return hits


def test_no_unqualified_project_object_in_raw_sql() -> None:
    violations = []
    for root in _SCANNED_DIRS:
        for path in sorted(root.rglob("*.py")):
            for line, snippet in _find_unqualified_sql(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(_BACKEND)}:{line}: {snippet!r}")
    assert not violations, (
        "Raw SQL names a project table or view without the schema. Use "
        "app.db.base.qualified(...):\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        'q = text("SELECT * FROM v_portfolio_risk")',
        'q = text("SELECT 1 FROM contract c JOIN party p ON p.id = c.counterparty_id")',
        'q = "SELECT 1 FROM risk_score rs LEFT JOIN flag f ON true"',
        'q = f"DELETE FROM qa_cache WHERE contract_id = {cid}"',
        'q = "INSERT INTO playbook_rule (id) VALUES (1)"',
        'q = "UPDATE contract SET status = 1"',
        'q = "DROP VIEW IF EXISTS counterparty_pattern"',
        'q = """\n    SELECT *\n    FROM\n        contract_metadata\n"""',
    ],
)
def test_guard_catches_unqualified_sql(source: str) -> None:
    assert _find_unqualified_sql(source), source


@pytest.mark.parametrize(
    "source",
    [
        'q = text(f"SELECT * FROM {qualified(\'v_portfolio_risk\')}")',
        'q = text(f"SELECT * FROM {_VIEW} ORDER BY created_at")',
        'q = f"SELECT 1 FROM {schema}.contract c JOIN {schema}.party p ON true"',
        "from app.db.models.contract import Contract",
        'def f():\n    """Reads rows FROM contract and joins party."""\n',
        'q = "WITH contract_risk AS (SELECT 1) SELECT * FROM contract_risk"',
    ],
)
def test_guard_allows_qualified_sql(source: str) -> None:
    assert not _find_unqualified_sql(source), source


def test_raw_sql_modules_name_the_schema() -> None:
    from app.db.repositories import nms_repo
    from app.services.analytics import service as analytics

    assert nms_repo._PATTERN_VIEW == f"{DB_SCHEMA}.counterparty_pattern"
    assert analytics._V_INTELLIGENCE == f"{DB_SCHEMA}.v_contract_intelligence"
    assert analytics._V_PORTFOLIO_RISK == f"{DB_SCHEMA}.v_portfolio_risk"
    assert analytics._V_CONTRACT_VALUE == f"{DB_SCHEMA}.v_contract_value"
    assert analytics._V_TABULAR_REVIEW == f"{DB_SCHEMA}.v_tabular_review"
    assert analytics._V_RENEWAL_DASHBOARD == f"{DB_SCHEMA}.v_renewal_dashboard"


async def test_runtime_view_queries_are_schema_qualified() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.db.repositories import nms_repo
    from app.services.analytics import service as analytics

    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    result.all.return_value = []
    result.__iter__.return_value = iter(())
    session.execute.return_value = result

    import uuid

    await nms_repo.get_counterparty_pattern(session, uuid.uuid4(), "indemnification")
    await nms_repo.get_patterns_for_counterparty(session, uuid.uuid4())
    await analytics.get_intelligence(session)
    await analytics.get_portfolio_risk(session)
    await analytics.get_contract_value(session)
    await analytics.get_tabular(session)
    await analytics.get_renewals(session)

    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert len(statements) == 7
    for sql, view in zip(statements, [_VIEW_NAMES[0]] * 2 + list(_VIEW_NAMES[1:]), strict=True):
        assert f"FROM {DB_SCHEMA}.{view}" in sql, sql
        assert not _unqualified_pattern().search(sql), sql


# ── Migrations ────────────────────────────────────────────────────────────────

# A schema that is deliberately not the default, to prove nothing in the
# migration path hard-codes the namespace.
_OTHER_SCHEMA = "zz_partition_check"


def _alembic_offline(*args: str) -> str:
    """Render migration SQL offline. No database connection is made."""
    env = {
        **os.environ,
        "DB_SCHEMA": _OTHER_SCHEMA,
        "DATABASE_URL": "postgresql+psycopg://user:pass@db.invalid/testdb",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args, "--sql"],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    assert _OTHER_SCHEMA != DB_SCHEMA
    return _alembic_offline("upgrade", "head")


@pytest.fixture(scope="module")
def downgrade_sql() -> str:
    return _alembic_offline("downgrade", "i9j0k1l2m3n4:base")


def test_offline_upgrade_creates_schema_first(upgrade_sql: str) -> None:
    begin = upgrade_sql.index("BEGIN;")
    create_schema = upgrade_sql.index(f"CREATE SCHEMA IF NOT EXISTS {_OTHER_SCHEMA};")
    search_path = upgrade_sql.index(f"SET LOCAL search_path TO {_OTHER_SCHEMA}, public;")
    version_table = upgrade_sql.index(f"CREATE TABLE {_OTHER_SCHEMA}.alembic_version (")
    first_migration = upgrade_sql.index("-- Running upgrade")
    assert begin < create_schema < search_path < version_table < first_migration
    # One transaction for the whole run, so SET LOCAL covers every migration.
    assert upgrade_sql.count("BEGIN;") == 1
    assert upgrade_sql.count("COMMIT;") == 1
    assert upgrade_sql.count("SET LOCAL search_path") == 1


def test_offline_upgrade_keeps_version_table_in_project_schema(upgrade_sql: str) -> None:
    assert f"INSERT INTO {_OTHER_SCHEMA}.alembic_version" in upgrade_sql
    assert f"UPDATE {_OTHER_SCHEMA}.alembic_version SET version_num='i9j0k1l2m3n4'" in upgrade_sql
    # Every mention of the version table is qualified.
    assert not re.search(r"(?<!\.)\balembic_version\b(?!_pkc)", upgrade_sql)


def test_offline_sql_never_names_public_or_the_default_schema(
    upgrade_sql: str, downgrade_sql: str
) -> None:
    for sql in (upgrade_sql, downgrade_sql):
        # ``public`` appears only as the tail of the search path.
        assert re.findall(r".*\bpublic\b.*", sql) == [
            f"SET LOCAL search_path TO {_OTHER_SCHEMA}, public;"
        ]
        # The default namespace is not hard-coded anywhere in the migrations.
        assert not re.search(rf"\b{re.escape(DB_SCHEMA)}\.", sql)
        assert "SET search_path" not in sql  # never session-level


def test_offline_upgrade_views_are_schema_qualified(upgrade_sql: str) -> None:
    assert f"CREATE VIEW {_OTHER_SCHEMA}.counterparty_pattern AS" in upgrade_sql
    assert f"FROM {_OTHER_SCHEMA}.decision_event" in upgrade_sql
    for view in _VIEW_NAMES[1:]:
        assert f"CREATE OR REPLACE VIEW {_OTHER_SCHEMA}.{view} AS" in upgrade_sql
    # Inside view bodies, every table reference carries the schema.
    for body in re.findall(r"CREATE (?:OR REPLACE )?VIEW .*?;\n", upgrade_sql, flags=re.S):
        assert not _unqualified_pattern().search(body), body


def test_offline_upgrade_creates_all_tables_and_keeps_extension(upgrade_sql: str) -> None:
    created = set(re.findall(r"^CREATE TABLE (\w+) \($", upgrade_sql, flags=re.M))
    # Migration files do not name the schema; the search path places them.
    assert created == _EXPECTED_TABLES
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in upgrade_sql


def test_offline_downgrade_drops_views_by_qualified_name(downgrade_sql: str) -> None:
    for view in _VIEW_NAMES:
        assert f"DROP VIEW IF EXISTS {_OTHER_SCHEMA}.{view};" in downgrade_sql
    assert not re.search(r"DROP VIEW (?:IF EXISTS )?\w+;", downgrade_sql)
    assert f"DELETE FROM {_OTHER_SCHEMA}.alembic_version" in downgrade_sql
