"""Schema move script (task 0.5): statement builder, planning and the run.

Mocked catalogue and a fake connection only. Nothing here opens a connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.namespace import (
    KIND_TABLE,
    KIND_VIEW,
    LEGACY_TABLES,
    LEGACY_VIEWS,
    SHARED_SCHEMA,
    Relation,
)
from app.db.base import DB_SCHEMA
from scripts import move_to_schema as mv

SRC = SHARED_SCHEMA
DST = DB_SCHEMA


def _layout(schema: str) -> list[Relation]:
    return [
        *(Relation(schema, name, KIND_TABLE) for name in LEGACY_TABLES),
        *(Relation(schema, name, KIND_VIEW) for name in LEGACY_VIEWS),
    ]


# ── Statement builder ────────────────────────────────────────────────────────


def test_statements_for_the_full_list() -> None:
    statements = mv.build_statements(SRC, DST, LEGACY_TABLES, LEGACY_VIEWS)
    assert len(statements) == 1 + 17 + 6
    assert statements[0] == f'CREATE SCHEMA IF NOT EXISTS "{DST}"'
    tables = statements[1:18]
    views = statements[18:]
    assert tables == [f'ALTER TABLE "{SRC}"."{n}" SET SCHEMA "{DST}"' for n in LEGACY_TABLES]
    assert views == [f'ALTER VIEW "{SRC}"."{n}" SET SCHEMA "{DST}"' for n in LEGACY_VIEWS]


def test_statements_touch_only_the_listed_objects() -> None:
    statements = mv.build_statements(SRC, DST, LEGACY_TABLES, LEGACY_VIEWS)
    joined = "\n".join(statements).upper()
    for forbidden in ("DROP", "EXTENSION", "VECTOR", "TRUNCATE", "DELETE", "CASCADE", "GRANT"):
        assert forbidden not in joined
    # Nothing is created in, or moved into, the shared schema.
    assert all(s.endswith(f'"{DST}"') for s in statements)


def test_statements_only_for_what_is_given() -> None:
    assert mv.build_statements(SRC, DST, ["alert"], []) == [
        f'CREATE SCHEMA IF NOT EXISTS "{DST}"',
        f'ALTER TABLE "{SRC}"."alert" SET SCHEMA "{DST}"',
    ]


@pytest.mark.parametrize("bad", ['x"; DROP TABLE y; --', "a b", "A", ""])
def test_statements_reject_unsafe_identifiers(bad: str) -> None:
    with pytest.raises(ValueError):
        mv.build_statements(SRC, DST, [bad], [])
    with pytest.raises(ValueError):
        mv.build_statements(SRC, bad, ["alert"], [])


def test_statements_refuse_the_shared_schema_as_target() -> None:
    with pytest.raises(ValueError):
        mv.build_statements("other", SHARED_SCHEMA, ["alert"], [])
    with pytest.raises(ValueError):
        mv.build_statements(DST, DST, ["alert"], [])


# ── Planning ─────────────────────────────────────────────────────────────────


def test_plan_pre_move_moves_all_23() -> None:
    plan = mv.plan_move(_layout(SRC), SRC, DST)
    assert not plan.problems
    assert plan.tables_to_move == list(LEGACY_TABLES)
    assert plan.views_to_move == list(LEGACY_VIEWS)


def test_plan_post_move_has_nothing_to_do() -> None:
    plan = mv.plan_move(_layout(DST), SRC, DST)
    assert not plan.problems
    assert not plan.to_move
    assert {o.status for o in plan.objects} == {mv.ALREADY_MOVED}


def test_plan_ignores_objects_not_on_the_list() -> None:
    relations = [*_layout(SRC), Relation(SRC, "someone_elses_table", KIND_TABLE)]
    plan = mv.plan_move(relations, SRC, DST)
    assert "someone_elses_table" not in {o.name for o in plan.objects}
    assert len(plan.to_move) == 23


def test_plan_refuses_when_object_exists_in_both_schemas() -> None:
    relations = [*_layout(SRC), Relation(DST, "contract", KIND_TABLE)]
    plan = mv.plan_move(relations, SRC, DST)
    assert [(o.name, o.status) for o in plan.problems] == [("contract", mv.CONFLICT)]


def test_plan_refuses_when_object_is_missing() -> None:
    relations = [r for r in _layout(SRC) if r.name != "v_tabular_review"]
    plan = mv.plan_move(relations, SRC, DST)
    assert [(o.name, o.status) for o in plan.problems] == [("v_tabular_review", mv.MISSING)]


def test_plan_refuses_wrong_kind() -> None:
    relations = [r for r in _layout(SRC) if r.name != "alert"]
    relations.append(Relation(SRC, "alert", KIND_VIEW))
    plan = mv.plan_move(relations, SRC, DST)
    assert [(o.name, o.status) for o in plan.problems] == [("alert", mv.WRONG_KIND)]


# ── Verification after apply ─────────────────────────────────────────────────


def _snap(relations: list[Relation], rows: int = 0, target_exists: bool = True) -> mv.Snapshot:
    return mv.Snapshot(
        target_exists=target_exists,
        relations=relations,
        row_counts=dict.fromkeys(LEGACY_TABLES, rows),
    )


def test_verify_accepts_a_clean_move() -> None:
    before = _snap(_layout(SRC), target_exists=False)
    plan = mv.plan_move(before.relations, SRC, DST)
    assert mv.verify_after(before, _snap(_layout(DST)), plan) == []


def test_verify_rejects_a_changed_row_count() -> None:
    before = _snap(_layout(SRC))
    plan = mv.plan_move(before.relations, SRC, DST)
    after = _snap(_layout(DST))
    after.row_counts["contract"] = 3
    errors = mv.verify_after(before, after, plan)
    assert errors == ["row count of contract changed: 0 before, 3 after"]


def test_verify_rejects_an_object_left_behind() -> None:
    before = _snap(_layout(SRC))
    plan = mv.plan_move(before.relations, SRC, DST)
    after_relations = [r for r in _layout(DST) if r.name != "flag"]
    after_relations.append(Relation(SRC, "flag", KIND_TABLE))
    errors = mv.verify_after(before, _snap(after_relations), plan)
    assert any("flag is not in" in e for e in errors)
    assert any("flag is still in" in e for e in errors)


def test_verify_rejects_a_change_outside_the_list() -> None:
    other = Relation(SRC, "someone_elses_table", KIND_TABLE)
    before = _snap([*_layout(SRC), other])
    plan = mv.plan_move(before.relations, SRC, DST)
    errors = mv.verify_after(before, _snap(_layout(DST)), plan)
    assert errors == ["an object outside the fixed list changed"]


# ── The run, against a fake connection ───────────────────────────────────────


class _FakeConn:
    """Records every statement and answers catalogue queries from a layout."""

    def __init__(self, relations: list[Relation], *, rows_after_move: int = 0) -> None:
        self.relations = list(relations)
        self.statements: list[str] = []
        self.committed = False
        self.rolled_back = False
        self.rows_after_move = rows_after_move
        self._moved = False

    async def execute(self, statement: object, params: object = None) -> MagicMock:
        sql = str(statement)
        self.statements.append(sql)
        result = MagicMock()
        if sql.startswith("SHOW transaction_read_only"):
            result.first.return_value = ("on",)
        elif "pg_namespace WHERE nspname" in sql:
            found = any(r.schema == DST for r in self.relations) or self._moved
            result.first.return_value = (1,) if found else None
        elif "pg_class" in sql:
            result.all.return_value = [(r.schema, r.name, r.kind) for r in self.relations]
        elif sql.startswith("SELECT count(*)"):
            result.scalar_one.return_value = self.rows_after_move if self._moved else 0
        elif sql.startswith("ALTER "):
            name = sql.split('"')[3]
            self._moved = True
            self.relations = [
                Relation(DST, r.name, r.kind) if r.schema == SRC and r.name == name else r
                for r in self.relations
            ]
        return result

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn
        self.disposed = False

    def connect(self) -> _FakeConn:
        return self._conn

    async def dispose(self) -> None:
        self.disposed = True


def _patch_engine(monkeypatch: pytest.MonkeyPatch, conn: _FakeConn) -> _FakeEngine:
    engine = _FakeEngine(conn)
    monkeypatch.setattr(mv, "create_async_engine", lambda *a, **k: engine)
    return engine


_WRITE_WORDS = ("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "GRANT")


async def test_dry_run_is_read_only_and_issues_no_ddl(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _FakeConn(_layout(SRC))
    engine = _patch_engine(monkeypatch, conn)

    assert await mv.run(apply=False) == 0

    assert conn.statements[0] == "SET TRANSACTION READ ONLY"
    for sql in conn.statements:
        assert not sql.lstrip().upper().startswith(_WRITE_WORDS), sql
    assert not conn.committed
    assert conn.rolled_back
    assert engine.disposed
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert f'ALTER TABLE "{SRC}"."alembic_version" SET SCHEMA "{DST}";' in out
    assert "Nothing was changed." in out
    assert f"{DST}: 17 tables, 6 views" in out


def test_dry_run_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    async def fake_run(apply: bool) -> int:
        seen.append(apply)
        return 0

    monkeypatch.setattr(mv, "run", fake_run)
    assert mv.main([]) == 0
    assert mv.main(["--dry-run"]) == 0
    assert mv.main(["--apply"]) == 0
    assert seen == [False, False, True]
    with pytest.raises(SystemExit):
        mv.main(["--dry-run", "--apply"])


async def test_apply_moves_everything_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConn(_layout(SRC))
    _patch_engine(monkeypatch, conn)

    assert await mv.run(apply=True) == 0

    ddl = [s for s in conn.statements if s.startswith(("CREATE", "ALTER"))]
    assert ddl == mv.build_statements(SRC, DST, LEGACY_TABLES, LEGACY_VIEWS)
    assert conn.committed and not conn.rolled_back
    assert "SET TRANSACTION READ ONLY" not in conn.statements
    assert {r.schema for r in conn.relations} == {DST}


async def test_apply_rolls_back_when_a_row_count_changes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _FakeConn(_layout(SRC), rows_after_move=5)
    _patch_engine(monkeypatch, conn)

    assert await mv.run(apply=True) == 1

    assert not conn.committed
    assert conn.rolled_back
    assert "ROLLED BACK" in capsys.readouterr().out


@pytest.mark.parametrize("apply", [False, True])
async def test_run_refuses_on_conflict_without_ddl(
    monkeypatch: pytest.MonkeyPatch, apply: bool
) -> None:
    conn = _FakeConn([*_layout(SRC), Relation(DST, "contract", KIND_TABLE)])
    _patch_engine(monkeypatch, conn)

    assert await mv.run(apply=apply) == 2

    assert not any(s.startswith(("CREATE", "ALTER")) for s in conn.statements)
    assert not conn.committed


@pytest.mark.parametrize("apply", [False, True])
async def test_run_after_the_move_is_a_no_op(
    monkeypatch: pytest.MonkeyPatch, apply: bool
) -> None:
    conn = _FakeConn(_layout(DST))
    _patch_engine(monkeypatch, conn)

    assert await mv.run(apply=apply) == 0

    assert not any(s.startswith(("CREATE", "ALTER")) for s in conn.statements)
    assert not conn.committed


def test_main_reports_errors_without_connection_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.core.config import get_settings

    url = get_settings().database_url

    async def boom(apply: bool) -> int:
        raise RuntimeError(f"could not connect using {url}")

    monkeypatch.setattr(mv, "run", boom)
    assert mv.main([]) == 3
    out = capsys.readouterr().out
    assert "ERROR: RuntimeError" in out
    assert url not in out
    assert "neon.tech" not in out
