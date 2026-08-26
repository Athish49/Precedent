"""Versioning endpoints for contract repository (T-032 / T-034)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.repositories.contract_repo import list_contracts as repo_list_contracts
from app.db.repositories.search_repo import faceted_search, full_text_search
from app.services.repository.service import list_versions, store_version
from app.services.repository.smart_search import SmartSearchResult, smart_search
from app.services.repository.vector import PrecedentResult, precedent_search

router = APIRouter(tags=["repository"])

# ── Session dependency ────────────────────────────────────────────────────────


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

# ── Response models ───────────────────────────────────────────────────────────

_VALID_RELATIONS = {"version", "amendment", "addendum"}


class ContractSummary(BaseModel):
    id: uuid.UUID
    title: str
    source_format: str
    paper_origin: str
    status: str
    contract_type: str | None
    counterparty_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContractListResponse(BaseModel):
    items: list[ContractSummary]
    total: int
    limit: int
    offset: int


class RedlineHistoryItem(BaseModel):
    clause_type: str
    accept_rate: float
    last_closed_text: str | None


class SmartSearchRequest(BaseModel):
    query: str


class ContractVersionResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    version_number: int
    parent_version_id: uuid.UUID | None
    object_key: str
    canonical_text: str
    relation: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/repository/contracts/{contract_id}/versions",
    response_model=list[ContractVersionResponse],
)
async def get_versions(
    contract_id: uuid.UUID, session: SessionDep
) -> list[ContractVersionResponse]:
    """Return all versions for a contract, ordered by version_number ascending."""
    versions = await list_versions(session, contract_id)
    return [ContractVersionResponse.model_validate(v) for v in versions]


@router.post(
    "/repository/contracts/{contract_id}/versions",
    response_model=ContractVersionResponse,
    status_code=201,
)
async def create_version(
    contract_id: uuid.UUID,
    file: UploadFile,
    relation: str = Form(default="version"),
    session: SessionDep = ...,
) -> ContractVersionResponse:
    """Upload a new version of a contract."""
    if relation not in _VALID_RELATIONS:
        raise AppError(400, "invalid_relation", "relation must be version|amendment|addendum")
    file_bytes = await file.read()
    version = await store_version(
        session, contract_id, file_bytes, file.filename or "upload", relation  # type: ignore[arg-type]
    )
    return ContractVersionResponse.model_validate(version)


@router.get("/repository/contracts", response_model=ContractListResponse)
async def list_contracts(
    session: SessionDep,
    contract_type: str | None = Query(default=None),
    counterparty_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    effective_date_from: date | None = Query(default=None),
    effective_date_to: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ContractListResponse:
    """Faceted contract list with optional filters."""
    items, total = await repo_list_contracts(
        session,
        contract_type=contract_type,
        counterparty_id=counterparty_id,
        status=status,
        effective_date_from=effective_date_from,
        effective_date_to=effective_date_to,
        limit=limit,
        offset=offset,
    )
    return ContractListResponse(
        items=[ContractSummary.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/repository/search", response_model=ContractListResponse)
async def search_contracts(
    session: SessionDep,
    q: str | None = Query(default=None),
    type: str = Query(default="fulltext"),
    contract_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ContractListResponse:
    """Keyword full-text OR faceted search, selected by the `type` query param."""
    if type == "fulltext" and q:
        items, total = await full_text_search(session, q, limit=limit, offset=offset)
    elif type == "faceted":
        items, total = await faceted_search(
            session,
            contract_type=contract_type,
            status=status,
            q=q,
            limit=limit,
            offset=offset,
        )
    else:
        items, total = [], 0
    return ContractListResponse(
        items=[ContractSummary.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/repository/smart-search", response_model=SmartSearchResult)
async def smart_search_endpoint(
    body: SmartSearchRequest,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SmartSearchResult:
    """NL query → LLM filters → faceted + vector search."""
    return await smart_search(body.query, session, limit=limit, offset=offset)


@router.get("/repository/precedent-search", response_model=list[PrecedentResult])
async def precedent_search_endpoint(
    session: SessionDep,
    query: str = Query(...),
    clause_type: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[PrecedentResult]:
    """Vector ANN search over clause_embedding."""
    return await precedent_search(query, session, clause_type=clause_type, limit=limit)


@router.get(
    "/repository/contracts/{contract_id}/redline-history",
    response_model=list[RedlineHistoryItem],
)
async def get_redline_history(
    contract_id: uuid.UUID,
    session: SessionDep,
) -> list[RedlineHistoryItem]:
    # decision_event table added in later migration — return empty for now
    return []
