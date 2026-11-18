"""Namespace guard and fixed object list (task 0.6).

Mocked sessions only: nothing here opens a connection. The schema name is
read from settings, never written here.
"""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.core.namespace as ns
from app.core.config import get_settings
from app.db.base import DB_SCHEMA, Base


def _session(*, schema_found: bool) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = (1,) if schema_found else None
    session.execute.return_value = result
    return session


def _use_schema(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    monkeypatch.setattr(ns, "get_settings", lambda: SimpleNamespace(db_schema=value))


# ── assert_namespace: one test per failure case ──────────────────────────────


async def test_guard_passes_when_schema_is_set_and_exists() -> None:
    session = _session(schema_found=True)
    assert await ns.assert_namespace(session) == DB_SCHEMA
    statement, params = session.execute.call_args.args
    assert "pg_namespace" in str(statement)
    assert params == {"schema": DB_SCHEMA}
    assert session.execute.await_count == 1


@pytest.mark.parametrize("value", ["", "   ", None])
async def test_guard_raises_when_schema_is_not_set(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    _use_schema(monkeypatch, value)
    session = _session(schema_found=True)
    with pytest.raises(ns.NamespaceError, match="not set"):
        await ns.assert_namespace(session)
    session.execute.assert_not_called()


@pytest.mark.parametrize("value", ["public", "PUBLIC", " public "])
async def test_guard_raises_when_schema_is_the_shared_schema(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _use_schema(monkeypatch, value)
    session = _session(schema_found=True)
    with pytest.raises(ns.NamespaceError, match="shared"):
        await ns.assert_namespace(session)
    session.execute.assert_not_called()


async def test_guard_raises_when_schema_is_not_a_plain_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_schema(monkeypatch, 'x"; DROP SCHEMA y; --')
    session = _session(schema_found=True)
    with pytest.raises(ns.NamespaceError, match="identifier"):
        await ns.assert_namespace(session)
    session.execute.assert_not_called()


async def test_guard_raises_when_schema_does_not_exist() -> None:
    session = _session(schema_found=False)
    with pytest.raises(ns.NamespaceError, match="does not exist"):
        await ns.assert_namespace(session)


async def test_guard_only_reads() -> None:
    session = _session(schema_found=True)
    await ns.assert_namespace(session)
    for call in session.execute.call_args_list:
        assert str(call.args[0]).lstrip().upper().startswith("SELECT")
    session.commit.assert_not_called()


def test_guard_is_where_seed_code_looks_for_it() -> None:
    # The seed session helper probes these modules in order and calls the
    # first ``assert_namespace`` it finds, passing the session if the function
    # takes a positional parameter. Keep the name, place and shape stable.
    assert not hasattr(importlib.import_module("app.core.config"), "assert_namespace")
    assert inspect.iscoroutinefunction(ns.assert_namespace)
    params = list(inspect.signature(ns.assert_namespace).parameters.values())
    assert [p.name for p in params] == ["session"]
    assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


# ── Fixed list ───────────────────────────────────────────────────────────────


def test_fixed_list_is_17_tables_and_6_views() -> None:
    assert len(ns.LEGACY_TABLES) == len(set(ns.LEGACY_TABLES)) == 17
    assert len(ns.LEGACY_VIEWS) == len(set(ns.LEGACY_VIEWS)) == 6
    assert ns.VERSION_TABLE in ns.LEGACY_TABLES
    assert not set(ns.LEGACY_TABLES) & set(ns.LEGACY_VIEWS)


def test_fixed_list_matches_the_migrations() -> None:
    views_009 = importlib.import_module("migrations.versions.009_analytics_views").VIEW_NAMES
    assert set(ns.LEGACY_VIEWS) == {"counterparty_pattern", *views_009}
    # Every legacy application table still has a model.
    models = {t.name for t in Base.metadata.tables.values()}
    assert set(ns.LEGACY_APP_TABLES) <= models


def test_project_tables_follow_the_metadata() -> None:
    names = set(ns.project_tables())
    assert set(ns.LEGACY_TABLES) <= names
    assert {t.name for t in Base.metadata.tables.values()} <= names
    assert set(ns.project_object_names()) == names | set(ns.PROJECT_VIEWS)


def test_project_tables_pick_up_a_table_added_later() -> None:
    from sqlalchemy import Column, Integer, MetaData, Table

    from app.db import base

    extra = MetaData(schema=DB_SCHEMA)
    Table("zz_added_by_a_later_migration", extra, Column("id", Integer, primary_key=True))
    original = base.Base.metadata
    try:
        base.Base.metadata = extra
        assert "zz_added_by_a_later_migration" in ns.project_tables()
        # The legacy list is still covered even if a model is removed.
        assert set(ns.LEGACY_TABLES) <= set(ns.project_tables())
    finally:
        base.Base.metadata = original


# ── Helpers ──────────────────────────────────────────────────────────────────


def test_quote_ident() -> None:
    assert ns.quote_ident("contract") == '"contract"'
    assert ns.qualified_ident(DB_SCHEMA, "contract") == f'"{DB_SCHEMA}"."contract"'
    for bad in ('a"b', "a b", "a;b", "A", "1a", "", "a.b"):
        with pytest.raises(ValueError):
            ns.quote_ident(bad)


def test_configured_schema_reads_settings() -> None:
    assert ns.configured_schema() == get_settings().db_schema


async def test_schema_exists() -> None:
    assert await ns.schema_exists(_session(schema_found=True), DB_SCHEMA) is True
    assert await ns.schema_exists(_session(schema_found=False), DB_SCHEMA) is False


async def test_fetch_relations_normalises_kinds() -> None:
    conn = AsyncMock()
    result = MagicMock()
    result.all.return_value = [
        ("public", "contract", "r"),
        ("public", "partitioned", "p"),
        ("public", "v_contract_value", "v"),
        ("public", "matview", "m"),
    ]
    conn.execute.return_value = result
    relations = await ns.fetch_relations(conn, ["public", DB_SCHEMA, "public"])
    assert [r.kind for r in relations] == ["r", "r", "v", "v"]
    assert conn.execute.call_args.args[1] == {"schemas": sorted({"public", DB_SCHEMA})}


async def test_begin_read_only_is_first_and_verified() -> None:
    conn = AsyncMock()
    shown = MagicMock()
    shown.first.return_value = ("on",)
    conn.execute.return_value = shown
    await ns.begin_read_only(conn)
    statements = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert statements == ["SET TRANSACTION READ ONLY", "SHOW transaction_read_only"]

    shown.first.return_value = ("off",)
    with pytest.raises(RuntimeError, match="read-only"):
        await ns.begin_read_only(conn)


def test_redact_connection_details() -> None:
    url = "postgresql+psycopg://alice:s3cret@db.host.example/mydb?sslmode=require"
    message = f"connection to db.host.example failed for alice (s3cret) on mydb; {url}"
    cleaned = ns.redact_connection_details(message, url)
    for secret in ("alice", "s3cret", "db.host.example", "mydb"):
        assert secret not in cleaned
    assert ns.redact_connection_details("boom", "") == "database error (details withheld)"
