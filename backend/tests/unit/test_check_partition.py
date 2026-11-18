"""Partition check script (task 0.6), against mocked catalogues.

No connection, no bucket, no filesystem access: every store is faked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.namespace import (
    KIND_TABLE,
    KIND_VIEW,
    LEGACY_TABLES,
    LEGACY_VIEWS,
    SHARED_SCHEMA,
    Relation,
    project_object_names,
)
from app.db.base import DB_SCHEMA
from scripts import check_partition as cp


def _layout(schema: str) -> list[Relation]:
    return [
        *(Relation(schema, name, KIND_TABLE) for name in LEGACY_TABLES),
        *(Relation(schema, name, KIND_VIEW) for name in LEGACY_VIEWS),
    ]


def _by_name(checks: list[cp.Check]) -> dict[str, cp.Check]:
    return {c.name: c for c in checks}


def _postgres(relations: list[Relation], schema_present: bool) -> list[cp.Check]:
    return cp.evaluate_postgres(relations, schema_present, DB_SCHEMA, project_object_names())


# ── Postgres ─────────────────────────────────────────────────────────────────


def test_pre_move_layout_fails() -> None:
    checks = _postgres(_layout(SHARED_SCHEMA), schema_present=False)
    assert [c.ok for c in checks] == [False, False, False]
    stray = checks[2]
    assert stray.detail.startswith("23 found: ")
    for name in (*LEGACY_TABLES, *LEGACY_VIEWS):
        assert name in stray.detail


def test_post_move_layout_passes() -> None:
    checks = _postgres(_layout(DB_SCHEMA), schema_present=True)
    assert all(c.ok for c in checks), checks
    assert len(checks) == 3


def test_fails_when_schema_is_missing() -> None:
    checks = _postgres([], schema_present=False)
    assert _by_name(checks)["project schema exists"].ok is False


def test_fails_when_version_table_is_not_in_project_schema() -> None:
    relations = [r for r in _layout(DB_SCHEMA) if r.name != "alembic_version"]
    relations.append(Relation(SHARED_SCHEMA, "alembic_version", KIND_TABLE))
    by_name = _by_name(_postgres(relations, schema_present=True))
    assert by_name["alembic_version in project schema"].ok is False
    stray = by_name[f"no project objects in {SHARED_SCHEMA}"]
    assert stray.ok is False
    assert stray.detail == "1 found: alembic_version"


def test_fails_for_a_single_project_view_left_in_the_shared_schema() -> None:
    relations = [*_layout(DB_SCHEMA), Relation(SHARED_SCHEMA, "v_portfolio_risk", KIND_VIEW)]
    stray = _postgres(relations, schema_present=True)[2]
    assert stray.ok is False
    assert stray.detail == "1 found: v_portfolio_risk"


def test_other_projects_objects_in_the_shared_schema_are_ignored() -> None:
    relations = [*_layout(DB_SCHEMA), Relation(SHARED_SCHEMA, "someone_elses_table", KIND_TABLE)]
    assert all(c.ok for c in _postgres(relations, schema_present=True))


def test_a_table_added_by_a_later_migration_is_covered() -> None:
    names = [*project_object_names(), "playbook_version"]
    relations = [*_layout(DB_SCHEMA), Relation(SHARED_SCHEMA, "playbook_version", KIND_TABLE)]
    checks = cp.evaluate_postgres(relations, True, DB_SCHEMA, names)
    assert checks[2].ok is False
    assert checks[2].detail == "1 found: playbook_version"


class _FakeConn:
    def __init__(self, relations: list[Relation], schema_present: bool) -> None:
        self.relations = relations
        self.schema_present = schema_present
        self.statements: list[str] = []
        self.committed = False

    async def execute(self, statement: object, params: object = None) -> MagicMock:
        sql = str(statement)
        self.statements.append(sql)
        result = MagicMock()
        if sql.startswith("SHOW"):
            result.first.return_value = ("on",)
        elif "pg_namespace WHERE nspname" in sql:
            result.first.return_value = (1,) if self.schema_present else None
        elif "pg_class" in sql:
            result.all.return_value = [(r.schema, r.name, r.kind) for r in self.relations]
        return result

    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    def connect(self) -> object:
        if isinstance(self._conn, Exception):
            raise self._conn
        return self._conn

    async def dispose(self) -> None:
        return None


async def test_check_postgres_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn(_layout(DB_SCHEMA), schema_present=True)
    monkeypatch.setattr(cp, "create_async_engine", lambda *a, **k: _FakeEngine(conn))

    checks, notes = await cp.check_postgres(DB_SCHEMA)

    assert all(c.ok for c in checks)
    assert conn.statements[0] == "SET TRANSACTION READ ONLY"
    for sql in conn.statements[2:]:
        assert sql.lstrip().upper().startswith("SELECT"), sql
    assert not conn.committed
    assert notes == [f"{SHARED_SCHEMA}: 0 tables, 0 views", f"{DB_SCHEMA}: 17 tables, 6 views"]


async def test_check_postgres_reports_unreachable_database_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    url = get_settings().database_url
    error = ConnectionError(f"cannot reach {url}")
    monkeypatch.setattr(cp, "create_async_engine", lambda *a, **k: _FakeEngine(error))

    checks, notes = await cp.check_postgres(DB_SCHEMA)

    assert [c.ok for c in checks] == [False]
    assert "ConnectionError" in checks[0].detail
    assert "neon.tech" not in checks[0].detail
    assert notes == []


# ── Object storage ───────────────────────────────────────────────────────────


def _settings(**overrides: str) -> SimpleNamespace:
    values = {
        "object_storage_endpoint": "https://abc123.r2.cloudflarestorage.com",
        "object_storage_bucket": "shared-bucket",
        "object_storage_access_key": "AKIAEXAMPLEKEY",
        "object_storage_secret_key": "s3cr3tvalue",
        "object_storage_prefix": DB_SCHEMA,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _factory(top_level: list[str]) -> MagicMock:
    backend = MagicMock()
    backend.list_top_level.return_value = top_level
    return MagicMock(return_value=backend)


@pytest.mark.parametrize(
    "overrides",
    [
        {"object_storage_endpoint": ""},
        {"object_storage_bucket": "  "},
        {"object_storage_endpoint": "https://placeholder.invalid"},
        {"object_storage_endpoint": "https://storage.invalid"},
        {"object_storage_bucket": "placeholder"},
        {"object_storage_access_key": "placeholder"},
        {"object_storage_secret_key": "placeholder"},
        {"object_storage_endpoint": "not a url"},
    ],
)
def test_storage_not_configured_fails_without_contacting_the_bucket(
    overrides: dict[str, str],
) -> None:
    factory = _factory([])
    checks = cp.check_storage(_settings(**overrides), factory)
    assert [c.ok for c in checks] == [False, False]
    assert checks[0].detail.startswith("not configured: OBJECT_STORAGE_")
    factory.assert_not_called()
    # Names of variables only; never a value.
    assert "s3cr3tvalue" not in checks[0].detail
    assert "AKIAEXAMPLEKEY" not in checks[0].detail


def test_storage_passes_when_everything_is_under_the_prefix() -> None:
    factory = _factory([f"{DB_SCHEMA}/", "other-project/", "readme.txt"])
    checks = cp.check_storage(_settings(), factory)
    assert all(c.ok for c in checks), checks


@pytest.mark.parametrize("stray", ["contracts/", "__health_check__"])
def test_storage_fails_for_a_project_key_outside_the_prefix(stray: str) -> None:
    factory = _factory([f"{DB_SCHEMA}/", stray])
    checks = cp.check_storage(_settings(), factory)
    assert checks[0].ok is True
    assert checks[1].ok is False
    assert checks[1].detail == f"1 found: {stray}"


def test_storage_unreachable_fails_without_crashing_or_leaking() -> None:
    factory = MagicMock(side_effect=OSError("cannot reach abc123.r2.cloudflarestorage.com"))
    checks = cp.check_storage(_settings(), factory)
    assert checks[1].ok is False
    assert checks[1].detail == "not checked: storage unreachable (OSError)"
    assert "cloudflarestorage" not in " ".join(c.detail for c in checks)


# ── Local storage ────────────────────────────────────────────────────────────


def test_local_folder_paths_cover_the_legacy_name_and_the_namespace() -> None:
    assert cp.local_storage_folders("precedent") == [cp.LEGACY_LOCAL_FOLDER]
    assert cp.local_storage_folders("other") == [
        cp.LEGACY_LOCAL_FOLDER,
        cp.LOCAL_FOLDER_TEMPLATE.format(namespace="other"),
    ]


def test_local_folder_present_fails() -> None:
    checks = cp.check_local_storage("other", exists=lambda path: path.endswith("other-storage"))
    assert [c.ok for c in checks] == [True, False]


def test_local_folder_absent_passes() -> None:
    checks = cp.check_local_storage("other", exists=lambda path: False)
    assert all(c.ok for c in checks)


# ── Report and exit code ─────────────────────────────────────────────────────


def test_report_has_a_table_per_store() -> None:
    checks = [
        cp.Check("Postgres", "project schema exists", True, "x"),
        cp.Check("Object storage", "storage configured", False, "not configured"),
        cp.Check("Local storage", "no folder", True, "absent"),
    ]
    report = cp.format_report(checks, {"Postgres": ["a note"]})
    lines = report.splitlines()
    assert [line for line in lines if line and not line.startswith(" ")] == [
        "Postgres",
        "Object storage",
        "Local storage",
        "RESULT: FAIL (1 of 3 checks failed)",
    ]
    assert "  PASS  project schema exists  x" in lines
    assert "  FAIL  storage configured  not configured" in lines
    assert "        (a note)" in lines
    assert cp.format_report(checks[:1]).endswith("RESULT: PASS (1 checks)")


async def _run_with(
    monkeypatch: pytest.MonkeyPatch,
    relations: list[Relation],
    schema_present: bool,
    settings: SimpleNamespace,
    top_level: list[str],
) -> int:
    conn = _FakeConn(relations, schema_present)
    monkeypatch.setattr(cp, "create_async_engine", lambda *a, **k: _FakeEngine(conn))
    settings.project_namespace = "other"
    settings.database_url = "postgresql+psycopg://u:p@db.invalid/x"
    monkeypatch.setattr(cp, "get_settings", lambda: settings)
    monkeypatch.setattr(cp, "check_storage", lambda s: cp_check_storage(s, _factory(top_level)))
    monkeypatch.setattr(cp, "check_local_storage", lambda ns: cp_check_local(ns, lambda p: False))
    return await cp.run()


cp_check_storage = cp.check_storage
cp_check_local = cp.check_local_storage


async def test_run_exits_zero_on_the_post_move_layout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await _run_with(monkeypatch, _layout(DB_SCHEMA), True, _settings(), [f"{DB_SCHEMA}/"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "RESULT: PASS" in out
    assert "FAIL" not in out
    assert "s3cr3tvalue" not in out and "cloudflarestorage" not in out


async def test_run_exits_non_zero_on_the_pre_move_layout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await _run_with(
        monkeypatch,
        _layout(SHARED_SCHEMA),
        False,
        _settings(object_storage_endpoint="https://placeholder.invalid"),
        [],
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "RESULT: FAIL" in out
    assert "23 found" in out
