"""Database session helper for seed loaders.

Reads the application's settings, so it needs the same environment as the
application (``backend/.env``). ``app`` is imported inside the functions, so
importing this module needs no settings and opens no connection.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Where task 0.6 may put ``assert_namespace``. The first module that has it wins.
# The guard lives in ``app``; seed code imports it, never the reverse.
NAMESPACE_GUARD_NAME = "assert_namespace"
NAMESPACE_GUARD_MODULES: tuple[str, ...] = (
    "app.core.config",
    "app.core.namespace",
    "app.core.partition",
    "app.db.namespace",
)


def _find_namespace_guard() -> Callable[..., Any] | None:
    for module_name in NAMESPACE_GUARD_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name and module_name.startswith(exc.name):
                continue  # the candidate module itself does not exist
            raise
        guard = getattr(module, NAMESPACE_GUARD_NAME, None)
        if callable(guard):
            return guard
    return None


async def call_namespace_guard(session: AsyncSession) -> bool:
    """Call the application's ``assert_namespace`` guard if it exists.

    Returns ``True`` if a guard was found and passed, ``False`` if the
    application has no guard yet. Whatever the guard raises propagates.

    The guard may be sync or async. If it declares at least one parameter it is
    called with ``session``; otherwise it is called with no arguments.
    """
    guard = _find_namespace_guard()
    if guard is None:
        return False
    takes_argument = any(
        p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        for p in inspect.signature(guard).parameters.values()
    )
    result = guard(session) if takes_argument else guard()
    if inspect.isawaitable(result):
        await result
    return True


@asynccontextmanager
async def seed_session(*, dry_run: bool = False) -> AsyncIterator[AsyncSession]:
    """Open one database session for a seed loader.

    Uses ``database_url`` from the application settings. Before yielding it
    calls the namespace guard (when the application has one), so a loader
    cannot write outside the project schema.

    On a clean exit the session is committed, or rolled back when ``dry_run``
    is true. On an exception it is rolled back and the exception propagates.
    The engine is created for this call and disposed afterwards.
    """
    from app.core.config import get_settings

    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            try:
                await call_namespace_guard(session)
                yield session
            except BaseException:
                await session.rollback()
                raise
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await engine.dispose()
