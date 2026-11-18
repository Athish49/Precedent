#!/usr/bin/env python3
"""One-off clean-up: move this project's objects into the project schema.

Migrations 001 to 009 created 17 tables and 6 views in the database's shared
default schema. This script moves exactly those 23 objects into the schema
named by ``Settings.db_schema`` with ``ALTER ... SET SCHEMA``. Indexes,
constraints and owned sequences move with their tables; views keep working
because they refer to tables by identity, not by name. Nothing else is
touched, and the ``vector`` extension stays where it is.

Usage (from ``backend/``)::

    python -m scripts.move_to_schema            # dry run (default): read-only
    python -m scripts.move_to_schema --apply    # execute, in one transaction

Dry run: opens a READ ONLY transaction, reads the catalogue and the row
counts, and prints what ``--apply`` would do. It issues no DDL at all.

Apply: one transaction. It prints object and row counts before and after, and
rolls back without committing if any row count changes or the result is not
exactly the expected layout.

Exit codes: 0 ok (or nothing left to move), 1 apply verification failed and
was rolled back, 2 the pre-flight check refused, 3 could not run.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.namespace import (
    KIND_TABLE,
    KIND_VIEW,
    LEGACY_TABLES,
    LEGACY_VIEWS,
    SHARED_SCHEMA,
    Relation,
    begin_read_only,
    configured_schema,
    fetch_relations,
    qualified_ident,
    quote_ident,
    redact_connection_details,
    schema_exists,
)

# Status of one listed object, decided from the catalogue.
MOVE = "move"  # in the source schema only: will be moved
ALREADY_MOVED = "already moved"  # in the target schema only: nothing to do
CONFLICT = "CONFLICT"  # in both schemas: refuse
MISSING = "MISSING"  # in neither schema: refuse
WRONG_KIND = "WRONG KIND"  # found, but a table where a view is expected or vice versa

_BLOCKING = (CONFLICT, MISSING, WRONG_KIND)
_KIND_LABEL = {KIND_TABLE: "table", KIND_VIEW: "view"}


@dataclass(frozen=True)
class PlannedObject:
    name: str
    kind: str  # KIND_TABLE or KIND_VIEW
    status: str


@dataclass
class MovePlan:
    source: str
    target: str
    objects: list[PlannedObject] = field(default_factory=list)

    @property
    def problems(self) -> list[PlannedObject]:
        return [o for o in self.objects if o.status in _BLOCKING]

    @property
    def to_move(self) -> list[PlannedObject]:
        return [o for o in self.objects if o.status == MOVE]

    @property
    def tables_to_move(self) -> list[str]:
        return [o.name for o in self.to_move if o.kind == KIND_TABLE]

    @property
    def views_to_move(self) -> list[str]:
        return [o.name for o in self.to_move if o.kind == KIND_VIEW]


@dataclass
class Snapshot:
    """What the catalogue holds for the two schemas at one moment."""

    target_exists: bool
    relations: list[Relation]
    row_counts: dict[str, int]  # listed table name → rows, wherever the table is

    def count(self, schema: str, kind: str) -> int:
        return sum(1 for r in self.relations if r.schema == schema and r.kind == kind)


# ── Pure planning: no database access ─────────────────────────────────────────


def build_statements(
    source: str,
    target: str,
    tables: Sequence[str],
    views: Sequence[str],
) -> list[str]:
    """Return the DDL that moves *tables* and *views* from *source* to *target*.

    Every identifier is validated and quoted. Tables go first, then views.
    The first statement creates the target schema if it does not exist.
    """
    if source == target:
        raise ValueError("source and target schema are the same")
    if target == SHARED_SCHEMA:
        raise ValueError(f"the target schema must not be {SHARED_SCHEMA!r}")
    target_ident = quote_ident(target)
    statements = [f"CREATE SCHEMA IF NOT EXISTS {target_ident}"]
    for name in tables:
        statements.append(
            f"ALTER TABLE {qualified_ident(source, name)} SET SCHEMA {target_ident}"
        )
    for name in views:
        statements.append(
            f"ALTER VIEW {qualified_ident(source, name)} SET SCHEMA {target_ident}"
        )
    return statements


def plan_move(
    relations: Sequence[Relation],
    source: str,
    target: str,
    tables: Sequence[str] = LEGACY_TABLES,
    views: Sequence[str] = LEGACY_VIEWS,
) -> MovePlan:
    """Decide, for each listed object, whether it can be moved.

    Works only from the fixed list. An object is moved only if it exists in
    *source* with the expected kind and no object of that name exists in
    *target*.
    """
    found = {(r.schema, r.name): r.kind for r in relations}
    plan = MovePlan(source=source, target=target)
    for kind, names in ((KIND_TABLE, tables), (KIND_VIEW, views)):
        for name in names:
            in_source = found.get((source, name))
            in_target = found.get((target, name))
            if in_source is not None and in_target is not None:
                status = CONFLICT
            elif in_source is None and in_target is None:
                status = MISSING
            elif (in_source or in_target) != kind:
                status = WRONG_KIND
            elif in_source is not None:
                status = MOVE
            else:
                status = ALREADY_MOVED
            plan.objects.append(PlannedObject(name=name, kind=kind, status=status))
    return plan


def verify_after(before: Snapshot, after: Snapshot, plan: MovePlan) -> list[str]:
    """Return the reasons the applied move must be rolled back (empty if none)."""
    errors: list[str] = []
    if not after.target_exists:
        errors.append(f"schema {plan.target} does not exist after the move")
    present = {(r.schema, r.name): r.kind for r in after.relations}
    for obj in plan.objects:
        if present.get((plan.target, obj.name)) != obj.kind:
            errors.append(f"{_KIND_LABEL[obj.kind]} {obj.name} is not in {plan.target}")
        if (plan.source, obj.name) in present:
            errors.append(f"{_KIND_LABEL[obj.kind]} {obj.name} is still in {plan.source}")
    for name, rows in before.row_counts.items():
        now = after.row_counts.get(name)
        if now != rows:
            errors.append(f"row count of {name} changed: {rows} before, {now} after")
    # Nothing outside the list may have changed schema.
    listed = {o.name for o in plan.objects}
    others_before = sorted(r for r in before.relations if r.name not in listed)
    others_after = sorted(r for r in after.relations if r.name not in listed)
    if others_before != others_after:
        errors.append("an object outside the fixed list changed")
    return errors


# ── Reading the database ──────────────────────────────────────────────────────


async def take_snapshot(conn: Any, source: str, target: str) -> Snapshot:
    """Read the tables and views of both schemas and count rows in listed tables."""
    relations = await fetch_relations(conn, [source, target])
    row_counts: dict[str, int] = {}
    for rel in relations:
        if rel.kind == KIND_TABLE and rel.name in LEGACY_TABLES and rel.name not in row_counts:
            result = await conn.execute(
                text(f"SELECT count(*) FROM {qualified_ident(rel.schema, rel.name)}")
            )
            row_counts[rel.name] = int(result.scalar_one())
    return Snapshot(
        target_exists=await schema_exists(conn, target),
        relations=list(relations),
        row_counts=row_counts,
    )


# ── Printing ──────────────────────────────────────────────────────────────────


def format_snapshot(title: str, snap: Snapshot, source: str, target: str) -> list[str]:
    lines = [title, f"  {'schema':<14}{'exists':<8}{'tables':>7}{'views':>7}"]
    for schema, exists in ((source, True), (target, snap.target_exists)):
        lines.append(
            f"  {schema:<14}{('yes' if exists else 'no'):<8}"
            f"{snap.count(schema, KIND_TABLE):>7}{snap.count(schema, KIND_VIEW):>7}"
        )
    where = {r.name: r.schema for r in snap.relations if r.kind == KIND_TABLE}
    lines.append(f"  {'listed table':<22}{'schema':<14}{'rows':>6}")
    for name in LEGACY_TABLES:
        if name in snap.row_counts:
            lines.append(f"  {name:<22}{where[name]:<14}{snap.row_counts[name]:>6}")
        else:
            lines.append(f"  {name:<22}{'(not found)':<14}{'-':>6}")
    lines.append(f"  total rows in listed tables: {sum(snap.row_counts.values())}")
    return lines


def format_plan(plan: MovePlan) -> list[str]:
    lines = [
        f"Fixed list: {len(LEGACY_TABLES)} tables and {len(LEGACY_VIEWS)} views",
        f"  {'kind':<7}{'name':<26}status",
    ]
    for obj in plan.objects:
        lines.append(f"  {_KIND_LABEL[obj.kind]:<7}{obj.name:<26}{obj.status}")
    return lines


def format_unlisted(snap: Snapshot, plan: MovePlan) -> list[str]:
    listed = {o.name for o in plan.objects}
    lines = []
    for schema in (plan.source, plan.target):
        others = [r for r in snap.relations if r.schema == schema and r.name not in listed]
        if others:
            lines.append(f"Tables and views in {schema} that are not on the list (left alone):")
            lines.extend(f"  {_KIND_LABEL[r.kind]:<7}{r.name}" for r in others)
        else:
            lines.append(f"Tables and views in {schema} that are not on the list: none")
    return lines


def _emit(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────


async def run(apply: bool) -> int:
    source = SHARED_SCHEMA
    target = configured_schema()
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )
    mode = "APPLY" if apply else "DRY RUN (read-only; nothing will be changed)"
    print(f"move_to_schema: {mode}")
    print(f"source schema: {source}    target schema: {target}")
    print()
    try:
        async with engine.connect() as conn:
            # One transaction for everything below. A dry run can never write.
            if apply:
                await conn.execute(text("SET LOCAL lock_timeout = '15s'"))
            else:
                await begin_read_only(conn)

            before = await take_snapshot(conn, source, target)
            plan = plan_move(before.relations, source, target)
            _emit(format_snapshot("Before", before, source, target))
            _emit(format_plan(plan))
            _emit(format_unlisted(before, plan))

            if plan.problems:
                print("REFUSED: the catalogue does not match the fixed list:")
                for obj in plan.problems:
                    print(f"  {_KIND_LABEL[obj.kind]} {obj.name}: {obj.status}")
                await conn.rollback()
                return 2

            nonzero = {n: c for n, c in before.row_counts.items() if c}
            if nonzero:
                print(f"Note: tables with rows (kept as they are by the move): {nonzero}")
                print()

            if not plan.to_move:
                print("Nothing to move: every listed object is already in the target schema.")
                await conn.rollback()
                return 0

            statements = build_statements(
                source, target, plan.tables_to_move, plan.views_to_move
            )
            header = "Statements" if apply else "Statements --apply would run, in one transaction"
            print(f"{header} ({len(statements)}):")
            for statement in statements:
                print(f"  {statement};")
            print()

            if not apply:
                moved_tables = len(plan.tables_to_move)
                moved_views = len(plan.views_to_move)
                print("Expected after --apply:")
                print(
                    f"  {source}: {before.count(source, KIND_TABLE) - moved_tables} tables, "
                    f"{before.count(source, KIND_VIEW) - moved_views} views"
                )
                print(
                    f"  {target}: {before.count(target, KIND_TABLE) + moved_tables} tables, "
                    f"{before.count(target, KIND_VIEW) + moved_views} views"
                )
                print()
                print("Dry run complete. No statement above was executed. Nothing was changed.")
                await conn.rollback()
                return 0

            for statement in statements:
                await conn.execute(text(statement))
            after = await take_snapshot(conn, source, target)
            _emit(format_snapshot("After (not yet committed)", after, source, target))
            errors = verify_after(before, after, plan)
            if errors:
                await conn.rollback()
                print("ROLLED BACK, nothing was changed:")
                for error in errors:
                    print(f"  {error}")
                return 1
            await conn.commit()
            print(f"COMMITTED: moved {len(plan.to_move)} objects from {source} to {target}.")
            return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="read-only: show what would be moved (the default)",
    )
    group.add_argument("--apply", action="store_true", help="execute the move")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(apply=bool(args.apply)))
    except Exception as exc:  # report without leaking connection details
        try:
            url = get_settings().database_url
        except Exception:
            url = ""
        print(f"ERROR: {type(exc).__name__}: {redact_connection_details(str(exc), url)}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
