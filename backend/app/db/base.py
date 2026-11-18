from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

# The database is shared with other projects, so every table and view of this
# project lives in its own Postgres schema (``Settings.db_schema``). The schema
# is set once here, on the shared metadata: models inherit it and must not set
# a schema of their own. Unqualified foreign-key strings such as
# ``"contract.id"`` resolve inside this schema.
#
# Generated SQL is therefore always schema-qualified. Nothing at runtime relies
# on the session ``search_path``: the connection goes through a pooled endpoint
# where a session-level ``SET`` does not reliably persist between transactions.
DB_SCHEMA: str = get_settings().db_schema


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)


def qualified(name: str) -> str:
    """Return *name* (a project table or view) qualified with the project schema.

    Hand-written SQL must use this instead of a bare object name, e.g.
    ``text(f"SELECT * FROM {qualified('v_portfolio_risk')}")``. Only pass
    literal object names: the result is interpolated into SQL text.
    """
    if not name.isidentifier():
        raise ValueError(f"{name!r} is not a plain SQL identifier")
    return f"{DB_SCHEMA}.{name}"


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB not initialized — call init_db() first (happens in app lifespan).")
    return _session_factory
