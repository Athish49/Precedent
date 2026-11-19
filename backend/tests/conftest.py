import os

import pytest
from fastapi.testclient import TestClient

# Placeholder storage settings. They satisfy the required-settings check and
# point nowhere: no test may reach a real bucket (see ``_in_memory_storage``).
STORAGE_ENV: dict[str, str] = {
    "OBJECT_STORAGE_ENDPOINT": "https://storage.invalid",
    "OBJECT_STORAGE_BUCKET": "test-bucket",
    "OBJECT_STORAGE_ACCESS_KEY": "test-access-key",
    "OBJECT_STORAGE_SECRET_KEY": "test-secret-key",
}

_DATABASE_URL = (
    "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require"
)

# ``app.db.base`` reads the project schema from settings when it is imported,
# so the required settings must exist before the first ``app`` import below,
# not only inside the per-test fixture. Real environment variables win over
# ``.env``, so these placeholders also keep the developer's real database URL
# out of the test process. Values already set by CI are left alone.
for _name, _value in {
    "DATABASE_URL": _DATABASE_URL,
    "ANTHROPIC_API_KEY": "sk-ant-test",
    **STORAGE_ENV,
}.items():
    os.environ.setdefault(_name, _value)

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from tests.fake_llm import FakeLLMGateway  # noqa: E402
from tests.in_memory_storage import InMemoryStorage  # noqa: E402

# Every module that binds ``get_storage`` by name. A module that does
# ``from app.core.storage import get_storage`` at import time must be listed
# here so the autouse fixture below can replace its reference.
_GET_STORAGE_TARGETS = (
    "app.core.storage.get_storage",
    "app.services.repository.service.get_storage",
    "app.services.document_processing.ingest.get_storage",
)


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure required env vars are always present and settings cache is clean."""
    monkeypatch.setenv("DATABASE_URL", _DATABASE_URL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    for name, value in STORAGE_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _in_memory_storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryStorage:
    """Give every test an in-memory storage double instead of the cloud backend.

    There is no local storage backend, so application code that stores a file
    would otherwise build a real S3 client. This fixture replaces the
    ``get_storage`` factory wherever the application looks it up, and makes
    ``boto3.client`` fail loudly so nothing can reach the network by accident.
    Tests of the S3 backend itself patch ``boto3.client`` with their own mock.
    """
    double = InMemoryStorage()
    for target in _GET_STORAGE_TARGETS:
        monkeypatch.setattr(target, lambda _settings=None: double)

    def _no_real_client(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "Tests must not create a real boto3 client; use the `storage` fixture "
            "or patch boto3.client with a mock."
        )

    monkeypatch.setattr("boto3.client", _no_real_client)
    return double


@pytest.fixture
def storage(_in_memory_storage: InMemoryStorage) -> InMemoryStorage:
    """The in-memory storage double the application is using in this test."""
    return _in_memory_storage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_llm() -> FakeLLMGateway:
    """Return a pre-configured :class:`FakeLLMGateway` instance.

    Tests that need specific responses should configure the gateway directly::

        fake = fake_llm  # from fixture
        fake._structured["my_task"] = MyModel(...)
    """
    return FakeLLMGateway()
