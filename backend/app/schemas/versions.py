from __future__ import annotations

import uuid

from pydantic import BaseModel


class ChangeDTO(BaseModel):
    op: str
    text: str
    old_start: int
    old_end: int
    new_start: int
    new_end: int


class ClauseDiffDTO(BaseModel):
    clause_id: uuid.UUID
    clause_type: str
    heading_text: str | None
    ordinal: int
    char_start: int
    char_end: int
    change_type: str
    changes: list[ChangeDTO]


class VersionDiffResponse(BaseModel):
    contract_id: uuid.UUID
    v_a: uuid.UUID
    v_b: uuid.UUID
    v_a_number: int
    v_b_number: int
    clause_diffs: list[ClauseDiffDTO]
    global_changes: list[ChangeDTO]


class VersionSummaryRequest(BaseModel):
    contract_id: uuid.UUID
    v_a: uuid.UUID
    v_b: uuid.UUID


class VersionSummaryResponse(BaseModel):
    contract_id: uuid.UUID
    v_a: uuid.UUID
    v_b: uuid.UUID
    v_a_number: int
    v_b_number: int
    summary: str
    modified_clause_types: list[str]
