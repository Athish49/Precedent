"""Unit tests for the Documents API (task 3.3).

Route tests only: no real database, no real Extend/network. The session
dependency (`_get_session`) is overridden with a fake session whose
``execute`` returns canned results in call order; `create_contract` /
`run_ingest` / `get_session_factory` are patched directly so the ingest
orchestrator (task 3.1, tested in ``test_dp_ingest.py``) is never actually
invoked from here.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.api.routes import documents as documents_route
from app.api.routes.documents import _get_session
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

_PDF_BYTES = b"%PDF-1.4 fake pdf content"


# ---------------------------------------------------------------------------
# Fake session plumbing
# ---------------------------------------------------------------------------


class _FakeResult:
    """Stands in for a SQLAlchemy ``Result``: supports the handful of
    accessors the route and the repositories it calls actually use.
    """

    def __init__(self, scalar=None, rows: list | None = None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalars(self):
        m = MagicMock()
        m.all.return_value = self._rows
        m.first.return_value = self._rows[0] if self._rows else None
        return m


class _FakeSession:
    """A minimal async session: ``execute`` pops the next canned
    ``_FakeResult`` off a queue, in the exact order the route (and the
    repository functions it calls) issue queries. ``commit``/``add`` are
    no-ops recorded for assertions.
    """

    def __init__(self, results: list[_FakeResult]):
        self._results = list(results)
        self.committed = 0
        self.executed_statements: list = []
        self.added: list = []

    async def execute(self, stmt, *args, **kwargs):
        self.executed_statements.append(stmt)
        if not self._results:
            raise AssertionError("no more canned results for session.execute()")
        return self._results.pop(0)

    async def commit(self):
        self.committed += 1

    def add(self, obj):
        self.added.append(obj)


def _override_session(session: _FakeSession):
    async def _fake_get_session():
        yield session

    app.dependency_overrides[_get_session] = _fake_get_session


def setup_function() -> None:
    app.dependency_overrides.pop(_get_session, None)


def teardown_function() -> None:
    app.dependency_overrides.pop(_get_session, None)


_UNKNOWN_ID = str(uuid.uuid4())


def _not_found_session() -> _FakeSession:
    return _FakeSession([_FakeResult(scalar=None)])


# ---------------------------------------------------------------------------
# POST /api/documents
# ---------------------------------------------------------------------------


def test_upload_invalid_paper_origin() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "bad"},
        files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_paper_origin"


def test_upload_invalid_party_role() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "party_role": "partner"},
        files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_party_role"


def test_upload_invalid_context_json() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "context": "{not valid json"},
        files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context"


def test_upload_context_must_be_json_object() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own", "context": "[1, 2, 3]"},
        files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context"


def test_upload_invalid_contract_type() -> None:
    _override_session(_FakeSession([]))
    with patch(
        "app.api.routes.documents.validate_contract_type",
        new=AsyncMock(
            side_effect=AppError(400, "invalid_contract_type", "contract_type must be one of [...]")
        ),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own", "contract_type": "not_a_real_type"},
            files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_contract_type"


def test_upload_unsupported_format() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own"},
        files={"file": ("contract.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_format"


def test_upload_empty_file() -> None:
    _override_session(_FakeSession([]))
    response = client.post(
        "/api/documents",
        data={"paper_origin": "own"},
        files={"file": ("contract.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_file"


def test_upload_file_too_large() -> None:
    _override_session(_FakeSession([]))
    with patch(
        "app.api.routes.documents.validate_upload",
        side_effect=AppError(413, "file_too_large", "File exceeds the 25 MB limit."),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own"},
            files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_upload_duplicate_file_without_force() -> None:
    _override_session(_FakeSession([]))
    existing_id = uuid.uuid4()
    with (
        patch(
            "app.api.routes.documents.create_contract",
            new=AsyncMock(
                side_effect=AppError(
                    409,
                    "duplicate_file",
                    "A contract with this file already exists.",
                    {"existing_contract_id": str(existing_id)},
                )
            ),
        ),
        patch("app.api.routes.documents.get_session_factory"),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own"},
            files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
        )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "duplicate_file"
    assert body["error"]["detail"] == {"existing_contract_id": str(existing_id)}


def test_upload_accepted_202() -> None:
    _override_session(_FakeSession([]))
    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    with (
        patch(
            "app.api.routes.documents.create_contract",
            new=AsyncMock(return_value=(contract_id, version_id)),
        ),
        patch("app.api.routes.documents.run_ingest", new=AsyncMock()),
        patch("app.api.routes.documents.get_session_factory", return_value=MagicMock()),
    ):
        response = client.post(
            "/api/documents",
            data={"paper_origin": "own"},
            files={"file": ("contract.pdf", _PDF_BYTES, "application/pdf")},
        )
    assert response.status_code == 202
    body = response.json()
    assert body == {
        "contract_id": str(contract_id),
        "version_id": str(version_id),
        "status": "processing",
    }


# ---------------------------------------------------------------------------
# GET /api/documents/{id}
# ---------------------------------------------------------------------------


def test_get_document_not_found() -> None:
    _override_session(_not_found_session())
    response = client.get(f"/api/documents/{_UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_document_processing_has_empty_lists() -> None:
    contract_id = uuid.uuid4()
    contract = SimpleNamespace(
        id=contract_id,
        title="contract.pdf",
        original_filename="contract.pdf",
        status="processing",
        status_reason=None,
        paper_origin="own",
        source_format="pdf",
        contract_type=None,
        contract_type_source=None,
        party_role=None,
        context=None,
        counterparty_id=None,
        current_version_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = _FakeSession([_FakeResult(scalar=contract)])
    _override_session(session)

    response = client.get(f"/api/documents/{contract_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["parties"] == []
    assert body["signatories"] == []
    assert body["fields"] == []
    assert body["metadata"] == {}
    assert body["warnings"] == []


def test_get_document_ready_full_shape() -> None:
    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    party_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract_party_id = uuid.uuid4()

    contract = SimpleNamespace(
        id=contract_id,
        title="MSA",
        original_filename="contract.pdf",
        status="ready",
        status_reason=None,
        paper_origin="own",
        source_format="pdf",
        contract_type="saas_msa",
        contract_type_source="extracted",
        party_role="vendor",
        context={"region": "us"},
        counterparty_id=party_id,
        current_version_id=version_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    contract_party = SimpleNamespace(
        role="counterparty",
        role_label="Customer",
        entity_type="corporation",
        jurisdiction="Delaware",
        address="123 Main St",
    )
    party = SimpleNamespace(id=party_id, display_name="Acme Corp")
    signatory = SimpleNamespace(
        printed_name="Jane Doe",
        title="CEO",
        is_signed=True,
        signed_date=date(2026, 1, 12),
    )
    field_row = SimpleNamespace(
        field_key="governing_law",
        value="Delaware",
        source="extract",
        confidence="high",
        quote="governed by Delaware law",
        page=7,
        char_start=100,
        char_end=130,
        clause_id=clause_id,
    )
    metadata_row = SimpleNamespace(
        effective_date=date(2026, 1, 12),
        expiry_date=date(2029, 1, 12),
        expiry_is_derived=True,
        initial_term_months=36,
        auto_renewal=False,
        renewal_term_months=12,
        renewal_notice_days=30,
        governing_law="Delaware",
        dispute_resolution="arbitration",
        total_value_amount=100000,
        currency="USD",
        liability_cap_amount=50000,
        liability_cap_basis="fees_paid",
        payment_terms_days=30,
        termination_for_convenience=True,
        termination_notice_days=60,
    )
    ingest_run = SimpleNamespace(warnings=["low_anchor_rate"])

    session = _FakeSession(
        [
            _FakeResult(scalar=contract),  # contract row
            _FakeResult(scalar=9),  # page_count
            _FakeResult(rows=[(contract_party, party)]),  # parties
            _FakeResult(rows=[(signatory, "Acme Corp")]),  # signatories
            _FakeResult(rows=[field_row]),  # field_repo.values_in_force's own execute
            _FakeResult(scalar=metadata_row),  # contract_metadata
            _FakeResult(rows=[ingest_run]),  # ingest_repo.latest_run's own execute
        ]
    )
    _override_session(session)

    response = client.get(f"/api/documents/{contract_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["page_count"] == 9
    assert body["parties"] == [
        {
            "party_id": str(party_id),
            "name": "Acme Corp",
            "role": "counterparty",
            "role_label": "Customer",
            "entity_type": "corporation",
            "jurisdiction": "Delaware",
            "address": "123 Main St",
        }
    ]
    assert body["signatories"][0]["printed_name"] == "Jane Doe"
    assert body["signatories"][0]["party_name"] == "Acme Corp"
    assert body["fields"][0]["field_key"] == "governing_law"
    assert body["fields"][0]["clause_id"] == str(clause_id)
    assert body["metadata"]["governing_law"] == "Delaware"
    assert body["metadata"]["expiry_is_derived"] is True
    assert body["warnings"] == ["low_anchor_rate"]


# ---------------------------------------------------------------------------
# GET /api/documents/{id}/clauses
# ---------------------------------------------------------------------------


def test_get_clauses_not_found() -> None:
    _override_session(_not_found_session())
    response = client.get(f"/api/documents/{_UNKNOWN_ID}/clauses")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_clauses_returns_uuid_ids_through_clause_repo() -> None:
    contract_id = uuid.uuid4()
    clause_row_id = uuid.uuid4()
    clause_key = uuid.uuid4()
    session = _FakeSession([_FakeResult(scalar=contract_id)])
    _override_session(session)

    clause_row = SimpleNamespace(
        id=clause_row_id,
        clause_key=clause_key,
        ordinal=4,
        level=1,
        parent_id=None,
        section_number="6",
        title="Limitation of Liability",
        heading_text="6. LIMITATION OF LIABILITY",
        clause_type="limitation_of_liability",
        type_source="extract",
        issue_keys=None,
        text="Neither party shall be liable...",
        char_start=5120,
        char_end=6480,
        page_start=3,
        page_end=3,
    )

    with patch(
        "app.api.routes.documents.clause_repo.get_clauses_for_contract",
        new=AsyncMock(return_value=[clause_row]),
    ) as mocked:
        response = client.get(f"/api/documents/{contract_id}/clauses")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(clause_row_id)
    assert uuid.UUID(body[0]["id"])  # really is a UUID, not "c0004"
    assert body[0]["clause_key"] == str(clause_key)
    assert body[0]["issue_keys"] == []
    mocked.assert_awaited_once()
    _, kwargs = mocked.await_args
    assert kwargs["level"] == "top"


def test_get_clauses_level_all() -> None:
    contract_id = uuid.uuid4()
    session = _FakeSession([_FakeResult(scalar=contract_id)])
    _override_session(session)

    with patch(
        "app.api.routes.documents.clause_repo.get_clauses_for_contract",
        new=AsyncMock(return_value=[]),
    ) as mocked:
        response = client.get(f"/api/documents/{contract_id}/clauses?level=all")

    assert response.status_code == 200
    _, kwargs = mocked.await_args
    assert kwargs["level"] == "all"


def test_get_clauses_invalid_level_rejected() -> None:
    contract_id = uuid.uuid4()
    session = _FakeSession([_FakeResult(scalar=contract_id)])
    _override_session(session)

    response = client.get(f"/api/documents/{contract_id}/clauses?level=2")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/documents/{id}/text
# ---------------------------------------------------------------------------


def test_get_text_not_found() -> None:
    _override_session(_not_found_session())
    response = client.get(f"/api/documents/{_UNKNOWN_ID}/text")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_text_returns_canonical_text() -> None:
    contract_id = uuid.uuid4()
    session = _FakeSession([_FakeResult(scalar="This is the canonical text.")])
    _override_session(session)

    response = client.get(f"/api/documents/{contract_id}/text")
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_text"] == "This is the canonical text."


# ---------------------------------------------------------------------------
# POST /api/documents/{id}/reprocess
# ---------------------------------------------------------------------------


def test_reprocess_not_found() -> None:
    _override_session(_not_found_session())
    response = client.post(f"/api/documents/{_UNKNOWN_ID}/reprocess")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def _reprocess_contract(contract_id: uuid.UUID, version_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=contract_id, current_version_id=version_id, status="ready", status_reason=None)


def test_reprocess_returns_409_when_flag_exists() -> None:
    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    contract = _reprocess_contract(contract_id, version_id)
    flag_id = uuid.uuid4()

    session = _FakeSession(
        [
            _FakeResult(scalar=contract),  # contract lookup
            _FakeResult(scalar=flag_id),  # has_flag
            _FakeResult(scalar=None),  # has_redline
        ]
    )
    _override_session(session)

    response = client.post(f"/api/documents/{contract_id}/reprocess")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "has_analysis"


def test_reprocess_force_discards_analysis_and_returns_202() -> None:
    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    contract = _reprocess_contract(contract_id, version_id)
    flag_id = uuid.uuid4()

    session = _FakeSession(
        [
            _FakeResult(scalar=contract),  # contract lookup
            _FakeResult(scalar=flag_id),  # has_flag
            _FakeResult(scalar=None),  # has_redline
            _FakeResult(),  # delete flag rows
        ]
    )
    _override_session(session)

    with (
        patch("app.api.routes.documents.run_ingest", new=AsyncMock()),
        patch("app.api.routes.documents.get_session_factory", return_value=MagicMock()),
    ):
        response = client.post(f"/api/documents/{contract_id}/reprocess?force=true")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert contract.status == "processing"
    assert session.committed >= 1


def test_reprocess_no_existing_analysis_returns_202() -> None:
    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    contract = _reprocess_contract(contract_id, version_id)

    session = _FakeSession(
        [
            _FakeResult(scalar=contract),  # contract lookup
            _FakeResult(scalar=None),  # has_flag
            _FakeResult(scalar=None),  # has_redline
        ]
    )
    _override_session(session)

    with (
        patch("app.api.routes.documents.run_ingest", new=AsyncMock()),
        patch("app.api.routes.documents.get_session_factory", return_value=MagicMock()),
    ):
        response = client.post(f"/api/documents/{contract_id}/reprocess")

    assert response.status_code == 202
    assert contract.status == "processing"


# ---------------------------------------------------------------------------
# No old-pipeline imports (the task's own "Done when")
# ---------------------------------------------------------------------------


def test_route_file_has_no_legacy_imports() -> None:
    import pathlib

    source = (
        pathlib.Path(documents_route.__file__)
    ).read_text()
    forbidden = ["service", "parsers", "extraction", "segmentation", "clause_types"]
    for name in forbidden:
        pattern = rf"^\s*(import|from)\s+\S*\b{name}\b"
        assert not re.search(pattern, source, re.MULTILINE), f"documents.py imports {name!r}"
    assert "ProcessedContract" not in source
