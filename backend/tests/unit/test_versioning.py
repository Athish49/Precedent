"""Unit tests for repository versioning service (T-032).

All DB access and storage are mocked — no real database or file I/O.
``store_version`` goes through task 3.1's ``extract_canonical_text``
(Extend Parse), so these tests drive it with ``FakeExtendClient`` fed a
real recorded fixture rather than mocking the old ``parsers.parse``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.db.models.contract import ContractVersion
from app.services.document_processing import ingest as dp_ingest
from app.services.repository.service import list_versions, store_version
from tests.fake_extend import FakeExtendClient

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"


def _load_raw_case(name: str) -> tuple[dict, dict]:
    """Load the raw extract.json / parse.json dicts for a fixture case, in
    the full response shape ``FakeExtendClient`` expects."""
    case_dir = _FIXTURES / name
    with open(case_dir / "extract.json") as f:
        extract = json.load(f)
    with open(case_dir / "parse.json") as f:
        parse = json.load(f)
    return extract, parse


def _fake_client() -> FakeExtendClient:
    extract_response, parse_response = _load_raw_case("msa_styled_docx")
    return FakeExtendClient(extract_response, parse_response)


def _docx_bytes() -> bytes:
    """A real, valid DOCX payload, so ``validate_upload`` accepts it."""
    return (_FIXTURES / "documents" / "msa_styled.docx").read_bytes()

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value) -> MagicMock:
    """Mock execute() result suitable for scalar_one_or_none() / scalar_one()."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    mock.scalar_one.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    """Mock execute() result suitable for scalars().all()."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _make_contract(contract_id: uuid.UUID | None = None) -> MagicMock:
    contract = MagicMock()
    contract.id = contract_id or uuid.uuid4()
    contract.current_version_id = None
    return contract


def _make_version(
    contract_id: uuid.UUID,
    version_number: int = 1,
    parent_version_id: uuid.UUID | None = None,
) -> MagicMock:
    v = MagicMock(spec=ContractVersion)
    v.id = uuid.uuid4()
    v.contract_id = contract_id
    v.version_number = version_number
    v.parent_version_id = parent_version_id
    v.object_key = f"contracts/{contract_id}/versions/{version_number}/file.pdf"
    v.canonical_text = "Sample text"
    v.relation = "version"
    return v


# ── store_version tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_version_increments_version_number() -> None:
    """First version gets version_number=1 when no prior versions exist."""
    contract_id = uuid.uuid4()
    contract = _make_contract(contract_id)

    session = _make_session()

    # execute calls in order:
    # 1. get_contract (scalar_one_or_none → contract)
    # 2. SELECT MAX(version_number) (scalar_one_or_none → None → max_ver=0)
    session.execute.side_effect = [
        _scalar_result(contract),  # get_contract
        _scalar_result(None),  # MAX(version_number)
    ]

    file_bytes = _docx_bytes()

    with (
        patch.object(dp_ingest, "get_extend_client", lambda settings=None: _fake_client()),
        patch("app.services.repository.service.get_storage") as mock_get_storage,
    ):
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        version = await store_version(session, contract_id, file_bytes, "file.docx", "version")

    assert version.version_number == 1
    assert version.parent_version_id is None
    assert version.contract_id == contract_id
    assert len(version.canonical_text) > 0
    assert version.file_sha256 is not None
    assert version.file_size_bytes == len(file_bytes)
    assert version.source_format == "docx"
    assert version.original_filename == "file.docx"
    mock_storage.put.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_version_links_parent() -> None:
    """Second version gets version_number=2 and links parent_version_id."""
    contract_id = uuid.uuid4()
    contract = _make_contract(contract_id)

    # existing version with version_number=1
    existing_version = _make_version(contract_id, version_number=1)

    session = _make_session()
    session.execute.side_effect = [
        _scalar_result(contract),  # get_contract
        _scalar_result(1),  # MAX(version_number) → max_ver=1
        _scalar_result(existing_version),  # get parent version
    ]

    file_bytes = _docx_bytes()

    with (
        patch.object(dp_ingest, "get_extend_client", lambda settings=None: _fake_client()),
        patch("app.services.repository.service.get_storage") as mock_get_storage,
    ):
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        version = await store_version(session, contract_id, file_bytes, "file.docx", "amendment")

    assert version.version_number == 2
    assert version.parent_version_id == existing_version.id
    assert version.relation == "amendment"
    assert len(version.canonical_text) > 0


@pytest.mark.asyncio
async def test_store_version_after_ingest_writes_version_number_two() -> None:
    """Numbering consequence (plan section 5.7 / 3.1): ingest writes the
    contract's version 1 row itself. The first "new version" uploaded
    through ``store_version`` for that contract must therefore come out as
    version_number=2, not 1. ``store_version``'s MAX(version_number)+1
    query already reads the real existing row, so no special-casing of "is
    this the very first version ever" is needed or present.
    """
    contract_id = uuid.uuid4()
    contract = _make_contract(contract_id)

    # Ingest (task 3.1) already created version 1 for this contract.
    ingest_version_1 = _make_version(contract_id, version_number=1)

    session = _make_session()
    session.execute.side_effect = [
        _scalar_result(contract),  # get_contract
        _scalar_result(1),  # MAX(version_number) -> 1 (ingest's version)
        _scalar_result(ingest_version_1),  # get parent version
    ]

    file_bytes = _docx_bytes()

    with (
        patch.object(dp_ingest, "get_extend_client", lambda settings=None: _fake_client()),
        patch("app.services.repository.service.get_storage") as mock_get_storage,
    ):
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        version = await store_version(session, contract_id, file_bytes, "file.docx", "version")

    assert version.version_number == 2
    assert version.parent_version_id == ingest_version_1.id


@pytest.mark.asyncio
async def test_store_version_contract_not_found() -> None:
    """Raises AppError 404 when contract does not exist."""
    session = _make_session()
    session.execute.return_value = _scalar_result(None)  # get_contract returns None

    with pytest.raises(AppError) as exc_info:
        await store_version(session, uuid.uuid4(), b"bytes", "file.pdf", "version")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


# ── list_versions tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_versions_returns_ordered_list() -> None:
    """Returns list of versions when contract exists."""
    contract_id = uuid.uuid4()
    contract = _make_contract(contract_id)
    v1 = _make_version(contract_id, version_number=1)
    v2 = _make_version(contract_id, version_number=2)

    session = _make_session()
    session.execute.side_effect = [
        _scalar_result(contract),  # get_contract
        _scalars_all_result([v1, v2]),  # SELECT versions
    ]

    result = await list_versions(session, contract_id)

    assert result == [v1, v2]


@pytest.mark.asyncio
async def test_list_versions_contract_not_found() -> None:
    """Raises AppError 404 when contract does not exist."""
    session = _make_session()
    session.execute.return_value = _scalar_result(None)  # get_contract returns None

    with pytest.raises(AppError) as exc_info:
        await list_versions(session, uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"
