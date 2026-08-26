import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.fake_llm import FakeLLMGateway


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure required env vars are always present and settings cache is clean."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


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
