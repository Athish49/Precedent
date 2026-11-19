"""Response models for the Documents API (task 3.3).

Shapes follow ``document_processing_implementation.md`` section 4.3
exactly. These are read-side models only; the route builds them from ORM
rows (via ``clause_repo``/``field_repo`` for clauses and fields) rather than
re-using any old-pipeline DTO (``ProcessedContract`` et al., which belong to
the old ``service.py`` pipeline and are not imported here).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class UploadAcceptedResponse(BaseModel):
    """``POST /api/documents`` — 202 body."""

    contract_id: uuid.UUID
    version_id: uuid.UUID
    status: str


class ReprocessAcceptedResponse(BaseModel):
    """``POST /api/documents/{id}/reprocess`` — 202 body."""

    contract_id: uuid.UUID
    version_id: uuid.UUID | None
    status: str


class PartyResponse(BaseModel):
    party_id: uuid.UUID
    name: str
    role: str
    role_label: str | None
    entity_type: str | None
    jurisdiction: str | None
    address: str | None


class SignatoryResponse(BaseModel):
    printed_name: str | None
    title: str | None
    party_name: str | None
    is_signed: bool | None
    signed_date: date | None


class FieldInForceResponse(BaseModel):
    field_key: str
    value: Any
    source: str
    confidence: str | None
    quote: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    clause_id: uuid.UUID | None


class DocumentDetailResponse(BaseModel):
    """``GET /api/documents/{id}``."""

    id: uuid.UUID
    title: str
    original_filename: str | None
    status: str
    status_reason: str | None
    paper_origin: str
    source_format: str
    contract_type: str | None
    contract_type_source: str | None
    party_role: str | None
    context: dict | None
    counterparty_id: uuid.UUID | None
    current_version_id: uuid.UUID | None
    page_count: int | None
    created_at: datetime
    updated_at: datetime
    parties: list[PartyResponse]
    signatories: list[SignatoryResponse]
    fields: list[FieldInForceResponse]
    metadata: dict[str, Any]
    warnings: list[str]


class ClauseResponse(BaseModel):
    """One entry of ``GET /api/documents/{id}/clauses``."""

    id: uuid.UUID
    clause_key: uuid.UUID
    ordinal: int
    level: int
    parent_id: uuid.UUID | None
    section_number: str | None
    title: str | None
    heading_text: str | None
    clause_type: str
    type_source: str
    issue_keys: list[str]
    text: str
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None


class CanonicalTextResponse(BaseModel):
    """``GET /api/documents/{id}/text`` — unchanged shape."""

    contract_id: uuid.UUID
    canonical_text: str
