"""Tests for the error envelope and AppError exception handler."""

import pytest
from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.main import app

# ---------------------------------------------------------------------------
# Register test-only routes directly on the app.
# These must be added before the TestClient is created.
# ---------------------------------------------------------------------------


@app.get("/_test/app-error")
async def _route_app_error() -> None:
    raise AppError(status_code=404, code="not_found", message="Contract not found")


@app.get("/_test/app-error-with-detail")
async def _route_app_error_with_detail() -> None:
    raise AppError(
        status_code=422,
        code="validation_error",
        message="Invalid field",
        detail={"field": "id"},
    )


@app.get("/_test/unhandled")
async def _route_unhandled() -> None:
    raise Exception("boom")  # noqa: TRY002


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def safe_client() -> TestClient:
    """TestClient that does NOT re-raise server-side exceptions."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_app_error_renders_envelope(safe_client: TestClient) -> None:
    response = safe_client.get("/_test/app-error")
    assert response.status_code == 404
    body = response.json()
    assert body == {
        "error": {
            "code": "not_found",
            "message": "Contract not found",
            "detail": None,
        }
    }


def test_app_error_with_detail(safe_client: TestClient) -> None:
    response = safe_client.get("/_test/app-error-with-detail")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["detail"] == {"field": "id"}


def test_unhandled_exception_returns_500(safe_client: TestClient) -> None:
    response = safe_client.get("/_test/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
