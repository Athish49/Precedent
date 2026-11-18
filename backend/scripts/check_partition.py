#!/usr/bin/env python3
"""Read-only partition check: is everything this project owns in its namespace?

The database and the storage account are shared with other projects. This
script confirms that nothing of this project sits outside its namespace. It
prints a short table per store and exits non-zero if any line fails.

Postgres
    * the project schema exists;
    * the Alembic version table is in the project schema;
    * no project table or view exists in the shared default schema.
Object storage
    * the four storage settings are configured (not blank, not placeholders);
    * no key written by this project lies outside the project prefix.
Local storage
    * no local storage folder for this project exists.

Usage (from ``backend/``)::

    python -m scripts.check_partition

It never writes. The database transaction is opened READ ONLY, and storage is
only listed at the root of the bucket: no object is read, written or deleted.

"Project table or view" means the fixed list in ``app.core.namespace`` plus
every table on ``Base.metadata``, so tables added by later migrations are
covered automatically. A later task that adds a view appends its name to
``app.core.namespace.PROJECT_VIEWS``; a later task that writes objects under a
new top-level key adds it to ``PROJECT_KEY_ROOTS`` below.

Exit codes: 0 every check passed, 1 at least one check failed.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.namespace import (
    KIND_TABLE,
    KIND_VIEW,
    SHARED_SCHEMA,
    VERSION_TABLE,
    Relation,
    begin_read_only,
    configured_schema,
    fetch_relations,
    project_object_names,
    redact_connection_details,
    schema_exists,
)

PASS = "PASS"
FAIL = "FAIL"

# Where this project's logical object keys start. ``contracts/...`` holds
# uploaded files; the health check writes one object at the top of the prefix.
PROJECT_KEY_ROOTS: tuple[str, ...] = ("contracts",)
HEALTH_CHECK_KEY = "__health_check__"

# The folder the removed local storage backend used, kept by name so it can be
# detected. The second form covers a namespace other than the original one.
LEGACY_LOCAL_FOLDER = "/tmp/precedent-storage"
LOCAL_FOLDER_TEMPLATE = "/tmp/{namespace}-storage"

# Values that satisfy the required-settings check but point nowhere: reserved
# top-level domains (RFC 2606) and obvious placeholder words.
_PLACEHOLDER_TLDS = (".invalid", ".example", ".test", ".localhost")
_PLACEHOLDER_WORDS = ("placeholder", "changeme", "your-", "<", "xxx")
_STORAGE_SETTINGS: tuple[tuple[str, str], ...] = (
    ("object_storage_endpoint", "OBJECT_STORAGE_ENDPOINT"),
    ("object_storage_bucket", "OBJECT_STORAGE_BUCKET"),
    ("object_storage_access_key", "OBJECT_STORAGE_ACCESS_KEY"),
    ("object_storage_secret_key", "OBJECT_STORAGE_SECRET_KEY"),
)


@dataclass(frozen=True)
class Check:
    store: str
    name: str
    ok: bool
    detail: str

    @property
    def status(self) -> str:
        return PASS if self.ok else FAIL


# ── Postgres ──────────────────────────────────────────────────────────────────

_POSTGRES = "Postgres"


def evaluate_postgres(
    relations: Iterable[Relation],
    schema_present: bool,
    schema: str,
    project_names: Sequence[str],
) -> list[Check]:
    """Judge a catalogue snapshot. Pure: no database access.

    *relations* are the tables and views of the shared default schema and of
    the project schema. *project_names* are the bare names this project owns.
    """
    relations = list(relations)
    checks = [
        Check(
            _POSTGRES,
            "project schema exists",
            schema_present,
            schema if schema_present else f"schema {schema} is missing",
        )
    ]

    version_here = any(
        r.schema == schema and r.name == VERSION_TABLE and r.kind == KIND_TABLE
        for r in relations
    )
    checks.append(
        Check(
            _POSTGRES,
            f"{VERSION_TABLE} in project schema",
            version_here,
            f"{schema}.{VERSION_TABLE}"
            if version_here
            else f"{VERSION_TABLE} not found in {schema}",
        )
    )

    owned = set(project_names)
    stray = sorted(r.name for r in relations if r.schema == SHARED_SCHEMA and r.name in owned)
    checks.append(
        Check(
            _POSTGRES,
            f"no project objects in {SHARED_SCHEMA}",
            not stray,
            "none" if not stray else f"{len(stray)} found: {', '.join(stray)}",
        )
    )
    return checks


def summarise_postgres(relations: Iterable[Relation], schema: str) -> list[str]:
    """Informational lines: how many tables and views each schema holds."""
    relations = list(relations)
    lines = []
    for name in (SHARED_SCHEMA, schema):
        tables = sum(1 for r in relations if r.schema == name and r.kind == KIND_TABLE)
        views = sum(1 for r in relations if r.schema == name and r.kind == KIND_VIEW)
        lines.append(f"{name}: {tables} tables, {views} views")
    return lines


async def check_postgres(schema: str) -> tuple[list[Check], list[str]]:
    """Read the catalogue in one READ ONLY transaction and judge it."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )
    try:
        async with engine.connect() as conn:
            await begin_read_only(conn)
            present = await schema_exists(conn, schema)
            relations = await fetch_relations(conn, [SHARED_SCHEMA, schema])
            await conn.rollback()
    except Exception as exc:
        detail = redact_connection_details(str(exc), settings.database_url).splitlines()[0]
        return (
            [
                Check(
                    _POSTGRES,
                    "database reachable",
                    False,
                    f"{type(exc).__name__}: {detail}"[:200],
                )
            ],
            [],
        )
    finally:
        await engine.dispose()
    checks = evaluate_postgres(relations, present, schema, project_object_names())
    return checks, summarise_postgres(relations, schema)


# ── Object storage ────────────────────────────────────────────────────────────

_STORAGE = "Object storage"


def unconfigured_storage_settings(settings: Any) -> list[str]:
    """Return the storage variables that are blank or hold a placeholder."""
    missing = []
    for attr, env_name in _STORAGE_SETTINGS:
        value = getattr(settings, attr, None)
        if not isinstance(value, str) or not value.strip():
            missing.append(env_name)
            continue
        lowered = value.strip().lower()
        if any(word in lowered for word in _PLACEHOLDER_WORDS):
            missing.append(env_name)
        elif attr == "object_storage_endpoint":
            host = (urlparse(lowered).hostname or "").rstrip(".")
            if not host or host.endswith(_PLACEHOLDER_TLDS) or host == "localhost":
                missing.append(env_name)
    return missing


def find_stray_keys(top_level: Iterable[str], prefix: str) -> list[str]:
    """Return root-level bucket names that look like this project's, outside *prefix*.

    *top_level* is the root listing of the bucket: plain keys, and folders
    with a trailing ``/``. Everything under ``{prefix}/`` is in place. Outside
    it, a name is this project's if it is the health-check object or one of
    the project's key roots. Other names belong to other projects and are
    ignored.
    """
    own_root = prefix.split("/", 1)[0]
    project_names = {HEALTH_CHECK_KEY, *PROJECT_KEY_ROOTS}
    stray = []
    for name in top_level:
        bare = name.rstrip("/")
        if bare == own_root:
            continue
        if bare in project_names:
            stray.append(name)
    return sorted(stray)


def check_storage(
    settings: Any,
    storage_factory: Callable[[Any], Any] | None = None,
) -> list[Check]:
    """Check object storage. Never raises; never reads or writes an object.

    When storage is not configured the bucket is not contacted at all.
    """
    missing = unconfigured_storage_settings(settings)
    if missing:
        return [
            Check(
                _STORAGE,
                "storage configured",
                False,
                "not configured: " + ", ".join(missing) + " blank or placeholder",
            ),
            Check(_STORAGE, "no project keys outside prefix", False, "not checked: not configured"),
        ]

    prefix = str(getattr(settings, "object_storage_prefix", "") or "")
    checks = [Check(_STORAGE, "storage configured", True, f"prefix {prefix}/")]
    try:
        if storage_factory is None:
            from app.core.storage import get_storage  # noqa: PLC0415

            storage_factory = get_storage
        top_level = storage_factory(settings).list_top_level()
    except Exception as exc:
        # The message may quote the endpoint or bucket; report the type only.
        checks.append(
            Check(
                _STORAGE,
                "no project keys outside prefix",
                False,
                f"not checked: storage unreachable ({type(exc).__name__})",
            )
        )
        return checks
    stray = find_stray_keys(top_level, prefix)
    checks.append(
        Check(
            _STORAGE,
            "no project keys outside prefix",
            not stray,
            "none" if not stray else f"{len(stray)} found: {', '.join(stray)}",
        )
    )
    return checks


# ── Local storage ─────────────────────────────────────────────────────────────

_LOCAL = "Local storage"


def local_storage_folders(namespace: str) -> list[str]:
    """Paths where a local storage folder for this project could exist."""
    paths = [LEGACY_LOCAL_FOLDER, LOCAL_FOLDER_TEMPLATE.format(namespace=namespace)]
    return list(dict.fromkeys(paths))


def check_local_storage(
    namespace: str,
    exists: Callable[[str], bool] | None = None,
) -> list[Check]:
    """Fail for each local storage folder that exists. Only tests existence."""
    exists = exists or (lambda path: Path(path).exists())
    checks = []
    for path in local_storage_folders(namespace):
        found = exists(path)
        checks.append(
            Check(
                _LOCAL,
                f"no folder {path}",
                not found,
                "folder exists; delete it (task 0.7)" if found else "absent",
            )
        )
    return checks


# ── Report ────────────────────────────────────────────────────────────────────


def format_report(checks: Sequence[Check], notes: dict[str, list[str]] | None = None) -> str:
    """Render one short table per store, then an overall result line."""
    notes = notes or {}
    lines: list[str] = []
    stores = list(dict.fromkeys(c.store for c in checks))
    for store in stores:
        rows = [c for c in checks if c.store == store]
        width = max(len(c.name) for c in rows)
        lines.append(store)
        for c in rows:
            lines.append(f"  {c.status:<5} {c.name:<{width}}  {c.detail}")
        for note in notes.get(store, []):
            lines.append(f"        ({note})")
        lines.append("")
    failed = [c for c in checks if not c.ok]
    if failed:
        lines.append(f"RESULT: FAIL ({len(failed)} of {len(checks)} checks failed)")
    else:
        lines.append(f"RESULT: PASS ({len(checks)} checks)")
    return "\n".join(lines)


async def run() -> int:
    settings = get_settings()
    schema = configured_schema()
    print(f"check_partition: namespace {settings.project_namespace}, schema {schema} (read-only)")
    print()
    postgres_checks, postgres_notes = await check_postgres(schema)
    checks = [
        *postgres_checks,
        *check_storage(settings),
        *check_local_storage(settings.project_namespace),
    ]
    print(format_report(checks, {_POSTGRES: postgres_notes}))
    return 0 if all(c.ok for c in checks) else 1


def main() -> int:
    try:
        return asyncio.run(run())
    except Exception as exc:  # configuration error: report the type, never a value
        print(f"check_partition could not run: {type(exc).__name__}")
        print("RESULT: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
