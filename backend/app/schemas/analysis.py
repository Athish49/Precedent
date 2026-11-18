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
    # Zone-evaluator fields (migration 012 / task 1.3; populated by task 4.3's
    # evaluate_finding via task 4.4's Layer 2 wiring). Optional/nullable so
    # existing callers constructing a FlagDTO without them keep working.
    rule_key: str | None = None
    zone: str | None = None
    position_id: uuid.UUID | None = None
    red_line_id: uuid.UUID | None = None
    parameter_values: dict | None = None


class RiskDTO(BaseModel):
    score: float
    max_clause_severity: str | None
    weights_version: str
    # New (task 4.5; risk_score.max_zone, migration 012): the worst zone
    # among all flags on the contract. Defaulted so existing callers that
    # construct a RiskDTO without it (tests outside this task's scope) keep
    # working.
    max_zone: str | None = None


class AnalysisResult(BaseModel):
    flags: list[FlagDTO]
    risk: RiskDTO | None
