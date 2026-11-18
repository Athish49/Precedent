import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so Base.metadata includes all tables.
import app.db.models  # noqa: F401, E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# ── Project partitioning ──────────────────────────────────────────────────────
# The database is shared with other projects. Everything this project owns,
# including its Alembic history table, lives in the schema named by
# ``Settings.db_schema`` (validated there: a plain lower-case identifier that
# is never ``public``).
#
# Migration files do not name a schema in ``op.create_table`` and similar
# calls. Instead ``_run_migrations`` puts the project schema first on the
# search path for the duration of the migration transaction, so unqualified
# names are created in, and resolve to, the project schema. ``public`` stays on
# the path only so the shared ``vector`` extension's type and operator classes
# resolve. Hand-written SQL in migrations still names the schema explicitly.


def _include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Limit autogenerate reflection to the project schema.

    ``include_schemas=True`` makes Alembic look at every schema in the
    database. Without this filter it would propose dropping other projects'
    tables in ``public`` and elsewhere.
    """
    if type_ == "schema":
        return name == get_settings().db_schema
    return True


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        version_table_schema=get_settings().db_schema,
        include_schemas=True,
        include_name=_include_name,
        # One transaction for the whole run: the ``SET LOCAL`` below must cover
        # every migration. Do not turn this on.
        transaction_per_migration=False,
        **kwargs,
    )


def _run_migrations() -> None:
    """Run migrations inside one transaction scoped to the project schema.

    Order matters: the schema must exist before Alembic creates or reads its
    version table there, and both statements run inside the migration
    transaction. ``SET LOCAL`` lasts only until that transaction ends, so
    nothing leaks into a pooled connection; a session-level ``SET`` would not
    be reliable on the pooled endpoint.
    """
    schema = get_settings().db_schema
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        context.execute(f"SET LOCAL search_path TO {schema}, public")
        context.run_migrations()


def run_migrations_offline() -> None:
    _configure(
        url=get_settings().database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    _run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    _run_migrations()


async def run_migrations_online() -> None:
    url = get_settings().database_url
    connectable = create_async_engine(url, pool_pre_ping=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
