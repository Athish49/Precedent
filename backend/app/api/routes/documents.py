"""S1 API — document upload and retrieval endpoints (T-025)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.models.clause import Clause
from app.db.models.contract import Contract, ContractMetadata
from app.services.document_processing.context_capture import (
    validate_contract_type,
    validate_context,
    validate_party_role,
)
from app.services.document_processing.service import ProcessedContract, process

router = APIRouter(tags=["documents"])

# ── Session dependency ────────────────────────────────────────────────────────


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

# ── Response models ───────────────────────────────────────────────────────────

_VALID_PAPER_ORIGINS = {"own", "counterparty"}


class ContractMetadataResponse(BaseModel):
    parties: list | None
    effective_date: date | None
    expiry_date: date | None
    governing_law: str | None
    liability_cap: dict | None
    notice_period_days: int | None
    auto_renewal: bool | None
    payment_terms: str | None
    financial_fields: dict | None
    milestone_dates: list | None
    extracted: dict | None


class ContractResponse(BaseModel):
    contract_id: uuid.UUID
    title: str
    source_format: str
    paper_origin: str
    status: str
    counterparty_id: uuid.UUID | None
    canonical_text: str
    created_at: datetime
    metadata: ContractMetadataResponse | None


class ClauseResponse(BaseModel):
    clause_id: str
    contract_id: uuid.UUID
    ordinal: int
    clause_type: str
    heading_text: str | None
    text: str
    char_start: int
    char_end: int


class CanonicalTextResponse(BaseModel):
    contract_id: uuid.UUID
    canonical_text: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/documents", response_model=ProcessedContract, status_code=201)
async def upload_document(
    file: UploadFile,
    paper_origin: str = Form(...),
    contract_type: str | None = Form(default=None),
    party_role: str | None = Form(default=None),
    context: str | None = Form(default=None),
    session: AsyncSession = Depends(_get_session),
) -> ProcessedContract:
    """Upload and process a contract document.

    ``contract_type``, ``party_role`` and ``context`` are optional (task
    4.1, item 1). ``context`` is a JSON object as a string, e.g.
    ``'{"region": "us", "deal_value": 250000}'``. When supplied,
    ``contract_type`` is validated against ``agreement_type`` and each
    recognised key in ``context`` is validated against ``context_dimension``
    — both checks are skipped gracefully where the relevant lookup table has
    no rows (``playbook_implementation.md`` section 4.1, item 6).
    """
    if paper_origin not in _VALID_PAPER_ORIGINS:
        raise AppError(
            400,
            "invalid_paper_origin",
            f"paper_origin must be one of {sorted(_VALID_PAPER_ORIGINS)!r}, got {paper_origin!r}",
        )

    if party_role is not None:
        validate_party_role(party_role)

    context_dict: dict | None = None
    if context is not None:
        try:
            context_dict = json.loads(context)
        except json.JSONDecodeError as exc:
            raise AppError(400, "invalid_context", f"context is not valid JSON: {exc}") from exc
        if not isinstance(context_dict, dict):
            raise AppError(400, "invalid_context", "context must be a JSON object")

    if contract_type is not None:
        await validate_contract_type(session, contract_type)

    if context_dict:
        await validate_context(session, context_dict)

    file_bytes = await file.read()
    try:
        result = await process(
            file_bytes,
            file.filename or "upload",
            paper_origin,
            session,
            contract_type=contract_type,
            party_role=party_role,
            context=context_dict,
        )
    except ValueError as exc:
        raise AppError(400, "unsupported_format", str(exc)) from exc

    return result


@router.get("/documents/{contract_id}", response_model=ContractResponse)
async def get_document(contract_id: uuid.UUID, session: SessionDep) -> ContractResponse:
    """Fetch a contract record and its metadata."""
    contract_row = (
        await session.execute(select(Contract).where(Contract.id == contract_id))
    ).scalar_one_or_none()

    if contract_row is None:
        raise AppError(404, "not_found", "Contract not found")

    meta_row = (
        await session.execute(
            select(ContractMetadata).where(ContractMetadata.contract_id == contract_id)
        )
    ).scalar_one_or_none()

    metadata_response: ContractMetadataResponse | None = None
    if meta_row is not None:
        metadata_response = ContractMetadataResponse(
            parties=meta_row.parties,
            effective_date=meta_row.effective_date,
            expiry_date=meta_row.expiry_date,
            governing_law=meta_row.governing_law,
            liability_cap=meta_row.liability_cap,
            notice_period_days=meta_row.notice_period_days,
            auto_renewal=meta_row.auto_renewal,
            payment_terms=meta_row.payment_terms,
            financial_fields=meta_row.financial_fields,
            milestone_dates=meta_row.milestone_dates,
            extracted=meta_row.extracted,
        )

    return ContractResponse(
        contract_id=contract_row.id,
        title=contract_row.title,
        source_format=contract_row.source_format,
        paper_origin=contract_row.paper_origin,
        status=contract_row.status,
        counterparty_id=contract_row.counterparty_id,
        canonical_text=contract_row.canonical_text,
        created_at=contract_row.created_at,
        metadata=metadata_response,
    )


@router.get("/documents/{contract_id}/clauses", response_model=list[ClauseResponse])
async def get_clauses(contract_id: uuid.UUID, session: SessionDep) -> list[ClauseResponse]:
    """Return all clauses for a contract, ordered by ordinal."""
    contract_exists = (
        await session.execute(select(Contract.id).where(Contract.id == contract_id))
    ).scalar_one_or_none()

    if contract_exists is None:
        raise AppError(404, "not_found", "Contract not found")

    clause_rows = (
        await session.execute(
            select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.ordinal)
        )
    ).scalars().all()

    return [
        ClauseResponse(
            clause_id=f"c{row.ordinal:04d}",
            contract_id=row.contract_id,
            ordinal=row.ordinal,
            clause_type=row.clause_type,
            heading_text=row.heading_text,
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
        )
        for row in clause_rows
    ]


@router.get("/documents/{contract_id}/text", response_model=CanonicalTextResponse)
async def get_canonical_text(
    contract_id: uuid.UUID, session: SessionDep
) -> CanonicalTextResponse:
    """Return the canonical text for a contract."""
    canonical_text = (
        await session.execute(
            select(Contract.canonical_text).where(Contract.id == contract_id)
        )
    ).scalar_one_or_none()

    if canonical_text is None:
        raise AppError(404, "not_found", "Contract not found")

    return CanonicalTextResponse(contract_id=contract_id, canonical_text=canonical_text)
