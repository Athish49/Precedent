"""Configuration for the seed test suite (``pytest seed/tests`` from ``backend/``).

This suite is separate from the application suite in ``backend/tests`` and
does not load that folder's conftest.
"""

from __future__ import annotations

import pytest

# Placeholders, so seed tests never read real credentials from backend/.env and
# can never reach the remote database or bucket. Environment variables take
# priority over the .env file in the application settings.
_PLACEHOLDER_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:pass@db.invalid/testdb",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "PROJECT_NAMESPACE": "precedent",
    "OBJECT_STORAGE_ENDPOINT": "https://storage.invalid",
    "OBJECT_STORAGE_BUCKET": "test-bucket",
    "OBJECT_STORAGE_ACCESS_KEY": "test-access-key",
    "OBJECT_STORAGE_SECRET_KEY": "test-secret-key",
}


@pytest.fixture(autouse=True)
def _seed_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _PLACEHOLDER_ENV.items():
        monkeypatch.setenv(name, value)
    try:
        from app.core.config import get_settings
    except Exception:  # settings module unavailable: nothing cached to clear
        yield
        return
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """An empty seed suite is not a failure.

    pytest exits with status 5 when it collects no tests. The folder starts
    empty and CI runs it whenever it exists, so that case exits 0 here.
    Collection errors and test failures keep their own status.
    """
    if exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK
