"""Documents API (task 3.3; document_processing_implementation.md section
3.3 / 4.3).

Switches the route internals over to the new ingest-based flow
(``document_processing/ingest.py``, task 3.1): upload writes ``contract`` +
``contract_version`` rows synchronously (``ingest.create_contract``) and
hands the Extend round-trip to a ``BackgroundTasks`` job
(``ingest.run_ingest``); the detail/clauses/text/reprocess routes read the
new tables. The old pipeline's files (``service.py``, ``parsers.py``,
``extraction.py``, ``segmentation.py``, ``clause_types.py``) are not
imported here — they are deleted outright in phase 5, once nothing else
references them.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.config import get_settings
from app.db.base import get_session_factory
from app.db.models.analysis import Flag
from app.db.models.contract import Contract, ContractMetadata, ContractVersion, Party
from app.db.models.party_link import ContractParty, ContractSignatory
from app.db.models.redline import Redline
from app.db.repositories import clause_repo, field_repo, ingest_repo
from app.schemas.documents import (
    CanonicalTextResponse,
    ClauseResponse,
    DocumentDetailResponse,
    FieldInForceResponse,
    PartyResponse,
    ReprocessAcceptedResponse,
    SignatoryResponse,
    UploadAcceptedResponse,
)
from app.services.document_processing.context_capture import (
    validate_contract_type,
    validate_context,
    validate_party_role,
)
from app.services.document_processing.ingest import create_contract, run_ingest
from app.services.document_processing.upload_validation import validate_upload

router = APIRouter(tags=["documents"])

# ── Session dependency ──────────────────────────────────────────────────────


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

# ``paper_origin`` has no lookup-table-backed validator in context_capture
# (only contract_type/party_role/context do) — same fixed set the old route
# used.
_VALID_PAPER_ORIGINS = frozenset({"own", "counterparty"})

# ── Metadata projection columns surfaced in GET /{id} ``metadata`` ─────────
# The typed contract_metadata columns ingest.py's write_metadata_projection
# writes (plan section 7.3 / fields.py's REGISTRY projections), not the old
# legacy columns (parties/liability_cap/financial_fields/... — those belong
# to the old pipeline and are dropped by phase 5's migration C).
_METADATA_FIELDS = (
    "effective_date",
    "expiry_date",
    "expiry_is_derived",
    "initial_term_months",
    "auto_renewal",
    "renewal_term_months",
    "renewal_notice_days",
    "governing_law",
    "dispute_resolution",
    "total_value_amount",
    "currency",
    "liability_cap_amount",
    "liability_cap_basis",
    "payment_terms_days",
    "termination_for_convenience",
    "termination_notice_days",
)


def _parse_context(context: str | None) -> dict[str, Any] | None:
    if context is None:
        return None
    try:
        parsed = json.loads(context)
    except json.JSONDecodeError as exc:
        raise AppError(400, "invalid_context", f"context is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AppError(400, "invalid_context", "context must be a JSON object")
    return parsed


# ── POST /documents ──────────────────────────────────────────────────────────


@router.post("/documents", response_model=UploadAcceptedResponse, status_code=202)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    paper_origin: str = Form(...),
    contract_type: str | None = Form(default=None),
    party_role: str | None = Form(default=None),
    context: str | None = Form(default=None),
    force: bool = Form(default=False),
    session: AsyncSession = Depends(_get_session),
) -> UploadAcceptedResponse:
    """Validate the upload, write ``contract``/``contract_version`` rows and
    schedule the Extend ingest in the background (section 4.3).
    """
    if paper_origin not in _VALID_PAPER_ORIGINS:
        raise AppError(
            400,
            "invalid_paper_origin",
            f"paper_origin must be one of {sorted(_VALID_PAPER_ORIGINS)!r}, got {paper_origin!r}",
        )

    if party_role is not None:
        validate_party_role(party_role)

    context_dict = _parse_context(context)

    if contract_type is not None:
        await validate_contract_type(session, contract_type)

    if context_dict:
        await validate_context(session, context_dict)

    data = await file.read()
    settings = get_settings()
    max_mb = int(getattr(settings, "max_upload_mb", 25))
    validated = validate_upload(file.filename or "upload", data, max_mb)

    contract_id, version_id = await create_contract(
        session,
        validated=validated,
        data=data,
        paper_origin=paper_origin,
        contract_type=contract_type,
        party_role=party_role,
        context=context_dict,
        force=force,
    )

    background_tasks.add_task(run_ingest, get_session_factory(), contract_id, version_id)

    return UploadAcceptedResponse(contract_id=contract_id, version_id=version_id, status="processing")


# ── GET /documents/{id} ──────────────────────────────────────────────────────


@router.get("/documents/{contract_id}", response_model=DocumentDetailResponse)
async def get_document(contract_id: uuid.UUID, session: SessionDep) -> DocumentDetailResponse:
    contract_row = (
        await session.execute(select(Contract).where(Contract.id == contract_id))
    ).scalar_one_or_none()
    if contract_row is None:
        raise AppError(404, "not_found", "Contract not found")

    page_count: int | None = None
    if contract_row.current_version_id is not None:
        page_count = (
            await session.execute(
                select(ContractVersion.page_count).where(
                    ContractVersion.id == contract_row.current_version_id
                )
            )
        ).scalar_one_or_none()

    parties: list[PartyResponse] = []
    signatories: list[SignatoryResponse] = []
    fields: list[FieldInForceResponse] = []
    metadata: dict[str, Any] = {}
    warnings: list[str] = []

    if contract_row.status != "processing":
        party_rows = (
            await session.execute(
                select(ContractParty, Party)
                .join(Party, Party.id == ContractParty.party_id)
                .where(ContractParty.contract_id == contract_id)
                .order_by(ContractParty.ordinal)
            )
        ).all()
        parties = [
            PartyResponse(
                party_id=party.id,
                name=party.display_name,
                role=cp.role,
                role_label=cp.role_label,
                entity_type=cp.entity_type,
                jurisdiction=cp.jurisdiction,
                address=cp.address,
            )
            for cp, party in party_rows
        ]

        if contract_row.current_version_id is not None:
            sig_rows = (
                await session.execute(
                    select(ContractSignatory, Party.display_name)
                    .outerjoin(
                        ContractParty, ContractParty.id == ContractSignatory.contract_party_id
                    )
                    .outerjoin(Party, Party.id == ContractParty.party_id)
                    .where(ContractSignatory.contract_version_id == contract_row.current_version_id)
                )
            ).all()
            signatories = [
                SignatoryResponse(
                    printed_name=sig.printed_name,
                    title=sig.title,
                    party_name=party_name,
                    is_signed=sig.is_signed,
                    signed_date=sig.signed_date,
                )
                for sig, party_name in sig_rows
            ]

            values_in_force = await field_repo.values_in_force(
                session, contract_row.current_version_id
            )
            fields = [
                FieldInForceResponse(
                    field_key=row.field_key,
                    value=row.value,
                    source=row.source,
                    confidence=row.confidence,
                    quote=row.quote,
                    page=row.page,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    clause_id=row.clause_id,
                )
                for row in values_in_force.values()
            ]

            meta_row = (
                await session.execute(
                    select(ContractMetadata).where(ContractMetadata.contract_id == contract_id)
                )
            ).scalar_one_or_none()
            if meta_row is not None:
                metadata = {field: getattr(meta_row, field) for field in _METADATA_FIELDS}

            latest = await ingest_repo.latest_run(session, contract_row.current_version_id)
            if latest is not None and latest.warnings:
                warnings = list(latest.warnings)

    return DocumentDetailResponse(
        id=contract_row.id,
        title=contract_row.title,
        original_filename=contract_row.original_filename,
        status=contract_row.status,
        status_reason=contract_row.status_reason,
        paper_origin=contract_row.paper_origin,
        source_format=contract_row.source_format,
        contract_type=contract_row.contract_type,
        contract_type_source=contract_row.contract_type_source,
        party_role=contract_row.party_role,
        context=contract_row.context,
        counterparty_id=contract_row.counterparty_id,
        current_version_id=contract_row.current_version_id,
        page_count=page_count,
        created_at=contract_row.created_at,
        updated_at=contract_row.updated_at,
        parties=parties,
        signatories=signatories,
        fields=fields,
        metadata=metadata,
        warnings=warnings,
    )


# ── GET /documents/{id}/clauses ──────────────────────────────────────────────


@router.get("/documents/{contract_id}/clauses", response_model=list[ClauseResponse])
async def get_clauses(
    contract_id: uuid.UUID,
    session: SessionDep,
    level: Literal["1", "all"] = Query(default="1"),
) -> list[ClauseResponse]:
    contract_exists = (
        await session.execute(select(Contract.id).where(Contract.id == contract_id))
    ).scalar_one_or_none()
    if contract_exists is None:
        raise AppError(404, "not_found", "Contract not found")

    repo_level = "all" if level == "all" else "top"
    clause_rows = await clause_repo.get_clauses_for_contract(
        session, contract_id, level=repo_level
    )

    return [
        ClauseResponse(
            id=row.id,
            clause_key=row.clause_key,
            ordinal=row.ordinal,
            level=row.level,
            parent_id=row.parent_id,
            section_number=row.section_number,
            title=row.title,
            heading_text=row.heading_text,
            clause_type=row.clause_type,
            type_source=row.type_source,
            issue_keys=list(row.issue_keys) if row.issue_keys else [],
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
            page_start=row.page_start,
            page_end=row.page_end,
        )
        for row in clause_rows
    ]


# ── GET /documents/{id}/text ─────────────────────────────────────────────────


@router.get("/documents/{contract_id}/text", response_model=CanonicalTextResponse)
async def get_canonical_text(
    contract_id: uuid.UUID, session: SessionDep
) -> CanonicalTextResponse:
    canonical_text = (
        await session.execute(select(Contract.canonical_text).where(Contract.id == contract_id))
    ).scalar_one_or_none()
    if canonical_text is None:
        raise AppError(404, "not_found", "Contract not found")

    return CanonicalTextResponse(contract_id=contract_id, canonical_text=canonical_text)


# ── POST /documents/{id}/reprocess ───────────────────────────────────────────


@router.post(
    "/documents/{contract_id}/reprocess",
    response_model=ReprocessAcceptedResponse,
    status_code=202,
)
async def reprocess_document(
    contract_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    force: bool = Query(default=False),
) -> ReprocessAcceptedResponse:
    contract_row = (
        await session.execute(select(Contract).where(Contract.id == contract_id))
    ).scalar_one_or_none()
    if contract_row is None:
        raise AppError(404, "not_found", "Contract not found")

    has_flag = (
        await session.execute(select(Flag.id).where(Flag.contract_id == contract_id).limit(1))
    ).scalar_one_or_none()
    has_redline = (
        await session.execute(
            select(Redline.id).where(Redline.contract_id == contract_id).limit(1)
        )
    ).scalar_one_or_none()

    if (has_flag is not None or has_redline is not None) and not force:
        raise AppError(
            409,
            "has_analysis",
            "This contract already has flags or redlines. Pass force=true to discard them.",
        )

    if force:
        if has_flag is not None:
            await session.execute(Flag.__table__.delete().where(Flag.contract_id == contract_id))
        if has_redline is not None:
            await session.execute(
                Redline.__table__.delete().where(Redline.contract_id == contract_id)
            )

    contract_row.status = "processing"
    contract_row.status_reason = None
    await session.commit()

    version_id = contract_row.current_version_id
    if version_id is not None:
        background_tasks.add_task(run_ingest, get_session_factory(), contract_id, version_id)

    return ReprocessAcceptedResponse(
        contract_id=contract_id, version_id=version_id, status="processing"
    )
