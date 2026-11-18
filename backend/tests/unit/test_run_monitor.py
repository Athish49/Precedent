"""Cron entrypoint script (task 0.6): asserts the namespace guard runs first.

No connection: the session factory, ``init_db`` and the monitor pass are all
mocked. Only the ordering and presence of the ``assert_namespace`` call is
under test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import run_monitor as rm


class _FakeSessionCM:
    """Async context manager returning a fixed mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.mark.asyncio
async def test_main_calls_assert_namespace_before_run_monitor_and_commit() -> None:
    """The guard runs first, before the monitor pass and before the commit."""
    session = AsyncMock()
    calls: list[str] = []

    async def _fake_assert_namespace(s: object) -> str:
        assert s is session
        calls.append("assert_namespace")
        return "project_schema"

    async def _fake_run_monitor(s: object) -> MagicMock:
        assert s is session
        calls.append("run_monitor")
        return MagicMock(deadline_alerts=[], renewal_alerts=[])

    async def _fake_commit() -> None:
        calls.append("commit")

    session.commit = _fake_commit

    with (
        patch.object(rm, "get_settings", return_value=MagicMock(env="test", database_url="sqlite://")),
        patch.object(rm, "configure_logging"),
        patch.object(rm, "init_db"),
        patch.object(rm, "get_session_factory", return_value=lambda: _FakeSessionCM(session)),
        patch.object(rm, "assert_namespace", side_effect=_fake_assert_namespace) as mock_guard,
        patch.object(rm, "run_monitor", side_effect=_fake_run_monitor) as mock_run,
    ):
        await rm.main()

    mock_guard.assert_awaited_once_with(session)
    mock_run.assert_awaited_once_with(session)
    assert calls == ["assert_namespace", "run_monitor", "commit"]


@pytest.mark.asyncio
async def test_main_does_not_run_monitor_when_guard_raises() -> None:
    """A failed namespace check must stop the script before any write."""
    from app.core.namespace import NamespaceError

    session = AsyncMock()

    async def _raise(s: object) -> str:
        raise NamespaceError("The project schema is not set.")

    with (
        patch.object(rm, "get_settings", return_value=MagicMock(env="test", database_url="sqlite://")),
        patch.object(rm, "configure_logging"),
        patch.object(rm, "init_db"),
        patch.object(rm, "get_session_factory", return_value=lambda: _FakeSessionCM(session)),
        patch.object(rm, "assert_namespace", side_effect=_raise),
        patch.object(rm, "run_monitor", new_callable=AsyncMock) as mock_run,
    ):
        with pytest.raises(NamespaceError):
            await rm.main()

    mock_run.assert_not_called()
    session.commit.assert_not_called()
