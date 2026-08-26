"""Unit tests for S1 document API endpoints (T-025).

All tests use dependency overrides and mocks — no real DB or file processing.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.routes.documents import _get_session
from app.main import app

# ── Shared mock session setup ─────────────────────────────────────────────────

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

# ── Helpers ───────────────────────────────────────────────────────────────────

_UNKNOWN_ID = str(uuid.uuid4())


def _not_found_execute():
    """Configure mock_session so any .execute().scalar_one_or_none() returns None.

    The execute() coroutine must return a plain MagicMock (not AsyncMock) so that
    synchronous methods like scalar_one_or_none() return values directly instead of
    returning unawaited coroutines.
    """
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_upload_invalid_paper_origin() -> None:
    """POST /api/documents with an invalid paper_origin returns 400."""
    response = client.post(
        "/api/documents",
        data={"paper_origin": "bad"},
        files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_paper_origin"


def test_upload_unsupported_format() -> None:
    """POST /api/documents with an unsupported file format returns 400."""
    with patch(
        "app.api.routes.documents.process",
        side_effect=ValueError("Unsupported file format: 'contract.txt'"),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own"},
            files={"file": ("contract.txt", b"plain text content", "text/plain")},
        )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unsupported_format"


def test_get_document_not_found() -> None:
    """GET /api/documents/{id} for an unknown contract returns 404."""
    _not_found_execute()
    response = client.get(f"/api/documents/{_UNKNOWN_ID}")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


def test_get_clauses_not_found() -> None:
    """GET /api/documents/{id}/clauses for an unknown contract returns 404."""
    _not_found_execute()
    response = client.get(f"/api/documents/{_UNKNOWN_ID}/clauses")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


def test_get_text_not_found() -> None:
    """GET /api/documents/{id}/text for an unknown contract returns 404."""
    _not_found_execute()
    response = client.get(f"/api/documents/{_UNKNOWN_ID}/text")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
