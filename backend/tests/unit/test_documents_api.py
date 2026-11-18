"""Unit tests for S1 document API endpoints (T-025).

All tests use dependency overrides and mocks — no real DB or file processing.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.errors import AppError
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


# ── Task 4.1: contract type and context capture form fields ────────────────


def _patch_process_ok():
    """Patch process() to a trivial async stub so these tests only exercise
    the route's own validation, not the full pipeline."""
    from app.services.document_processing.extraction import ContractMetadataDTO
    from app.services.document_processing.service import ProcessedContract

    async def _fake_process(*args: object, **kwargs: object) -> ProcessedContract:
        # process(file_bytes, filename, paper_origin, session, contract_type=, party_role=, context=)
        paper_origin = args[2] if len(args) > 2 else "own"
        return ProcessedContract(
            contract_id=uuid.uuid4(),
            canonical_text="text",
            paper_origin=paper_origin,
            counterparty_id=None,
            contract_type=kwargs.get("contract_type"),
            party_role=kwargs.get("party_role"),
            context=kwargs.get("context"),
            clauses=[],
            metadata=ContractMetadataDTO.model_construct(),
        )

    return patch("app.api.routes.documents.process", side_effect=_fake_process)


def test_upload_invalid_party_role() -> None:
    """POST /api/documents with an invalid party_role returns 400."""
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "party_role": "partner"},
        files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_party_role"


def test_upload_invalid_context_json() -> None:
    """POST /api/documents with a malformed context JSON string returns 400."""
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "context": "{not valid json"},
        files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context"


def test_upload_context_must_be_json_object() -> None:
    """POST /api/documents with a context JSON array (not object) returns 400."""
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "context": "[1, 2, 3]"},
        files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context"


def test_upload_invalid_contract_type() -> None:
    """POST /api/documents with a contract_type not in agreement_type returns 400."""
    with patch(
        "app.api.routes.documents.validate_contract_type",
        new=AsyncMock(
            side_effect=AppError(400, "invalid_contract_type", "contract_type must be one of [...]")
        ),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own", "contract_type": "not_a_real_type"},
            files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_contract_type"


def test_upload_invalid_context_value() -> None:
    """POST /api/documents with a context value not in context_dimension returns 400."""
    with (
        patch("app.api.routes.documents.validate_contract_type", new=AsyncMock()),
        patch(
            "app.api.routes.documents.validate_context",
            new=AsyncMock(
                side_effect=AppError(
                    400, "invalid_context_value", "region value 'mars' is not one of [...]"
                )
            ),
        ),
    ):
        response = client.post(
            "/api/documents",
            data={
                "paper_origin": "own",
                "contract_type": "saas_msa",
                "context": '{"region": "mars"}',
            },
            files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context_value"


def test_upload_accepts_valid_optional_fields() -> None:
    """POST /api/documents with valid contract_type/party_role/context succeeds
    and passes them through to process()."""
    with (
        patch("app.api.routes.documents.validate_contract_type", new=AsyncMock()),
        patch("app.api.routes.documents.validate_context", new=AsyncMock()),
        _patch_process_ok(),
    ):
        response = client.post(
            "/api/documents",
            data={
                "paper_origin": "own",
                "contract_type": "saas_msa",
                "party_role": "vendor",
                "context": '{"region": "us"}',
            },
            files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["contract_type"] == "saas_msa"
    assert body["party_role"] == "vendor"
    assert body["context"] == {"region": "us"}


def test_upload_without_optional_fields_still_succeeds() -> None:
    """POST /api/documents without contract_type/party_role/context (the
    pre-task-4.1 shape) still works, with no validation calls made."""
    with (
        patch("app.api.routes.documents.validate_contract_type", new=AsyncMock()) as vct,
        patch("app.api.routes.documents.validate_context", new=AsyncMock()) as vc,
        _patch_process_ok(),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own"},
            files={"file": ("contract.pdf", b"%PDF-fake", "application/pdf")},
        )
    assert response.status_code == 201
    vct.assert_not_called()
    vc.assert_not_called()
