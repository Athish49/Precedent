from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FlagDTO(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    contract_id: uuid.UUID
    clause_id: uuid.UUID | None
    flag_type: str
    severity: str
    source: str
    char_start: int | None
    char_end: int | None
    detail: dict
    matched_rule_id: uuid.UUID | None
    created_at: datetime


class RiskDTO(BaseModel):
    score: float
    max_clause_severity: str | None
    weights_version: str


class AnalysisResult(BaseModel):
    flags: list[FlagDTO]
    risk: RiskDTO | None
