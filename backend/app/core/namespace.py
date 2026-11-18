"""Project namespace: the fixed object list and the write guard.

The database is shared with other projects. Everything this project owns
lives in the Postgres schema named by ``Settings.db_schema`` and never in the
shared default schema. This module holds what the partition tooling shares:

* the fixed list of objects that migrations ``001`` to ``009`` created, which
  ``scripts/move_to_schema.py`` moves and ``scripts/check_partition.py``
  looks for;
* :func:`project_tables` and :func:`project_views`, the full current list
  (legacy list plus every model on ``Base.metadata``);
* small read-only catalogue helpers;
* :func:`assert_namespace`, the guard every script that writes data calls
  first.

Extending the list in later tasks:

* a new **table** needs nothing here once its model is imported by
  ``app.db.models``: :func:`project_tables` picks it up from the metadata;
* a new **view** (views have no model) is appended to :data:`PROJECT_VIEWS`.

``LEGACY_TABLES`` and ``LEGACY_VIEWS`` are frozen: they describe the one-off
move of task 0.5 and must not grow.

The schema name is never written here; it always comes from settings.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, NamedTuple

from sqlalchemy import bindparam, text

from app.core.config import get_settings

# The schema every Postgres database starts with, shared by all projects.
SHARED_SCHEMA = "public"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

# ── Fixed list: what migrations 001–009 created ───────────────────────────────

# Alembic's history table. It moves with the application tables so the
# migration history stays with the project.
VERSION_TABLE = "alembic_version"

# The 16 application tables.
LEGACY_APP_TABLES: tuple[str, ...] = (
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
)

# The 17 tables the move handles: the application tables and the version table.
LEGACY_TABLES: tuple[str, ...] = (*LEGACY_APP_TABLES, VERSION_TABLE)

# The 6 views (migrations 004 and 009).
LEGACY_VIEWS: tuple[str, ...] = (
    "counterparty_pattern",
    "v_contract_intelligence",
    "v_contract_value",
    "v_portfolio_risk",
    "v_renewal_dashboard",
    "v_tabular_review",
)

# Every view this project owns. Later migrations that add a view append here.
PROJECT_VIEWS: tuple[str, ...] = LEGACY_VIEWS

# pg_class.relkind values for the two kinds of object this project owns.
KIND_TABLE = "r"
KIND_VIEW = "v"


class NamespaceError(RuntimeError):
    """Raised when the project schema is unset, shared, invalid or missing."""


class Relation(NamedTuple):
    """One table or view as read from the catalogue."""

    schema: str
    name: str
    kind: str  # KIND_TABLE or KIND_VIEW


def quote_ident(name: str) -> str:
    """Return *name* as a double-quoted SQL identifier.

    Only plain lower-case identifiers are accepted, so the result is safe to
    interpolate into SQL text. Anything else raises ``ValueError``.
    """
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"{name!r} is not a plain SQL identifier")
    return f'"{name}"'


def qualified_ident(schema: str, name: str) -> str:
    """Return ``"schema"."name"`` with both parts quoted."""
    return f"{quote_ident(schema)}.{quote_ident(name)}"


def project_tables() -> tuple[str, ...]:
    """Bare names of every table this project owns, sorted.

    The fixed legacy list plus every table registered on ``Base.metadata``,
    so tables added by later migrations are covered without editing this file.
    """
    import app.db.models  # noqa: F401, PLC0415  (registers every model)
    from app.db.base import Base  # noqa: PLC0415

    names = set(LEGACY_TABLES) | {table.name for table in Base.metadata.tables.values()}
    return tuple(sorted(names))


def project_views() -> tuple[str, ...]:
    """Bare names of every view this project owns, sorted."""
    return tuple(sorted(set(PROJECT_VIEWS)))


def project_object_names() -> tuple[str, ...]:
    """Bare names of every table and view this project owns, sorted."""
    return tuple(sorted({*project_tables(), *project_views()}))


def configured_schema() -> str:
    """Return the project schema from settings, or raise :class:`NamespaceError`.

    Settings already validate the value at startup. It is checked again here
    because a settings object can be built or patched without validation, and
    this is the last stop before a script writes.
    """
    schema = getattr(get_settings(), "db_schema", None)
    if not isinstance(schema, str) or not schema.strip():
        raise NamespaceError(
            "The project schema is not set. Set PROJECT_NAMESPACE (or DB_SCHEMA); "
            "refusing to write to a shared database without a namespace."
        )
    schema = schema.strip()
    if schema.lower() == SHARED_SCHEMA:
        raise NamespaceError(
            f"The project schema must not be {SHARED_SCHEMA!r}: that schema is shared "
            "with other projects."
        )
    if not _IDENTIFIER.fullmatch(schema):
        raise NamespaceError(f"The project schema {schema!r} is not a plain SQL identifier.")
    return schema


# ── Read-only catalogue helpers ───────────────────────────────────────────────
# ``conn`` is anything with an awaitable ``execute``: an ``AsyncSession`` or an
# ``AsyncConnection``. All statements are plain SELECTs on system catalogues.

_SCHEMA_EXISTS = text("SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = :schema")

_RELATIONS = text(
    "SELECT n.nspname, c.relname, c.relkind "
    "FROM pg_catalog.pg_class c "
    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname IN :schemas AND c.relkind IN ('r', 'p', 'v', 'm') "
    "ORDER BY n.nspname, c.relname"
).bindparams(bindparam("schemas", expanding=True))


async def schema_exists(conn: Any, schema: str) -> bool:
    """Return whether *schema* exists in the connected database."""
    result = await conn.execute(_SCHEMA_EXISTS, {"schema": schema})
    return result.first() is not None


async def fetch_relations(conn: Any, schemas: Iterable[str]) -> list[Relation]:
    """Return every table and view in *schemas*.

    Partitioned tables are reported as tables and materialised views as views.
    """
    result = await conn.execute(_RELATIONS, {"schemas": sorted(set(schemas))})
    relations = []
    for schema, name, kind in result.all():
        kind = str(kind)
        normalised = KIND_TABLE if kind in ("r", "p") else KIND_VIEW
        relations.append(Relation(str(schema), str(name), normalised))
    return relations


async def begin_read_only(conn: Any) -> None:
    """Make the transaction that *conn* is about to open read-only.

    Must be the first statement on the connection's transaction. The database
    then rejects every write for the rest of that transaction, so a bug in a
    checking script cannot change anything. The setting is transaction-scoped
    and leaves no state behind on a pooled connection.

    Raises:
        RuntimeError: if the database does not confirm the read-only mode.
    """
    await conn.execute(text("SET TRANSACTION READ ONLY"))
    result = await conn.execute(text("SHOW transaction_read_only"))
    row = result.first()
    if row is None or str(row[0]).lower() != "on":
        raise RuntimeError("Could not open a read-only transaction; refusing to continue.")


def redact_connection_details(message: str, database_url: str) -> str:
    """Return *message* with the host, user, password and database name removed.

    Driver errors can quote parts of the connection string. Scripts print
    errors through this so no connection detail reaches a terminal or a log.
    """
    from sqlalchemy.engine import make_url  # noqa: PLC0415

    try:
        url = make_url(database_url)
    except Exception:
        return "database error (details withheld)"
    secrets = [database_url, url.password, url.host, url.username, url.database]
    for value in sorted({v for v in secrets if v}, key=len, reverse=True):
        message = message.replace(value, "***")
    return message


# ── Write guard ───────────────────────────────────────────────────────────────


async def assert_namespace(session: Any) -> str:
    """Raise unless writes will land in an existing, project-owned schema.

    Checks, in order, that the project schema is set, is not the shared
    default schema, is a plain identifier, and exists in the database that
    *session* is connected to. Returns the schema name.

    Call it first in every seed loader and every operational script that
    writes data. It only reads; it never creates the schema (migrations do).

    Raises:
        NamespaceError: on any failed check.
    """
    schema = configured_schema()
    if not await schema_exists(session, schema):
        raise NamespaceError(
            f"The project schema {schema!r} does not exist in this database. "
            "Run the migrations (or the schema move) before writing data."
        )
    return schema


__all__ = [
    "KIND_TABLE",
    "KIND_VIEW",
    "LEGACY_APP_TABLES",
    "LEGACY_TABLES",
    "LEGACY_VIEWS",
    "PROJECT_VIEWS",
    "SHARED_SCHEMA",
    "VERSION_TABLE",
    "NamespaceError",
    "Relation",
    "assert_namespace",
    "begin_read_only",
    "configured_schema",
    "fetch_relations",
    "project_object_names",
    "project_tables",
    "project_views",
    "quote_ident",
    "qualified_ident",
    "redact_connection_details",
    "schema_exists",
]
