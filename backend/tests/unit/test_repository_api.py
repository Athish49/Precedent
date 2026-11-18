"""Unit tests for repository versioning API endpoints (T-032).

All tests use dependency overrides and mocks — no real DB or file processing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.api.routes.repository import _get_session
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
    """Configure mock_session so scalar_one_or_none() returns None."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)


def _make_version_obj(contract_id: uuid.UUID, version_number: int = 1) -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.contract_id = contract_id
    v.version_number = version_number
    v.parent_version_id = None
    v.object_key = f"contracts/{contract_id}/versions/{version_number}/file.pdf"
    v.canonical_text = "Sample text"
    v.relation = "version"
    v.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return v


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_get_versions_not_found() -> None:
    """GET /api/repository/contracts/{id}/versions for unknown contract returns 404."""
    with patch(
        "app.api.routes.repository.list_versions",
        side_effect=AppError(404, "not_found", "Contract not found"),
    ):
        response = client.get(f"/api/repository/contracts/{_UNKNOWN_ID}/versions")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


def test_get_versions_empty() -> None:
    """GET /api/repository/contracts/{id}/versions returns empty list when no versions."""
    contract_id = uuid.uuid4()
    with patch(
        "app.api.routes.repository.list_versions",
        return_value=[],
    ):
        response = client.get(f"/api/repository/contracts/{contract_id}/versions")

    assert response.status_code == 200
    assert response.json() == []


def test_create_version_invalid_relation() -> None:
    """POST /api/repository/contracts/{id}/versions with invalid relation returns 400."""
    contract_id = uuid.uuid4()
    response = client.post(
        f"/api/repository/contracts/{contract_id}/versions",
        data={"relation": "bad"},
        files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_relation"


# ── T-034 tests ───────────────────────────────────────────────────────────────


def test_list_contracts_returns_200() -> None:
    """GET /api/repository/contracts returns 200 with empty list."""
    with patch(
        "app.api.routes.repository.repo_list_contracts",
        new=AsyncMock(return_value=([], 0)),
    ):
        resp = client.get("/api/repository/contracts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_search_fulltext_returns_200() -> None:
    """GET /api/repository/search?q=test returns 200 for fulltext type."""
    with patch(
        "app.api.routes.repository.full_text_search",
        new=AsyncMock(return_value=([], 0)),
    ):
        resp = client.get("/api/repository/search?q=test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_search_faceted_returns_200() -> None:
    """GET /api/repository/search?type=faceted returns 200."""
    with patch(
        "app.api.routes.repository.faceted_search",
        new=AsyncMock(return_value=([], 0)),
    ):
        resp = client.get("/api/repository/search?type=faceted")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_precedent_search_requires_query() -> None:
    """GET /api/repository/precedent-search without query param returns 422."""
    resp = client.get("/api/repository/precedent-search")
    assert resp.status_code == 422


def test_redline_history_returns_empty() -> None:
    """GET /api/repository/contracts/{id}/redline-history returns 200 empty list."""
    contract_id = uuid.uuid4()
    resp = client.get(f"/api/repository/contracts/{contract_id}/redline-history")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Task 4.1: PATCH /repository/contracts/{id} ──────────────────────────────


def _make_contract_obj(
    contract_id: uuid.UUID,
    contract_type: str | None = "saas_msa",
    party_role: str | None = "vendor",
    context: dict | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = contract_id
    c.contract_type = contract_type
    c.party_role = party_role
    c.context = context
    return c


def test_patch_contract_not_found() -> None:
    """PATCH /api/repository/contracts/{id} for an unknown contract returns 404."""
    contract_id = uuid.uuid4()
    with patch(
        "app.api.routes.repository.repo_update_contract",
        new=AsyncMock(return_value=None),
    ):
        resp = client.patch(
            f"/api/repository/contracts/{contract_id}",
            json={"party_role": "vendor"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "contract_not_found"


def test_patch_contract_invalid_contract_type() -> None:
    """PATCH with an invalid contract_type returns 400 and never touches the repo."""
    contract_id = uuid.uuid4()
    with (
        patch(
            "app.api.routes.repository.validate_contract_type",
            new=AsyncMock(side_effect=AppError(400, "invalid_contract_type", "bad type")),
        ),
        patch("app.api.routes.repository.repo_update_contract", new=AsyncMock()) as repo_update,
    ):
        resp = client.patch(
            f"/api/repository/contracts/{contract_id}",
            json={"contract_type": "not_a_real_type"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_contract_type"
    repo_update.assert_not_called()


def test_patch_contract_invalid_party_role() -> None:
    """PATCH with an invalid party_role returns 400."""
    contract_id = uuid.uuid4()
    resp = client.patch(
        f"/api/repository/contracts/{contract_id}",
        json={"party_role": "partner"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_party_role"


def test_patch_contract_invalid_context_value() -> None:
    """PATCH with an invalid context value returns 400."""
    contract_id = uuid.uuid4()
    with patch(
        "app.api.routes.repository.validate_context",
        new=AsyncMock(
            side_effect=AppError(400, "invalid_context_value", "region value not allowed")
        ),
    ):
        resp = client.patch(
            f"/api/repository/contracts/{contract_id}",
            json={"context": {"region": "mars"}},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_context_value"


def test_patch_contract_success() -> None:
    """PATCH with valid fields updates the contract and returns 200."""
    contract_id = uuid.uuid4()
    updated = _make_contract_obj(
        contract_id, contract_type="dpa", party_role="vendor", context={"region": "eu"}
    )
    with (
        patch("app.api.routes.repository.validate_contract_type", new=AsyncMock()),
        patch("app.api.routes.repository.validate_context", new=AsyncMock()),
        patch(
            "app.api.routes.repository.repo_update_contract",
            new=AsyncMock(return_value=updated),
        ) as repo_update,
    ):
        resp = client.patch(
            f"/api/repository/contracts/{contract_id}",
            json={"contract_type": "dpa", "party_role": "vendor", "context": {"region": "eu"}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contract_type"] == "dpa"
    assert body["party_role"] == "vendor"
    assert body["context"] == {"region": "eu"}
    # exclude_unset: only the three supplied fields are passed through.
    assert repo_update.call_args.kwargs == {
        "contract_type": "dpa",
        "party_role": "vendor",
        "context": {"region": "eu"},
    }


def test_patch_contract_partial_update_only_sends_supplied_fields() -> None:
    """PATCH with only one field set must not pass the other two to the repo
    (exclude_unset semantics: omitted fields stay unchanged)."""
    contract_id = uuid.uuid4()
    updated = _make_contract_obj(contract_id, contract_type="dpa")
    with (
        patch("app.api.routes.repository.validate_contract_type", new=AsyncMock()),
        patch(
            "app.api.routes.repository.repo_update_contract",
            new=AsyncMock(return_value=updated),
        ) as repo_update,
    ):
        resp = client.patch(
            f"/api/repository/contracts/{contract_id}",
            json={"contract_type": "dpa"},
        )
    assert resp.status_code == 200
    assert repo_update.call_args.kwargs == {"contract_type": "dpa"}
