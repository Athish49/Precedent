from fastapi.testclient import TestClient

from app.main import app


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
