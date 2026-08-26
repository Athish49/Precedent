"""Unit tests for the S1 document-processing service (T-024).

All external dependencies (parser, segmenter, extraction, storage, DB session)
are mocked so no real I/O occurs.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_processing.service import ClauseDTO, ProcessedContract, process

# ── Shared test fixtures / helpers ─────────────────────────────────────────────

_FILE_BYTES = b"fake pdf content"
_FILENAME_PDF = "contract.pdf"
_FILENAME_DOCX = "contract.docx"
_PAPER_ORIGIN = "own"


def _make_parsed_doc(canonical_text: str = "Term\n\nThis is the term clause.") -> MagicMock:
    doc = MagicMock()
    doc.canonical_text = canonical_text
    return doc


def _make_seg_clause(
    ordinal: int = 0,
    heading_text: str | None = "Term",
    text: str = "Term\n\nThis is the term clause.",
    char_start: int = 0,
    char_end: int = 30,
) -> MagicMock:
    clause = MagicMock()
    clause.clause_id = f"c{ordinal:04d}"
    clause.ordinal = ordinal
    clause.heading_text = heading_text
    clause.text = text
    clause.char_start = char_start
    clause.char_end = char_end
    return clause


def _make_meta_dto() -> MagicMock:
    from app.services.document_processing.extraction import ContractMetadataDTO

    return ContractMetadataDTO(
        parties=[{"name": "Acme Corp", "role": "unknown"}],
        effective_date=date(2024, 1, 1),
        expiry_date=None,
        governing_law="New York",
        liability_cap=None,
        notice_period_days=30,
        auto_renewal=False,
        payment_terms="Net 30",
        financial_fields={},
        milestone_dates=[],
        extracted={},
    )


def _make_party_dto(
    display_name: str = "Acme Corp", normalized_name: str = "acme corp"
) -> MagicMock:
    from app.services.document_processing.extraction import PartyDTO

    return PartyDTO(display_name=display_name, normalized_name=normalized_name)


def _make_mock_session() -> AsyncMock:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no existing party
    mock_session.execute.return_value = mock_result
    return mock_session


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_returns_processed_contract() -> None:
    """process() returns a ProcessedContract with clauses and metadata populated."""
    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    party_dto = _make_party_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc(),
        ),
        patch(
            "app.services.document_processing.service.segment",
            return_value=[seg_clause],
        ),
        patch(
            "app.services.document_processing.service.normalize_clause_type",
            return_value="term",
        ),
        patch(
            "app.services.document_processing.service.extract_metadata",
            return_value=(meta_dto, [party_dto]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    assert isinstance(result, ProcessedContract)
    assert result.paper_origin == _PAPER_ORIGIN
    assert len(result.clauses) == 1
    clause = result.clauses[0]
    assert isinstance(clause, ClauseDTO)
    assert clause.clause_type == "term"
    assert clause.heading_text == "Term"
    assert result.metadata == meta_dto
    assert isinstance(result.contract_id, uuid.UUID)


@pytest.mark.asyncio
async def test_process_stores_bytes_in_storage() -> None:
    """process() calls storage.put() with the correct key and the original bytes."""
    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    party_dto = _make_party_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc(),
        ),
        patch(
            "app.services.document_processing.service.segment",
            return_value=[seg_clause],
        ),
        patch(
            "app.services.document_processing.service.normalize_clause_type",
            return_value="term",
        ),
        patch(
            "app.services.document_processing.service.extract_metadata",
            return_value=(meta_dto, [party_dto]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    # storage.put should have been called once with the right key pattern and bytes
    mock_storage.put.assert_called_once()
    call_args = mock_storage.put.call_args
    key_arg, bytes_arg = call_args[0]
    expected_prefix = f"contracts/{result.contract_id}/{_FILENAME_PDF}"
    assert key_arg == expected_prefix
    assert bytes_arg == _FILE_BYTES


@pytest.mark.asyncio
async def test_process_unsupported_format_raises() -> None:
    """process() raises ValueError for unsupported file extensions."""
    mock_session = _make_mock_session()

    with pytest.raises(ValueError, match="Unsupported file format"):
        await process(_FILE_BYTES, "contract.txt", _PAPER_ORIGIN, mock_session)


@pytest.mark.asyncio
async def test_process_pdf_dispatches_pdf_parser() -> None:
    """process() derives source_format='pdf' for a .pdf filename and passes it to parse()."""
    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc(),
        ) as mock_parse,
        patch(
            "app.services.document_processing.service.segment",
            return_value=[seg_clause],
        ),
        patch(
            "app.services.document_processing.service.normalize_clause_type",
            return_value="other",
        ),
        patch(
            "app.services.document_processing.service.extract_metadata",
            return_value=(meta_dto, []),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    mock_parse.assert_called_once_with(_FILE_BYTES, "pdf")


@pytest.mark.asyncio
async def test_process_clause_types_normalized() -> None:
    """process() calls normalize_clause_type for each segmented clause."""
    seg_clauses = [
        _make_seg_clause(ordinal=0, heading_text="Confidentiality", char_start=0, char_end=10),
        _make_seg_clause(ordinal=1, heading_text="Payment", char_start=12, char_end=22),
        _make_seg_clause(ordinal=2, heading_text=None, char_start=24, char_end=34),
    ]
    meta_dto = _make_meta_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()

    normalize_results = ["confidentiality", "payment", "other"]
    normalize_side_effect = iter(normalize_results)

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc(),
        ),
        patch(
            "app.services.document_processing.service.segment",
            return_value=seg_clauses,
        ),
        patch(
            "app.services.document_processing.service.normalize_clause_type",
            side_effect=normalize_side_effect,
        ) as mock_normalize,
        patch(
            "app.services.document_processing.service.extract_metadata",
            return_value=(meta_dto, []),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    # normalize_clause_type should be called once per clause
    assert mock_normalize.call_count == 3
    mock_normalize.assert_any_call("Confidentiality")
    mock_normalize.assert_any_call("Payment")
    mock_normalize.assert_any_call(None)

    # clause_types in result DTOs match the normalized values
    assert result.clauses[0].clause_type == "confidentiality"
    assert result.clauses[1].clause_type == "payment"
    assert result.clauses[2].clause_type == "other"
