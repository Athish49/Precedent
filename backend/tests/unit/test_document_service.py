"""Unit tests for the S1 document-processing service (T-024, task 4.1).

All external dependencies (parser, segmenter, extraction, storage, DB session)
are mocked so no real I/O occurs. The task-4.1 context-capture steps
(classify_contract_type, derive_regimes, derive_deal_value_band) are made
inert by an autouse fixture for tests that predate task 4.1 and don't
exercise them; the dedicated task-4.1 tests near the bottom of this file
override that fixture to exercise the real functions end to end.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contract import Contract
from app.services.document_processing.service import ClauseDTO, ProcessedContract, process

# ── Context-capture defaults (task 4.1) ─────────────────────────────────────
#
# Tests written before task 4.1 call process() without a contract_type, which
# would otherwise now trigger a real LLM classification call and real DB
# queries. This autouse fixture keeps those steps inert, matching how `parse`,
# `segment` etc. are patched per-test below. Tests that want to exercise the
# real context-capture logic re-patch these names within their own body.


@pytest.fixture(autouse=True)
def _inert_context_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_classification(*_args: object, **_kwargs: object) -> None:
        return None

    async def _no_band(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.document_processing.service.classify_contract_type", _no_classification
    )
    monkeypatch.setattr(
        "app.services.document_processing.service.derive_regimes", lambda *_a, **_k: []
    )
    monkeypatch.setattr(
        "app.services.document_processing.service.derive_deal_value_band", _no_band
    )


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
        initial_term_days=None,
        renewal_term_days=None,
        governing_law="New York",
        dispute_resolution=None,
        arbitration_venue=None,
        liability_cap=None,
        indemnification_cap=None,
        total_contract_value=None,
        currency=None,
        notice_period_days=30,
        notice_address=None,
        auto_renewal=False,
        termination_for_convenience=None,
        termination_notice_days=None,
        payment_terms="Net 30",
        financial_fields={},
        milestone_dates=[],
        warranty_period_days=None,
        confidentiality_period_years=None,
        ip_ownership=None,
        assignment_allowed=None,
        non_compete_months=None,
        non_solicitation_months=None,
        sla_uptime_percent=None,
        sla_response_time_hours=None,
        data_processing_agreement=None,
        gdpr_applicable=None,
        force_majeure=None,
        entire_agreement=None,
        amendments_require_writing=None,
        limitation_of_liability_exclusions=[],
        survival_clauses=[],
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


# ── Task 4.1: contract type and context capture ────────────────────────────


def _agreement_type_row(key: str) -> MagicMock:
    row = MagicMock()
    row.key = key
    row.name = key
    row.kind = "agreement"
    return row


@pytest.mark.asyncio
async def test_process_classifies_contract_type_via_fake_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: contract_type not supplied -> the real classify_contract_type
    runs through the fake LLM gateway -> the persisted Contract has a non-null
    contract_type. This is the task 4.1 "done when" test.
    """
    from app.core.llm.schemas.classification import ContractTypeClassification
    from app.services.document_processing import context_capture
    from app.services.document_processing.context_capture import (
        classify_contract_type as real_classify_contract_type,
    )
    from tests.fake_llm import FakeLLMGateway

    # Un-stub classify_contract_type for this test only; derive_regimes and
    # derive_deal_value_band stay inert (no context passed in this test).
    monkeypatch.setattr(
        "app.services.document_processing.service.classify_contract_type",
        real_classify_contract_type,
    )

    fake_gateway = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(
                contract_type="saas_msa", confidence=0.9
            )
        }
    )
    monkeypatch.setattr(context_capture, "gateway", fake_gateway)

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    mock_storage = MagicMock()

    # No parties -> process() never queries for Party, so the single
    # session.execute() call is the agreement_type lookup inside
    # classify_contract_type.
    agreement_result = MagicMock()
    agreement_result.scalars.return_value.all.return_value = [
        _agreement_type_row("saas_msa"),
        _agreement_type_row("nda"),
    ]
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=agreement_result)

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc("Master Subscription Agreement\n\nTerms..."),
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
            return_value=(meta_dto, []),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    assert result.contract_type == "saas_msa"
    assert len(fake_gateway.calls) == 1

    # The persisted Contract row also carries the classified type.
    persisted_contracts = [
        call.args[0]
        for call in mock_session.add.call_args_list
        if isinstance(call.args[0], Contract)
    ]
    assert len(persisted_contracts) == 1
    assert persisted_contracts[0].contract_type == "saas_msa"


@pytest.mark.asyncio
async def test_process_low_confidence_classification_leaves_contract_type_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.llm.schemas.classification import ContractTypeClassification
    from app.services.document_processing import context_capture
    from app.services.document_processing.context_capture import (
        classify_contract_type as real_classify_contract_type,
    )
    from tests.fake_llm import FakeLLMGateway

    monkeypatch.setattr(
        "app.services.document_processing.service.classify_contract_type",
        real_classify_contract_type,
    )
    fake_gateway = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(
                contract_type="saas_msa", confidence=0.2
            )
        }
    )
    monkeypatch.setattr(context_capture, "gateway", fake_gateway)

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    mock_storage = MagicMock()
    agreement_result = MagicMock()
    agreement_result.scalars.return_value.all.return_value = [_agreement_type_row("saas_msa")]
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=agreement_result)

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc("Ambiguous short document."),
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
            return_value=(meta_dto, []),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(_FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session)

    assert result.contract_type is None


@pytest.mark.asyncio
async def test_process_skips_classification_when_contract_type_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the caller already supplied contract_type, classify_contract_type
    must not be called at all (no wasted LLM call)."""
    classify_mock = AsyncMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr(
        "app.services.document_processing.service.classify_contract_type", classify_mock
    )

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
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
            return_value=(meta_dto, [_make_party_dto()]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(
            _FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session, contract_type="dpa"
        )

    assert result.contract_type == "dpa"
    classify_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_derives_regimes_when_not_supplied(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.document_processing.context_capture import derive_regimes as real_derive_regimes

    monkeypatch.setattr(
        "app.services.document_processing.service.derive_regimes", real_derive_regimes
    )

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()
    hipaa_text = "Vendor is a Business Associate handling PHI on behalf of Customer."

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc(hipaa_text),
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
            return_value=(meta_dto, [_make_party_dto()]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(
            _FILE_BYTES, _FILENAME_PDF, _PAPER_ORIGIN, mock_session, contract_type="saas_msa"
        )

    assert result.context == {"regimes": ["hipaa"]}


@pytest.mark.asyncio
async def test_process_respects_explicitly_supplied_regimes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller already supplied regimes, derive_regimes must not override it,
    even if the text would otherwise trigger detection."""
    real_derive_regimes_mock = MagicMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr(
        "app.services.document_processing.service.derive_regimes", real_derive_regimes_mock
    )

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
    mock_session = _make_mock_session()
    mock_storage = MagicMock()

    with (
        patch(
            "app.services.document_processing.service.parse",
            return_value=_make_parsed_doc("Vendor is a Business Associate handling PHI."),
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
            return_value=(meta_dto, [_make_party_dto()]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(
            _FILE_BYTES,
            _FILENAME_PDF,
            _PAPER_ORIGIN,
            mock_session,
            contract_type="saas_msa",
            context={"regimes": []},
        )

    real_derive_regimes_mock.assert_not_called()
    assert result.context == {"regimes": []}


@pytest.mark.asyncio
async def test_process_derives_deal_value_band_from_supplied_deal_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    band_mock = AsyncMock(return_value="enterprise")
    monkeypatch.setattr(
        "app.services.document_processing.service.derive_deal_value_band", band_mock
    )

    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
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
            return_value=(meta_dto, [_make_party_dto()]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(
            _FILE_BYTES,
            _FILENAME_PDF,
            _PAPER_ORIGIN,
            mock_session,
            contract_type="saas_msa",
            context={"deal_value": 750_000},
        )

    band_mock.assert_called_once()
    assert band_mock.call_args.args[1] == 750_000
    assert result.context == {"deal_value": 750_000, "deal_value_band": "enterprise"}


@pytest.mark.asyncio
async def test_process_persists_party_role_and_context(monkeypatch: pytest.MonkeyPatch) -> None:
    seg_clause = _make_seg_clause()
    meta_dto = _make_meta_dto()
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
            return_value=(meta_dto, [_make_party_dto()]),
        ),
        patch(
            "app.services.document_processing.service.get_storage",
            return_value=mock_storage,
        ),
        patch("app.services.document_processing.service.get_settings"),
    ):
        result = await process(
            _FILE_BYTES,
            _FILENAME_PDF,
            _PAPER_ORIGIN,
            mock_session,
            contract_type="dpa",
            party_role="vendor",
            context={"region": "eu"},
        )

    assert result.party_role == "vendor"
    assert result.context == {"region": "eu"}

    persisted_contracts = [
        call.args[0]
        for call in mock_session.add.call_args_list
        if isinstance(call.args[0], Contract)
    ]
    assert len(persisted_contracts) == 1
    assert persisted_contracts[0].party_role == "vendor"
    assert persisted_contracts[0].context == {"region": "eu"}
