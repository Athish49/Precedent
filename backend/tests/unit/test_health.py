from fastapi.testclient import TestClient

from app.main import app
from tests.in_memory_storage import InMemoryStorage


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "db" in body
    assert "embedding_model" in body
    assert "storage" in body
    assert isinstance(body["db"], bool)
    assert isinstance(body["embedding_model"], bool)
    assert isinstance(body["storage"], bool)


def test_health_storage_uses_configured_backend(storage: InMemoryStorage) -> None:
    """The storage probe goes through the storage factory and writes no file."""
    response = TestClient(app).get("/api/health")
    assert response.json()["storage"] is True
    assert storage.get("__health_check__") == b"ok"


def test_health_reports_schema_name() -> None:
    from app.core.config import get_settings

    body = TestClient(app).get("/api/health").json()
    assert body["db_schema"] == get_settings().db_schema
    assert body["db_schema"] != "public"
    # No database in unit tests: the schema cannot be confirmed.
    assert body["db"] is False
    assert body["db_schema_exists"] is False


def _fake_session_factory(schema_found: bool):  # type: ignore[no-untyped-def]
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = (1,) if schema_found else None
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return session, lambda: (lambda: context)


def test_health_reports_schema_exists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    session, get_factory = _fake_session_factory(schema_found=True)
    monkeypatch.setattr("app.db.base.get_session_factory", get_factory)

    body = TestClient(app).get("/api/health").json()

    assert body["db"] is True
    assert body["db_schema_exists"] is True
    schema = get_settings().db_schema
    assert session.execute.call_args.args[1] == {"schema": schema}


def test_health_reports_schema_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _session, get_factory = _fake_session_factory(schema_found=False)
    monkeypatch.setattr("app.db.base.get_session_factory", get_factory)

    body = TestClient(app).get("/api/health").json()

    assert body["db"] is True
    assert body["db_schema_exists"] is False
