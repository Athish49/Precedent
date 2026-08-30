"""S1 document-processing service (T-024).

Orchestrates the full S1 pipeline and persists results to the database and
object storage.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import get_storage
from app.db.models.clause import Clause
from app.db.models.contract import Contract, ContractMetadata, Party
from app.services.document_processing.clause_types import normalize_clause_type
from app.services.document_processing.extraction import (
    ContractMetadataDTO,
    PartyDTO,
    extract_metadata,
)
from app.services.document_processing.parsers import parse
from app.services.document_processing.segmentation import segment

# ── DTOs ──────────────────────────────────────────────────────────────────────


class ClauseDTO(BaseModel):
    clause_id: str
    ordinal: int
    clause_type: str
    heading_text: str | None
    text: str
    char_start: int
    char_end: int


class ProcessedContract(BaseModel):
    contract_id: uuid.UUID
    canonical_text: str
    paper_origin: str
    counterparty_id: uuid.UUID | None
    clauses: list[ClauseDTO]
    metadata: ContractMetadataDTO


# ── Pipeline ──────────────────────────────────────────────────────────────────

_EXTENSION_TO_FORMAT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
}


def _source_format_from_filename(filename: str) -> str:
    """Derive source_format from the filename extension.

    Raises:
        ValueError: if the extension is not supported.
    """
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    fmt = _EXTENSION_TO_FORMAT.get(suffix)
    if fmt is None:
        raise ValueError(f"Unsupported file format: {filename!r}")
    return fmt


async def process(
    file_bytes: bytes,
    filename: str,
    paper_origin: str,
    session: AsyncSession,
) -> ProcessedContract:
    """Run the S1 document-processing pipeline and persist all results.

    Args:
        file_bytes: Raw file content.
        filename: Original filename (used to derive format and as the contract title).
        paper_origin: ``"own"`` or ``"counterparty"``.
        session: Async SQLAlchemy session (caller is responsible for lifecycle).

    Returns:
        A :class:`ProcessedContract` DTO with all extracted and persisted data.

    Raises:
        ValueError: if the file extension is not supported.
    """
    # 1. Derive format and parse
    source_format = _source_format_from_filename(filename)
    parsed_doc = parse(file_bytes, source_format)  # type: ignore[arg-type]

    # 2. Segment
    segmented_clauses = segment(parsed_doc)

    # 3. Normalize clause types
    clause_types_list = [normalize_clause_type(clause.heading_text) for clause in segmented_clauses]

    # 4. Extract metadata
    meta_dto, parties = extract_metadata(parsed_doc.canonical_text)

    # 5. Store bytes
    contract_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/{filename}"
    settings = get_settings()
    storage = get_storage(settings)
    storage.put(object_key, file_bytes)

    # 6. Upsert party (first party in list, if any)
    counterparty_id: uuid.UUID | None = None
    if parties:
        party_dto: PartyDTO = parties[0]
        result = await session.execute(
            select(Party).where(Party.normalized_name == party_dto.normalized_name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            counterparty_id = existing.id
        else:
            new_party = Party(
                normalized_name=party_dto.normalized_name,
                display_name=party_dto.display_name,
            )
            session.add(new_party)
            await session.flush()
            counterparty_id = new_party.id

    # 7. Persist contract
    contract = Contract(
        id=contract_id,
        title=filename,
        object_key=object_key,
        source_format=source_format,
        canonical_text=parsed_doc.canonical_text,
        paper_origin=paper_origin,
        counterparty_id=counterparty_id,
        status="processing",
    )
    session.add(contract)
    await session.flush()

    # 8. Persist clauses
    for i, seg_clause in enumerate(segmented_clauses):
        clause_type = clause_types_list[i]
        clause_row = Clause(
            id=uuid.uuid4(),
            contract_id=contract_id,
            ordinal=seg_clause.ordinal,
            clause_type=clause_type,
            heading_text=seg_clause.heading_text,
            text=seg_clause.text,
            char_start=seg_clause.char_start,
            char_end=seg_clause.char_end,
        )
        session.add(clause_row)
    await session.flush()

    # 9. Persist metadata
    extended = {
        "initial_term_days": meta_dto.initial_term_days,
        "renewal_term_days": meta_dto.renewal_term_days,
        "dispute_resolution": meta_dto.dispute_resolution,
        "arbitration_venue": meta_dto.arbitration_venue,
        "indemnification_cap": meta_dto.indemnification_cap,
        "total_contract_value": meta_dto.total_contract_value,
        "currency": meta_dto.currency,
        "notice_address": meta_dto.notice_address,
        "termination_for_convenience": meta_dto.termination_for_convenience,
        "termination_notice_days": meta_dto.termination_notice_days,
        "warranty_period_days": meta_dto.warranty_period_days,
        "confidentiality_period_years": meta_dto.confidentiality_period_years,
        "ip_ownership": meta_dto.ip_ownership,
        "assignment_allowed": meta_dto.assignment_allowed,
        "non_compete_months": meta_dto.non_compete_months,
        "non_solicitation_months": meta_dto.non_solicitation_months,
        "sla_uptime_percent": meta_dto.sla_uptime_percent,
        "sla_response_time_hours": meta_dto.sla_response_time_hours,
        "data_processing_agreement": meta_dto.data_processing_agreement,
        "gdpr_applicable": meta_dto.gdpr_applicable,
        "force_majeure": meta_dto.force_majeure,
        "entire_agreement": meta_dto.entire_agreement,
        "amendments_require_writing": meta_dto.amendments_require_writing,
        "limitation_of_liability_exclusions": meta_dto.limitation_of_liability_exclusions,
        "survival_clauses": meta_dto.survival_clauses,
        **meta_dto.extracted,
    }
    meta_row = ContractMetadata(
        contract_id=contract_id,
        parties=meta_dto.parties,
        effective_date=meta_dto.effective_date,
        expiry_date=meta_dto.expiry_date,
        governing_law=meta_dto.governing_law,
        liability_cap=meta_dto.liability_cap,
        notice_period_days=meta_dto.notice_period_days,
        auto_renewal=meta_dto.auto_renewal,
        payment_terms=meta_dto.payment_terms,
        financial_fields=meta_dto.financial_fields,
        milestone_dates=[d.isoformat() for d in meta_dto.milestone_dates],
        extracted=extended,
    )
    session.add(meta_row)
    await session.commit()

    # 10. Return DTO
    clause_dtos = [
        ClauseDTO(
            clause_id=seg_clause.clause_id,
            ordinal=seg_clause.ordinal,
            clause_type=clause_types_list[i],
            heading_text=seg_clause.heading_text,
            text=seg_clause.text,
            char_start=seg_clause.char_start,
            char_end=seg_clause.char_end,
        )
        for i, seg_clause in enumerate(segmented_clauses)
    ]

    return ProcessedContract(
        contract_id=contract_id,
        canonical_text=parsed_doc.canonical_text,
        paper_origin=paper_origin,
        counterparty_id=counterparty_id,
        clauses=clause_dtos,
        metadata=meta_dto,
    )
